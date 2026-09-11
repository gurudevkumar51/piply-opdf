"""
Structure for tables nobody drew lines on.

A bank statement, a remittance advice, an invoice: few or no ruled lines, and
the whole value in the relationship between columns. The plan calls this the
single biggest structural gap for the documents this system targets, and the
reason is that the obvious approach — persistent vertical gaps, then horizontal
ones, then cells at the intersections — fails on exactly these pages.

::

    Date       Description                        Amount
               continuation of long description
               another continuation
    05/01      Payment                            500

Lines two and three are not new rows. They are one row, wrapped. A detector
driven by horizontal whitespace reports four rows where there are two, and
every column after `Description` is then read against the wrong row.

So the pipeline is::

    text blocks
        -> candidate columns        persistent vertical gaps
        -> baseline clustering      which blocks share a writing line
        -> continuation analysis    a new row, or a wrap of the last?
        -> row confidence           how strongly is this a boundary
        -> cells

**This is Piply's speciality, not the baseline model's.** A trained layout
model reports one `table` region; assembling its rows and cells correctly on a
borderless statement is the specialised work that stays here.

Nothing in it needs a text layer. The input is boxes with optional text, so the
same code serves a digital PDF and a scan where OCR supplies the boxes — which
matters, because a structure recogniser that needs a text layer only works on
the documents where the problem is already solved.
"""

from __future__ import annotations

from piply_opdf.structure.columns import (
    MIN_GAP_IN_HEIGHTS, MIN_GAP_PERSISTENCE, find_columns,
)
from piply_opdf.structure.rows import (
    DOUBTFUL_BELOW, ROW_EVIDENCE_WEIGHTS, find_rows, group_lines,
)
from piply_opdf.structure.types import (
    BorderlessGrid, Cell, Column, Row, TextBlock,
)

__all__ = [
    "build_grid",
    "TextBlock",
    "Column",
    "Row",
    "Cell",
    "BorderlessGrid",
    "find_columns",
    "find_rows",
    "group_lines",
    "ROW_EVIDENCE_WEIGHTS",
    "MIN_GAP_IN_HEIGHTS",
    "MIN_GAP_PERSISTENCE",
    "DOUBTFUL_BELOW",
]


def build_grid(blocks: list[TextBlock]) -> BorderlessGrid:
    """Assemble a borderless table from text boxes.

    Columns first, because rows are decided partly by *how many columns* a line
    touches — the anchor-free test — so the columns have to exist before that
    question can be asked.

    **Give it one table's blocks, not a whole page.** Run on every word of an
    invoice it will dutifully find columns in the delivery address, because
    that is what it was asked. Measured on `OD330106520353075100.pdf`: the
    whole page yields 33 rows by 6 columns, with the address split across
    columns that exist only because address lines happen to break in similar
    places. Scoping the region is the caller's job, and the division of labour
    the plan describes — a layout model says *here is a table*, this says what
    its rows and cells are.
    """
    from piply_opdf.core.types import BBox

    if not blocks:
        return BorderlessGrid()

    columns = find_columns(blocks)
    rows = find_rows(blocks, columns)

    cells: list[Cell] = []
    for row in rows:
        for column in columns:
            held = tuple(b for b in row.blocks if column.holds(b))
            # Empty cells are kept, not skipped. A statement row with no date
            # has a date cell that is empty, and dropping it would shift every
            # value after it into the wrong column — the same misalignment
            # this module exists to prevent, arriving by a different route.
            box = _bounds(held) if held else BBox(column.x0, row.bbox.y,
                                                  column.width, row.bbox.height)
            cells.append(Cell(row=row.index, column=column.index,
                              bbox=box, blocks=held))

    return BorderlessGrid(columns=tuple(columns), rows=tuple(rows),
                          cells=tuple(cells))


def _bounds(blocks: tuple[TextBlock, ...]):
    from piply_opdf.core.types import BBox

    x0 = min(b.bbox.x for b in blocks)
    y0 = min(b.bbox.y for b in blocks)
    x1 = max(b.bbox.x1 for b in blocks)
    y1 = max(b.bbox.y1 for b in blocks)
    return BBox(x0, y0, x1 - x0, y1 - y0)
