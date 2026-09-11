"""
Finding the columns of a table nobody drew lines on.

A column is not a place where text happens to start. It is a **gap that
persists** — a vertical strip that stays empty line after line, while the text
either side of it does not. One line with a wide word space is a coincidence;
twenty lines all leaving the same strip clear is a column boundary.

Everything here is measured against the text's own size rather than in pixels,
so the same document at 150 and 600 DPI produces the same columns.
"""

from __future__ import annotations

from statistics import median

from piply_opdf.structure.types import Column, TextBlock

__all__ = ["find_columns", "MIN_GAP_IN_HEIGHTS", "MIN_GAP_PERSISTENCE"]

#: A gap must be at least this many text-heights wide to separate columns.
#:
#: In points, a word space is roughly a quarter of the type size and an em is
#: one; 1.5 heights is far wider than either, so ordinary spacing inside a
#: sentence cannot produce one. Expressed in heights rather than pixels so it
#: holds at any resolution.
MIN_GAP_IN_HEIGHTS = 1.5

#: And it must be clear on at least this share of the lines. The number is what
#: separates a column from a coincidence: a long description that happens to
#: stop short on three lines out of forty leaves a gap those three times, and
#: without a persistence test that becomes a column boundary running through
#: the middle of a sentence.
MIN_GAP_PERSISTENCE = 0.75

#: Ignore columns narrower than this share of the table. Below it, what has
#: been found is the space between two words rather than a column.
_MIN_COLUMN_SHARE = 0.02


def find_columns(blocks: list[TextBlock]) -> list[Column]:
    """The vertical bands this text lines up in.

    Returns a single full-width column when no gap persists — which is the
    correct answer for a paragraph, and the answer that stops a block of prose
    being reported as a one-column table with forty rows.
    """
    if not blocks:
        return []

    left = min(b.bbox.x for b in blocks)
    right = max(b.bbox.x1 for b in blocks)
    if right <= left:
        return []

    lines = _group_by_line(blocks)
    gaps = _persistent_gaps(lines, left, right)

    if not gaps:
        return [Column(index=0, x0=left, x1=right)]

    # A column runs from where its own text starts to where the *next* column's
    # text starts — not to where its own text usually stops.
    #
    # Both halves of that were found by running it on a statement with a
    # wrapped description.
    #
    # Ragged right margins are clear on most lines too, so the gap after a
    # column of prose begins at the shortest line's end and runs all the way to
    # the next column. Ending a band at its gap's *start* cut the column off at
    # its narrowest line and left every longer value outside every cell.
    #
    # And the boundary is snapped to real text rather than to the search grid.
    # Gaps are counted on a coarse grid so two boundaries a pixel apart are one
    # boundary, which means a gap's recorded end overshoots by up to a step —
    # enough that "the first text at or after the end" skipped a column whose
    # words began three pixels earlier. Searching forward from the gap's
    # *start* has no such edge.
    starts = [int(left)] + [_text_resumes_after(blocks, start) for start, _end in gaps]
    ends = starts[1:] + [int(right)]

    span = right - left
    bands = [
        Column(index=0, x0=x0, x1=x1)
        for x0, x1 in zip(starts, ends)
        if x1 - x0 >= span * _MIN_COLUMN_SHARE
    ]

    # A band holding no text is not a column. Integer rounding at a table's
    # right edge can leave a sliver a few pixels wide that passes the width
    # test — visible only when the same table is measured at half resolution,
    # where it produced a fourth, empty column. Asking whether anything is
    # actually in it is exact at any resolution.
    filled = [c for c in bands if any(c.holds(b) for b in blocks)]
    return [Column(index=i, x0=c.x0, x1=c.x1) for i, c in enumerate(filled)]


def _text_resumes_after(blocks: list[TextBlock], gap_start: float) -> int:
    """The leftmost text beginning anywhere past *gap_start*.

    Falls back to *gap_start* when nothing does, which happens only when the
    gap runs to the end of the table — and then there is no column beyond it,
    so the value is never used.
    """
    starts = [b.bbox.x for b in blocks if b.bbox.x >= gap_start]
    return int(min(starts)) if starts else int(gap_start)


def _group_by_line(blocks: list[TextBlock]) -> list[list[TextBlock]]:
    """Blocks sharing a writing line, by baseline.

    Only used here to count how often a gap is clear, so it can be simple:
    the precise line grouping that rows depend on lives in ``rows.py``.
    """
    if not blocks:
        return []

    height = _typical_height(blocks)
    tolerance = height * 0.5

    ordered = sorted(blocks, key=lambda b: b.baseline)
    lines: list[list[TextBlock]] = [[ordered[0]]]
    for block in ordered[1:]:
        if abs(block.baseline - lines[-1][-1].baseline) <= tolerance:
            lines[-1].append(block)
        else:
            lines.append([block])
    return lines


def _persistent_gaps(
    lines: list[list[TextBlock]], left: int, right: int,
) -> list[tuple[int, int]]:
    """Vertical strips left clear on most lines.

    Worked out per line and then intersected, rather than from a whole-page ink
    profile. A profile answers "is any ink here", which one long line ruins for
    every other; intersecting per-line gaps answers "is this clear *usually*",
    which is the question a column actually poses.
    """
    if not lines:
        return []

    blocks = [b for line in lines for b in line]
    minimum = _typical_height(blocks) * MIN_GAP_IN_HEIGHTS
    needed = max(1, int(len(lines) * MIN_GAP_PERSISTENCE))

    # A gap is a candidate if it is clear on one line; it survives if it is
    # clear on enough of them. Counting is done on a coarse grid of positions
    # so two gaps a pixel apart are the same gap.
    step = max(1, int(minimum / 4))
    positions = range(int(left), int(right), step)
    clear_count = {x: 0 for x in positions}

    for line in lines:
        spans = sorted((b.bbox.x, b.bbox.x1) for b in line)
        for x in positions:
            if not any(x0 <= x < x1 for x0, x1 in spans):
                clear_count[x] += 1

    usually_clear = [x for x in positions if clear_count[x] >= needed]
    return _wide_runs(usually_clear, step, minimum)


def _wide_runs(positions: list[int], step: int, minimum: float) -> list[tuple[int, int]]:
    """Consecutive clear positions, kept when the run is wide enough."""
    if not positions:
        return []

    runs: list[tuple[int, int]] = []
    start = previous = positions[0]
    for x in positions[1:]:
        if x - previous > step:
            runs.append((start, previous + step))
            start = x
        previous = x
    runs.append((start, previous + step))

    return [(x0, x1) for x0, x1 in runs if x1 - x0 >= minimum]


def _typical_height(blocks: list[TextBlock]) -> float:
    """Median block height — the document's own sense of scale.

    Median rather than mean: one tall heading or a stray full-page box would
    drag a mean upward and widen every threshold derived from it.
    """
    heights = [b.bbox.height for b in blocks if b.bbox.height > 0]
    return median(heights) if heights else 1.0
