"""
Deciding where one row ends and the next begins.

This is the part that makes borderless tables work, and the part the obvious
approach gets wrong. Clustering text by horizontal whitespace turns this:

    Date       Description                        Amount
               continuation of long description
               another continuation
    05/01      Payment                            500

into four rows where there are two. Every column after `Description` is then
matched against the wrong row, and a statement reads as though payments
happened on dates they did not.

**The rule that makes it work:** no single column may be the mandatory row
anchor. A row is not "wherever the date column has a value" — some rows have no
date, some have a value only in the last column, a total line may fill two
cells out of six. Anchoring on one column bakes in an assumption about one
document that will be wrong on the next.

Instead a row boundary is *evidence-weighted*, exactly like confidence
elsewhere: how many columns gained a value, how the vertical gap compares with
this document's own line spacing, and whether the line is indented like a
continuation. Each is a measurement, and the combination becomes
``row_confidence`` so a doubtful split can be reviewed rather than trusted.
"""

from __future__ import annotations

from statistics import median

from piply_opdf.core.types import BBox
from piply_opdf.structure.types import Column, Row, TextBlock

__all__ = ["group_lines", "find_rows", "ROW_EVIDENCE_WEIGHTS"]

#: What makes a line a new row rather than a wrap.
#:
#: ``spread`` leads because it is the anchor-free one: a line that fills four
#: of five columns is a row whatever column it starts in, and a line filling
#: only the description column is a wrap whatever it says. It is the direct
#: expression of "no single column may be the mandatory anchor".
#:
#: ``gap`` is next — a genuinely new row usually sits further below its
#: predecessor than a wrapped line does, but not always, so it cannot decide
#: alone.
#:
#: ``indent`` is weakest. Continuations are often indented to their column's
#: text start, but plenty of documents do not indent at all, and reading a
#: missing indent as evidence of a new row would split every wrapped line in
#: those documents.
ROW_EVIDENCE_WEIGHTS: dict[str, float] = {
    "spread": 3.0,
    "gap": 2.0,
    "indent": 1.0,
}

#: A line must fill at least this share of the columns the table normally uses
#: before its spread alone marks it a new row.
_ROW_SPREAD = 0.5

#: A vertical gap this many times the document's own median line gap reads as
#: row spacing rather than line spacing. Relative to the document, so a tightly
#: set statement and an airy invoice are both judged on their own terms.
_ROW_GAP_RATIO = 1.4

#: Below this, a row boundary is doubtful enough to be worth a person's glance.
DOUBTFUL_BELOW = 0.5


