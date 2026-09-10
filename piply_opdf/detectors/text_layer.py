"""
Shared primitives for detectors that read the embedded PDF text layer.

Before this module, ``_merge_wrapped_words``, ``_group_words_by_line``,
``_line_bbox``, ``_scale_bbox`` and ``_is_excluded`` were copy-pasted into the
paragraph, key-value and list-item detectors — three drifting copies of the
same logic. They live here once.

Everything in this module works in **PDF points** (PyMuPDF's native units).
Convert to pixel space at the boundary with :meth:`PageContext.to_pixels`.
"""

from __future__ import annotations

from dataclasses import dataclass

import fitz

from piply_opdf.core.types import BBox, PageContext

__all__ = [
    "Word",
    "TextLine",
    "extract_words",
    "group_into_lines",
    "split_line_by_gap",
]


@dataclass(frozen=True, slots=True)
class Word:
    """A single word from the text layer, in points."""

    bbox: BBox
    text: str
    block: int
    line: int


@dataclass(frozen=True, slots=True)
class TextLine:
    """One visual line of text, in points."""

    words: tuple[Word, ...]

    @property
    def bbox(self) -> BBox:
        x0 = min(w.bbox.x for w in self.words)
        y0 = min(w.bbox.y for w in self.words)
        x1 = max(w.bbox.x1 for w in self.words)
        y1 = max(w.bbox.y1 for w in self.words)
        return BBox.from_xyxy(x0, y0, x1, y1)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words).strip()

    @property
    def left(self) -> int:
        return min(w.bbox.x for w in self.words)

    @property
    def right(self) -> int:
        return max(w.bbox.x1 for w in self.words)

    def gap_to(self, other: TextLine) -> float:
        """Vertical whitespace between this line's bottom and *other*'s top."""
        return max(0.0, other.bbox.y - self.bbox.y1)


def extract_words(page: PageContext) -> list[Word]:
    """Read every non-empty word from *page*'s text layer.

    When *page* is a crop — a container being searched from the inside — words
    outside the crop are dropped and the rest are moved into the crop's own
    coordinates. A detector therefore sees exactly what it would see if the crop
    were a page, and needs no knowledge of containers.

    Returns an empty list for scanned PDFs and image inputs — callers should
    branch on :attr:`PageContext.has_text_layer` rather than on emptiness here.
    """
    if page.source_path.suffix.lower() != ".pdf":
        return []

    try:
        with fitz.open(str(page.source_path)) as doc:
            raw = doc[page.page_number - 1].get_text("words")
    except Exception:
        return []

    words: list[Word] = []
    for item in raw:
        if len(item) < 7:
            continue
        text = str(item[4]).strip()
        if not text:
            continue
        words.append(
            Word(
                bbox=BBox.from_xyxy(item[0], item[1], item[2], item[3]),
                text=text,
                block=int(item[5]),
                line=int(item[6]),
            )
        )

    return _restrict_to_region(words, page)


def _restrict_to_region(words: list[Word], page: PageContext) -> list[Word]:
    """Keep words inside a cropped context, in that crop's coordinates."""
    if page.region is None:
        return words

    # Words are in points; the region is in pixels.
    left = page.region.x / page.scale
    top = page.region.y / page.scale
    right = left + page.width / page.scale
    bottom = top + page.height / page.scale

    kept: list[Word] = []
    for word in words:
        cx, cy = word.bbox.center
        if not (left <= cx <= right and top <= cy <= bottom):
            continue
        kept.append(
            Word(
                bbox=BBox(
                    int(word.bbox.x - left), int(word.bbox.y - top),
                    word.bbox.width, word.bbox.height,
                ),
                text=word.text,
                block=word.block,
                line=word.line,
            )
        )
    return kept


def _merge_bracketed(words: list[Word]) -> list[Word]:
    """Join words split across an unclosed bracket or parenthesis.

    ``"(see"``, ``"note"``, ``"3)"`` becomes one ``"(see note 3)"`` token, so a
    parenthetical is not torn apart into separate review units.
    """
    merged: list[Word] = []
    i = 0
    n = len(words)

    while i < n:
        word = words[i]
        opens_bracket = word.text.startswith("[")
        opens_paren = word.text.startswith("(")
        stripped = word.text.rstrip(".,:;")
        already_closed = stripped.endswith("]") or stripped.endswith(")")

        if (opens_bracket or opens_paren) and not already_closed:
            closer = "]" if opens_bracket else ")"
            group = [word]
            j = i + 1
            found = False
            while j < n:
                group.append(words[j])
                if words[j].text.rstrip(".,:;").endswith(closer):
                    found = True
                    break
                j += 1

            if found:
                merged.append(
                    Word(
                        bbox=BBox.from_xyxy(
                            min(g.bbox.x for g in group),
                            min(g.bbox.y for g in group),
                            max(g.bbox.x1 for g in group),
                            max(g.bbox.y1 for g in group),
                        ),
                        text=" ".join(g.text for g in group),
                        block=word.block,
                        line=word.line,
                    )
                )
                i = j + 1
                continue

        merged.append(word)
        i += 1

    return merged


