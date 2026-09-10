"""Key-value detection from the rendered page, for scanned documents.

Without a text layer the separator character cannot be read, so the split is
inferred from geometry. Line-merging dilation already breaks a ``key      value``
row into **two separate ink clusters on one baseline** — a wide gap survives
dilation while ordinary word spacing does not. So a baseline carrying exactly
two clusters, separated by a gap wide relative to the text height, is a
key-value candidate.

The gap test is expressed as a multiple of text height rather than an absolute
distance, so it holds at any font size, page size and render DPI.
"""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import binarize, find_text_lines, to_grayscale

__all__ = ["CvKeyValueStrategy"]


class CvKeyValueStrategy(DetectionStrategy):
    """Infers key-value rows from two clusters sharing a baseline."""

    name = "cv-gap"
    priority = 10

    def __init__(
        self,
        *,
        min_gap_height_ratio: float = 1.2,
        top_margin_ratio: float = 0.12,
        bottom_margin_ratio: float = 0.88,
    ) -> None:
        #: Gap between key and value must exceed this multiple of text height.
        #: Ordinary word spacing is well under 1x; a column gap is comfortably over.
        self.min_gap_height_ratio = min_gap_height_ratio
        self.top_margin_ratio = top_margin_ratio
        self.bottom_margin_ratio = bottom_margin_ratio

    def is_applicable(self, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        body_top = int(page.height * self.top_margin_ratio)
        body_bottom = int(page.height * self.bottom_margin_ratio)
        if body_bottom <= body_top:
            return []

        crop = page.image[body_top:body_bottom, 0:page.width]
        binary = binarize(to_grayscale(crop))

        for ex in exclusions:
            ex_y0 = max(0, ex.y - body_top)
            ex_y1 = min(body_bottom - body_top, ex.y1 - body_top)
            ex_x0 = max(0, ex.x)
            ex_x1 = min(page.width, ex.x1)
            if ex_x1 > ex_x0 and ex_y1 > ex_y0:
                binary[ex_y0:ex_y1, ex_x0:ex_x1] = 0

        results: list[DetectedComponent] = []
        index = 1

        for baseline in _group_by_baseline(find_text_lines(binary, dpi=page.dpi)):
            for column in _split_into_columns(baseline):
                parsed = self._as_key_value(column)
                if parsed is None:
                    continue

                key_box, separator_box, value_box = parsed
                full = BBox.from_xyxy(
                    key_box.x, min(key_box.y, value_box.y) + body_top,
                    value_box.x1, max(key_box.y1, value_box.y1) + body_top,
                )

                # Detection records *where* the split is; the segmenter turns
                # that into KEY / SEPARATOR / VALUE units. Attaching children
                # here would pre-empt segmentation entirely.
                metadata = {
                    "strategy": self.name,
                    "needs_ocr": True,
                    "key_bbox": [
                        key_box.x, key_box.y + body_top, key_box.width, key_box.height,
                    ],
                    "value_bbox": [
                        value_box.x, value_box.y + body_top, value_box.width, value_box.height,
                    ],
                }
                if separator_box is not None:
                    metadata["separator_bbox"] = [
                        separator_box.x, separator_box.y + body_top,
                        separator_box.width, separator_box.height,
                    ]

                results.append(
                    DetectedComponent(
                        id=f"key_value_{page.page_number:03d}_{index:03d}",
                        type=ComponentType.KEY_VALUE,
                        page=page.page_number,
                        bbox=full,
                        text="",
                        confidence=0.65,
                        index=index,
                        metadata=metadata,
                    )
                )
                index += 1

        return results

    def _as_key_value(
        self,
        column: list[BBox],
    ) -> tuple[BBox, BBox | None, BBox] | None:
        """Return ``(key, separator, value)`` when *column* is a key-value row.

        Two shapes are accepted:

        * two clusters — ``key`` and ``value``, separator absorbed into one of
          them or absent entirely;
        * three clusters where the middle is very narrow — the separator glyph
          (``:`` or ``=``) survived as its own cluster, which is the ideal case
          because it gives the separator's geometry directly.

        Anything else is prose (one cluster) or a table row (four or more that
        did not split into columns).
        """
        if not column:
            return None

        text_height = max(b.height for b in column)
        if text_height <= 0:
            return None

        if len(column) == 2:
            key, value = column
            separator = None
        else:
            # Look for the separator glyph: a lone narrow cluster that is
            # neither the first nor the last. Once found it anchors the split —
            # everything before is the key, everything after is the value.
            # A multi-word value fragments into several clusters, so the value
            # must be their union rather than a single cluster.
            separator_at = next(
                (
                    i for i in range(1, len(column) - 1)
                    if column[i].width <= text_height * 0.6
                ),
                None,
            )
            if separator_at is None:
                return None

            separator = column[separator_at]
            key = _union(column[:separator_at])
            value = _union(column[separator_at + 1:])

        text_height = max(key.height, value.height)
        if text_height <= 0:
            return None

        gap = value.x - key.x1
        if gap < text_height * self.min_gap_height_ratio:
            return None

        return key, separator, value


def _split_into_columns(
    baseline: list[BBox],
    *,
    relative_gap: float = 2.0,
    min_height_multiple: float = 3.0,
) -> list[list[BBox]]:
    """Split a baseline at column separators.

    Form layouts put several key-value pairs side by side on one line::

        Ref. Dr.  : SELF-INSURANCE        Collected On  : 11-Feb-2026 11:58 AM

    The gap between columns is markedly wider than the gaps inside a pair, so
    the split point is found from the line's *own* gap distribution rather than
    an absolute distance — which keeps it working at any font size, column
    count and page width.
    """
    if len(baseline) < 4:
        return [baseline]

    gaps = [baseline[i + 1].x - baseline[i].x1 for i in range(len(baseline) - 1)]
    if not gaps:
        return [baseline]

    ordered = sorted(gaps)
    median_gap = ordered[len(ordered) // 2]
    text_height = max(b.height for b in baseline)

    threshold = max(median_gap * relative_gap, text_height * min_height_multiple)

    columns: list[list[BBox]] = [[baseline[0]]]
    for gap, box in zip(gaps, baseline[1:]):
        if gap > threshold:
            columns.append([box])
        else:
            columns[-1].append(box)

    if len(columns) == 1 and len(baseline) % 2 == 0:
        # A long value can run close to the next column, leaving a gap under
        # the threshold. An even cluster count is itself evidence of paired
        # columns, so fall back to splitting at the single widest gap.
        widest_at = max(range(len(gaps)), key=gaps.__getitem__)
        columns = [baseline[: widest_at + 1], baseline[widest_at + 1:]]

    return columns


def _union(boxes: list[BBox]) -> BBox:
    return BBox.from_xyxy(
        min(b.x for b in boxes), min(b.y for b in boxes),
        max(b.x1 for b in boxes), max(b.y1 for b in boxes),
    )


def _group_by_baseline(lines: list[BBox], overlap_ratio: float = 0.5) -> list[list[BBox]]:
    """Cluster line boxes that share a baseline, ordered left to right.

    Two boxes belong to the same baseline when their vertical spans overlap by
    more than *overlap_ratio* of the shorter box's height.
    """
    if not lines:
        return []

    remaining = sorted(lines, key=lambda b: (b.y, b.x))
    baselines: list[list[BBox]] = [[remaining[0]]]

    for box in remaining[1:]:
        current = baselines[-1]
        reference = current[0]
        overlap = min(reference.y1, box.y1) - max(reference.y, box.y)
        shorter = min(reference.height, box.height)
        if shorter > 0 and overlap / shorter > overlap_ratio:
            current.append(box)
        else:
            baselines.append([box])

    for baseline in baselines:
        baseline.sort(key=lambda b: b.x)
    return baselines