def group_lines(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Blocks sharing a writing line, clustered on baselines.

    On the bottom edge rather than the centre: characters sit on a common
    baseline while their heights vary, so a line mixing capitals and lowercase
    has one baseline and several centres.
    """
    if not blocks:
        return []

    tolerance = _typical_height(blocks) * 0.5
    ordered = sorted(blocks, key=lambda b: (b.baseline, b.bbox.x))

    lines: list[list[TextBlock]] = [[ordered[0]]]
    for block in ordered[1:]:
        anchor = median([b.baseline for b in lines[-1]])
        if abs(block.baseline - anchor) <= tolerance:
            lines[-1].append(block)
        else:
            lines.append([block])

    for line in lines:
        line.sort(key=lambda b: b.bbox.x)
    return lines


def find_rows(blocks: list[TextBlock], columns: list[Column]) -> list[Row]:
    """Logical rows, with wrapped lines folded into the row they belong to."""
    lines = group_lines(blocks)
    if not lines:
        return []

    gaps = _line_gaps(lines)
    typical_gap = median(gaps) if gaps else 0.0

    rows: list[Row] = []
    current: list[list[TextBlock]] = [lines[0]]
    evidence_for_current: dict[str, float] = {"spread": 1.0, "gap": 1.0, "indent": 1.0}

    for position, line in enumerate(lines[1:], start=1):
        evidence = _boundary_evidence(
            line, current[0], columns,
            gap=gaps[position - 1] if position - 1 < len(gaps) else 0.0,
            typical_gap=typical_gap,
        )
        if _weighted(evidence) >= 0.5:
            rows.append(_assemble(len(rows), current, evidence_for_current))
            current, evidence_for_current = [line], evidence
        else:
            current.append(line)                 # a wrap of the row above

    rows.append(_assemble(len(rows), current, evidence_for_current))
    return rows


def _boundary_evidence(
    line: list[TextBlock],
    row_start: list[TextBlock],
    columns: list[Column],
    *,
    gap: float,
    typical_gap: float,
) -> dict[str, float]:
    """How strongly this line starts a new row rather than continuing one.

    Compared against the **row's first line**, not the physically preceding
    one. The plan says a continuation is "indented to the column's text start
    rather than to a new row's start", and the row's start is what that means.

    Found by running it: a description wrapping onto *two* lines lost the
    indent evidence on the second, because that line's predecessor was the
    first continuation and they share a left edge. Comparing against the row
    instead, both wraps read as indented, which is what they are.
    """
    return {
        "spread": _spread_evidence(line, columns),
        "gap": _gap_evidence(gap, typical_gap),
        "indent": _indent_evidence(line, row_start),
    }


def _spread_evidence(line: list[TextBlock], columns: list[Column]) -> float:
    """How much of the table's width this line uses.

    The anchor-free signal, and the one that does the work. A line touching
    most of the columns is a row no matter which column it begins in; a line
    touching one is a wrap no matter what it contains. Neither judgement names
    a particular column, which is the whole point.
    """
    if len(columns) < 2:
        return 1.0                    # one column: every line is its own row

    touched = {c.index for c in columns for b in line if c.holds(b)}
    share = len(touched) / len(columns)
    return min(1.0, share / _ROW_SPREAD)


def _gap_evidence(gap: float, typical: float) -> float:
    """How far below its predecessor this line sits, in this document's terms.

    Compared with the document's own median line gap rather than a fixed
    distance, because row spacing on a dense bank statement is tighter than
    line spacing on an airy invoice, and a fixed threshold would be wrong for
    one of them.
    """
    if typical <= 0:
        return 0.5                    # nothing to compare against: no opinion
    return min(1.0, (gap / typical) / _ROW_GAP_RATIO)


def _indent_evidence(line: list[TextBlock], row_start: list[TextBlock]) -> float:
    """Whether the line starts where its row starts, or further in.

    Weakest of the three, deliberately. Many documents do not indent
    continuations at all, so a line that is *not* indented is barely evidence
    of anything — which is why an un-indented line still scores 0.5 rather than
    1.0 and needs help from the other two.
    """
    if not line or not row_start:
        return 0.5

    start, before = line[0].bbox.x, row_start[0].bbox.x
    height = _typical_height(line + row_start)

    if start > before + height:
        return 0.0                    # clearly indented: a continuation
    if start < before - height:
        return 1.0                    # starts further left: a new row
    return 0.5                         # same place: says nothing either way


def _weighted(evidence: dict[str, float]) -> float:
    total = sum(ROW_EVIDENCE_WEIGHTS[k] * v for k, v in evidence.items())
    return total / sum(ROW_EVIDENCE_WEIGHTS[k] for k in evidence)


def _assemble(
    index: int, lines: list[list[TextBlock]], evidence: dict[str, float],
) -> Row:
    blocks = [b for line in lines for b in line]
    return Row(
        index=index,
        bbox=_bounding(blocks),
        blocks=tuple(blocks),
        confidence=round(_weighted(evidence), 4),
        evidence={k: round(v, 4) for k, v in evidence.items()},
        lines=len(lines),
    )


def _line_gaps(lines: list[list[TextBlock]]) -> list[float]:
    """Baseline-to-baseline distance between consecutive lines."""
    anchors = [median([b.baseline for b in line]) for line in lines]
    return [b - a for a, b in zip(anchors, anchors[1:])]


def _bounding(blocks: list[TextBlock]) -> BBox:
    if not blocks:
        return BBox(0, 0, 0, 0)
    x0 = min(b.bbox.x for b in blocks)
    y0 = min(b.bbox.y for b in blocks)
    x1 = max(b.bbox.x1 for b in blocks)
    y1 = max(b.bbox.y1 for b in blocks)
    return BBox(x0, y0, x1 - x0, y1 - y0)


def _typical_height(blocks: list[TextBlock]) -> float:
    heights = [b.bbox.height for b in blocks if b.bbox.height > 0]
    return median(heights) if heights else 1.0