def group_into_lines(
    words: list[Word],
    *,
    merge_brackets: bool = True,
    merge_baselines: bool = True,
) -> list[TextLine]:
    """Group words into visual lines, ordered top-to-bottom then left-to-right.

    Two passes:

    1. Bucket by PyMuPDF's block/line numbering, which handles mixed font sizes
       within a run better than clustering on y-coordinates alone.
    2. Merge buckets that share a baseline.

    The second pass matters for forms. A row such as::

        Ref. Dr.  : SELF-INSURANCE      Collected On  : 11-Feb-2026 11:58 AM

    is frequently emitted as four independent blocks, so block numbering alone
    reports four "lines" where a reader sees one. Any detector reasoning about
    a line — key-value pairing above all — needs the visual line.
    """
    if not words:
        return []

    buckets: dict[tuple[int, int], list[Word]] = {}
    for word in words:
        buckets.setdefault((word.block, word.line), []).append(word)

    lines: list[TextLine] = []
    for bucket in buckets.values():
        bucket.sort(key=lambda w: w.bbox.x)
        if merge_brackets:
            bucket = _merge_bracketed(bucket)
        lines.append(TextLine(tuple(bucket)))

    lines.sort(key=lambda ln: (ln.bbox.y, ln.bbox.x))

    if merge_baselines:
        lines = _merge_shared_baselines(lines)

    return lines


def _merge_shared_baselines(lines: list[TextLine], overlap_ratio: float = 0.5) -> list[TextLine]:
    """Join lines whose vertical spans substantially overlap.

    Overlap is measured against the shorter of the two, so a small-print label
    still merges with the larger value sitting beside it.
    """
    if len(lines) < 2:
        return lines

    merged: list[list[Word]] = [list(lines[0].words)]
    reference = lines[0].bbox

    for line in lines[1:]:
        overlap = min(reference.y1, line.bbox.y1) - max(reference.y, line.bbox.y)
        shorter = min(reference.height, line.bbox.height)
        if shorter > 0 and overlap / shorter > overlap_ratio:
            merged[-1].extend(line.words)
            merged[-1].sort(key=lambda w: w.bbox.x)
            xs = merged[-1]
            reference = BBox.from_xyxy(
                min(w.bbox.x for w in xs), min(w.bbox.y for w in xs),
                max(w.bbox.x1 for w in xs), max(w.bbox.y1 for w in xs),
            )
        else:
            merged.append(list(line.words))
            reference = line.bbox

    return [TextLine(tuple(group)) for group in merged]


def split_line_by_gap(line: TextLine, threshold: float) -> list[TextLine]:
    """Split *line* wherever the horizontal gap between words exceeds
    *threshold* points.
    """
    if len(line.words) < 2:
        return [line]

    chunks: list[list[Word]] = [[line.words[0]]]
    for previous, current in zip(line.words, line.words[1:]):
        if (current.bbox.x - previous.bbox.x1) > threshold:
            chunks.append([current])
        else:
            chunks[-1].append(current)

    return [TextLine(tuple(chunk)) for chunk in chunks]


def split_line_by_columns(
    line: TextLine,
    *,
    relative_gap: float = 2.5,
    min_height_multiple: float = 2.0,
) -> list[TextLine]:
    """Split *line* at column boundaries only.

    Form layouts place several key-value pairs side by side::

        Ref. Dr.  : SELF-INSURANCE        Collected On  : 11-Feb-2026 11:58 AM

    A fixed gap threshold cannot separate the column boundary from the gap
    between a key and its own value — both exceed normal word spacing, and
    which is larger depends on font size and column width. The boundary is
    instead found from the line's *own* gap distribution, so it adapts to any
    layout.
    """
    if len(line.words) < 4:
        return [line]

    gaps = [
        current.bbox.x - previous.bbox.x1
        for previous, current in zip(line.words, line.words[1:])
    ]
    positive = sorted(g for g in gaps if g > 0)
    if not positive:
        return [line]

    median_gap = positive[len(positive) // 2]
    text_height = max(w.bbox.height for w in line.words)
    threshold = max(median_gap * relative_gap, text_height * min_height_multiple)

    chunks: list[list[Word]] = [[line.words[0]]]
    for gap, word in zip(gaps, line.words[1:]):
        if gap > threshold:
            chunks.append([word])
        else:
            chunks[-1].append(word)

    return [TextLine(tuple(chunk)) for chunk in chunks]
