"""
Telling a real table from a key-value list that happens to be drawn as a grid.

A form often rules a box around what is really a list of labelled fields. The
grid detector sees the rules and reports a table, but the content is not
tabular: a table's columns each carry their own kind of data, whereas this is
one label and one value per row, with a separator between them.

`ChallanReceipt.pdf` is the case this was written for. Six columns were
reported, and measured across the page they are:

    col0  label     ink present
    col1  spacer    empty
    col2  ":"       a sliver of ink
    col3  value     ink present
    col4  spacer    empty
    col5  spacer    empty

Three columns hold nothing at all and a fourth holds only punctuation. Calling
that a six-column table is wrong in a way that matters: the value of `PAN` ends
up in a cell whose column header is meaningless, and an operator reviewing it
sees "row 3, column 4" instead of "PAN".

Decided by counting **glyphs**, not text and not raw ink.

Raw ink share does not work: the drawn rules cross every column, so a spacer
column still measures 0.02-0.08 of the table's ink and never looks empty. What
separates them is whether a column contains *writing* — many small blobs — or
only the ruling that passes through it.

Counting glyph-shaped components also means the rule holds on a scan, where no
text exists until OCR has run.
"""

from __future__ import annotations

import cv2
import numpy as np

from piply_opdf.detectors.common import binarize, to_grayscale

__all__ = ["column_glyph_counts", "looks_like_key_value_grid"]

#: A component this much longer than it is thick is a ruled line, not a glyph.
_RULE_ASPECT = 8.0

#: Fewer glyphs per row than this and a column is carrying nothing of its own.
#:
#: Measured, not guessed. On `ChallanReceipt.pdf` the two real columns hold 201
#: and 281 glyphs over 18 rows while the spacers hold 0, 0, 0 and 4 — under a
#: quarter of a glyph per row. On the `DOC-20250901-WA0021.pdf` packing list the
#: *quietest* column still holds 31 glyphs over 25 rows, because it is a real
#: column that happens to be sparse.
#:
#: Judged against the column's own row count rather than against the busiest
#: column: a relative threshold called the packing list a key-value list, since
#: one description column dwarfs the rest without those being empty.
_MIN_GLYPHS_PER_ROW = 0.5

#: A separator column is narrow: a colon occupies a sliver of the table width.
_MAX_SEPARATOR_WIDTH_SHARE = 0.10

#: Below this many rows the shape is not established — two rows of two columns
#: is as likely to be a genuine small table.
_MIN_ROWS = 4


def column_glyph_counts(image: np.ndarray, table) -> list[int]:
    """Number of glyph-shaped components in each column, left to right.

    Long thin components are the table's own rules and are ignored, otherwise
    every column looks equally busy.
    """
    box = table.bbox
    region = image[box.y:box.y + box.height, box.x:box.x + box.width]
    if region.size == 0:
        return []

    binary = binarize(to_grayscale(region))
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)

    glyph_centres = []
    for i in range(1, count):
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        if w <= 0 or h <= 0:
            continue
        longest, shortest = max(w, h), min(w, h)
        if shortest == 0 or longest / shortest >= _RULE_ASPECT:
            continue                      # a ruled line, not writing
        if stats[i, cv2.CC_STAT_AREA] < 4:
            continue                      # speckle
        glyph_centres.append(centroids[i][0])

    counts = []
    for column in table.columns:
        cb = column.bbox
        x0 = cb.x - box.x
        x1 = x0 + cb.width
        counts.append(sum(1 for cx in glyph_centres if x0 <= cx < x1))
    return counts


def looks_like_key_value_grid(image: np.ndarray, table) -> bool:
    """True when a detected grid is really a list of labelled fields.

    The shape looked for, once columns carrying no writing are discarded:

        label | value              two columns
        label | : | value          three, the middle one narrow

    Anything else — three or more columns all carrying writing — is a table.
    """
    columns = list(table.columns)
    if len(columns) < 2 or len(table.rows) < _MIN_ROWS:
        return False

    counts = column_glyph_counts(image, table)
    if len(counts) != len(columns) or not any(counts):
        return False

    floor = len(table.rows) * _MIN_GLYPHS_PER_ROW
    carrying = [(col, n) for col, n in zip(columns, counts) if n >= floor]

    # Every column carrying writing means it is doing a table's job.
    if len(carrying) == len(columns):
        return False

    if len(carrying) == 2:
        return True

    if len(carrying) == 3:
        middle = carrying[1][0]
        return middle.bbox.width <= table.bbox.width * _MAX_SEPARATOR_WIDTH_SHARE

    return False
