"""
Structure for tables nobody drew lines on.

The failure being prevented is specific and it is the reason this module
exists. Clustering text by horizontal whitespace turns a wrapped description
into extra rows, and every column after it is then read against the wrong row —
a statement claims payments happened on dates they did not.

So the tests are built around documents that wrap, documents where a row has no
value in the first column, and the same document measured at three
resolutions.
"""

from __future__ import annotations

import pytest

from piply_opdf.core.types import BBox
from piply_opdf.structure import (
    BorderlessGrid, TextBlock, build_grid, find_columns, find_rows, group_lines,
)

LINE_HEIGHT = 20
LINE_GAP = 30            # within a wrapped description
ROW_GAP = 46             # between rows


def _line(y: int, cells: list[tuple[int, str]]) -> list[TextBlock]:
    """One physical line: (x, text) pairs at a common baseline."""
    return [TextBlock(BBox(x, y, max(1, len(text) * 9), LINE_HEIGHT), text)
            for x, text in cells]


def _statement() -> list[TextBlock]:
    """The document from the plan: a wrapped description, and a total row
    with no date."""
    blocks: list[TextBlock] = []
    blocks += _line(100, [(100, "Date"), (300, "Description"), (900, "Amount")])
    blocks += _line(146, [(100, "04/28"), (300, "Wire transfer received from"), (900, "1200")])
    blocks += _line(176, [(300, "Acme Industries Limited")])
    blocks += _line(206, [(300, "reference 88213")])
    blocks += _line(252, [(100, "05/01"), (300, "Payment"), (900, "500")])
    blocks += _line(298, [(300, "Closing balance"), (900, "700")])
    return blocks


def _texts(grid: BorderlessGrid) -> list[list[str]]:
    return [[grid.cell(r.index, c.index).text for c in grid.columns]
            for r in grid.rows]


def _rescaled(blocks: list[TextBlock], factor: float) -> list[TextBlock]:
    return [
        TextBlock(
            BBox(int(b.bbox.x / factor), int(b.bbox.y / factor),
                 max(1, int(b.bbox.width / factor)),
                 max(1, int(b.bbox.height / factor))),
            b.text,
        )
        for b in blocks
    ]


# ── the failure this exists to prevent ───────────────────────────────────────

def test_a_wrapped_description_does_not_become_extra_rows():
    """The whole point. Three physical lines, one logical row."""
    grid = build_grid(_statement())

    assert grid.shape == (4, 3), grid.summary()
    assert _texts(grid) == [
        ["Date", "Description", "Amount"],
        ["04/28",
         "Wire transfer received from Acme Industries Limited reference 88213",
         "1200"],
        ["05/01", "Payment", "500"],
        ["", "Closing balance", "700"],
    ]


def test_values_stay_with_the_row_they_belong_to():
    """The consequence of getting it wrong: a statement that claims payments
    happened on dates they did not."""
    grid = build_grid(_statement())

    for row in grid.rows:
        date = grid.cell(row.index, 0).text
        amount = grid.cell(row.index, 2).text
        if date == "04/28":
            assert amount == "1200"
        if date == "05/01":
            assert amount == "500"


def test_the_wrap_is_recorded_as_one_row_of_several_lines():
    grid = build_grid(_statement())
    wrapped = [r for r in grid.rows if r.wrapped]

    assert len(wrapped) == 1
    assert wrapped[0].lines == 3


# ── no column is the mandatory anchor ────────────────────────────────────────

def test_a_row_with_no_value_in_the_first_column_is_still_a_row():
    """A total line fills two cells of three. Anchoring rows on "the date
    column has a value" would lose it entirely."""
    grid = build_grid(_statement())
    last = grid.rows[-1]

    assert grid.cell(last.index, 0).is_empty
    assert grid.cell(last.index, 1).text == "Closing balance"
    assert grid.cell(last.index, 2).text == "700"


def test_a_row_with_a_value_only_in_the_last_column_is_still_a_row():
    blocks = _statement()
    blocks += _line(344, [(900, "0")])

    grid = build_grid(blocks)

    assert grid.rows[-1].index == 4
    assert grid.cell(4, 2).text == "0"


