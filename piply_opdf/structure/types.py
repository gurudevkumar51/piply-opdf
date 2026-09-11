"""
What a borderless table is made of, before anything has decided its shape.

The input is deliberately poor: boxes with text in them. No rules, no colour,
no font metadata — because on a scan there is none of that, and a structure
recogniser that needs a text layer is one that works on the documents where
this problem is already solved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from piply_opdf.core.types import BBox

__all__ = ["TextBlock", "Column", "Row", "Cell", "BorderlessGrid"]


@dataclass(frozen=True, slots=True)
class TextBlock:
    """One word, or a short run of text, with a box around it."""

    bbox: BBox
    text: str = ""

    @property
    def baseline(self) -> int:
        """The bottom edge.

        Used instead of the centre throughout, because characters sit on a
        common baseline while their heights vary — a line of small caps and a
        line with a descender have different centres and the same baseline.
        Clustering on centres mixes lines that are typographically distinct and
        splits lines that are not.
        """
        return self.bbox.y1


@dataclass(frozen=True, slots=True)
class Column:
    """A vertical band the table's values line up in."""

    index: int
    x0: int
    x1: int

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    def holds(self, block: TextBlock) -> bool:
        """Whether a block belongs to this column.

        By the block's *left* edge rather than its centre: a long value that
        overruns into the next column's space still starts where it was
        written, and a wrapped description should stay with its label rather
        than drift right as it gets longer.
        """
        return self.x0 <= block.bbox.x < self.x1


@dataclass(frozen=True, slots=True)
class Cell:
    """One column's worth of one row."""

    row: int
    column: int
    bbox: BBox
    blocks: tuple[TextBlock, ...] = ()

    @property
    def text(self) -> str:
        return " ".join(b.text for b in self.blocks if b.text).strip()

    @property
    def is_empty(self) -> bool:
        return not self.blocks


@dataclass(frozen=True, slots=True)
class Row:
    """One logical row — which may occupy several physical lines."""

    index: int
    bbox: BBox
    blocks: tuple[TextBlock, ...] = ()
    #: How strongly this is a row *boundary*, from the evidence below. A
    #: ranking, like confidence elsewhere: it says which row divisions to doubt
    #: first, not how often they are right.
    confidence: float = 0.0
    #: Why. Kept so a wrong split can be argued with rather than guessed at.
    evidence: dict[str, float] = field(default_factory=dict)
    #: How many physical lines were folded into this row. More than one means
    #: continuation analysis absorbed a wrap.
    lines: int = 1

    @property
    def wrapped(self) -> bool:
        return self.lines > 1


@dataclass(frozen=True, slots=True)
class BorderlessGrid:
    """The assembled table."""

    columns: tuple[Column, ...] = ()
    rows: tuple[Row, ...] = ()
    cells: tuple[Cell, ...] = ()

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.rows), len(self.columns)

    def cell(self, row: int, column: int) -> Cell | None:
        for candidate in self.cells:
            if candidate.row == row and candidate.column == column:
                return candidate
        return None

    def summary(self) -> str:
        wrapped = sum(1 for r in self.rows if r.wrapped)
        doubtful = sum(1 for r in self.rows if r.confidence < 0.5)
        return (f"{len(self.rows)} rows x {len(self.columns)} columns, "
                f"{wrapped} wrapped, {doubtful} doubtful")