def test_empty_cells_are_kept_rather_than_skipped():
    """Dropping them would shift every later value into the wrong column —
    the same misalignment, arriving by a different route."""
    grid = build_grid(_statement())

    assert len(grid.cells) == len(grid.rows) * len(grid.columns)


# ── scale-free ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("factor", [0.5, 1.0, 2.0])
def test_the_same_table_at_any_resolution_gives_the_same_structure(factor):
    """Every threshold is in text-heights or relative to the document's own
    spacing, so a scan at 150 DPI and one at 600 read alike."""
    grid = build_grid(_rescaled(_statement(), factor))

    assert grid.shape == (4, 3)
    assert sum(1 for r in grid.rows if r.wrapped) == 1


def test_a_band_holding_no_text_is_not_reported_as_a_column():
    """Integer rounding at a table's right edge can leave a sliver wide enough
    to pass a width test. Asking whether anything is in it is exact."""
    grid = build_grid(_rescaled(_statement(), 2.0))

    assert all(
        any(not grid.cell(r.index, c.index).is_empty for r in grid.rows)
        for c in grid.columns
    )


# ── columns ──────────────────────────────────────────────────────────────────

def test_a_column_runs_to_where_the_next_one_starts():
    """Not to where its own text usually stops. Ragged right margins are clear
    on most lines too, and ending a band at its gap's start cuts the column off
    at its narrowest line."""
    columns = find_columns(_statement())

    assert len(columns) == 3
    assert columns[0].x1 == columns[1].x0
    assert columns[1].x1 == columns[2].x0
    assert columns[1].width > 500, "the description column holds its longest line"


def test_prose_is_one_column_not_a_one_column_table():
    """A paragraph has no persistent gap. Reporting one would turn every block
    of text on the page into a table."""
    prose = []
    for index in range(6):
        prose += _line(100 + index * 30, [(100, "the quick brown fox jumps over the lazy dog")])

    assert len(find_columns(prose)) == 1


def test_one_lucky_gap_does_not_make_a_column():
    """A single short line leaves a gap. Twenty lines leaving the same gap is a
    column; one is a coincidence."""
    blocks = []
    for index in range(8):
        text = "short" if index == 3 else "a much longer line of running text here"
        blocks += _line(100 + index * 30, [(100, text)])

    assert len(find_columns(blocks)) == 1


def test_nothing_in_produces_nothing_out():
    assert find_columns([]) == []
    assert find_rows([], []) == []
    assert build_grid([]).shape == (0, 0)


# ── lines ────────────────────────────────────────────────────────────────────

def test_lines_are_clustered_on_baselines_not_centres():
    """Characters sit on a common baseline while their heights vary, so a line
    mixing tall and short words has one baseline and several centres."""
    tall = TextBlock(BBox(100, 80, 60, 40), "TALL")        # bottom 120
    short = TextBlock(BBox(200, 104, 60, 16), "small")     # bottom 120

    lines = group_lines([tall, short])

    assert len(lines) == 1, "same baseline, different centres"


# ── row confidence ───────────────────────────────────────────────────────────

def test_every_row_carries_the_evidence_for_its_boundary():
    """A split nobody can argue with is one that gets believed or ignored."""
    grid = build_grid(_statement())

    for row in grid.rows:
        assert set(row.evidence) == {"spread", "gap", "indent"}
        assert 0.0 <= row.confidence <= 1.0


def test_a_full_width_row_is_more_confident_than_a_sparse_one():
    grid = build_grid(_statement())

    full = next(r for r in grid.rows if grid.cell(r.index, 0).text == "05/01")
    sparse = grid.rows[-1]                       # the closing balance

    assert full.confidence > sparse.confidence


def test_the_spread_signal_names_no_particular_column():
    """The direct expression of "no single column may be the mandatory
    anchor" — two rows filling the same number of columns score the same
    however different the columns are."""
    from piply_opdf.structure.rows import _spread_evidence

    columns = find_columns(_statement())
    first_two = _line(400, [(100, "a"), (300, "b")])
    last_two = _line(400, [(300, "b"), (900, "c")])

    assert (_spread_evidence(first_two, columns)
            == _spread_evidence(last_two, columns))
