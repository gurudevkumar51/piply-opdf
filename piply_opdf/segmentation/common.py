"""
Shared splitting primitives for segmenters.

Two ways to cut a region into lines and words:

* **text layer** — exact word boxes from the PDF, when the page has them;
* **CV** — connected-component analysis on the rendered crop, for scans.

Both return boxes in **page pixel coordinates**, so callers never deal with the
crop-local frame.
"""

from __future__ import annotations

import cv2

from piply_opdf.core.types import BBox, PageContext
from piply_opdf.detectors.common import binarize, points_to_px, to_grayscale
from piply_opdf.detectors.text_layer import Word, extract_words, group_into_lines

__all__ = [
    "words_from_text_layer",
    "lines_from_text_layer",
    "lines_from_image",
    "words_from_image",
]


def words_from_text_layer(region: BBox, page: PageContext) -> list[tuple[BBox, str]]:
    """Word boxes (in page pixels) whose centre falls inside *region*."""
    inside: list[tuple[BBox, str]] = []
    for word in extract_words(page):
        pixel_bbox = page.to_pixels(word.bbox)
        cx, cy = pixel_bbox.center
        if region.contains_point(cx, cy):
            inside.append((pixel_bbox, word.text))
    inside.sort(key=lambda item: (item[0].y, item[0].x))
    return inside


def lines_from_text_layer(region: BBox, page: PageContext) -> list[tuple[BBox, str, list[Word]]]:
    """Visual lines (in page pixels) whose centre falls inside *region*."""
    result: list[tuple[BBox, str, list[Word]]] = []
    for line in group_into_lines(extract_words(page)):
        pixel_bbox = page.to_pixels(line.bbox)
        cx, cy = pixel_bbox.center
        if region.contains_point(cx, cy):
            result.append((pixel_bbox, line.text, list(line.words)))
    result.sort(key=lambda item: (item[0].y, item[0].x))
    return result


def _crop_binary(region: BBox, page: PageContext):
    x0 = max(0, region.x)
    y0 = max(0, region.y)
    x1 = min(page.width, region.x1)
    y1 = min(page.height, region.y1)
    if x1 <= x0 or y1 <= y0:
        return None, 0, 0
    crop = page.image[y0:y1, x0:x1]
    return binarize(to_grayscale(crop)), x0, y0


def lines_from_image(region: BBox, page: PageContext) -> list[BBox]:
    """Text lines inside *region*, found by horizontal ink projection.

    Projection is used rather than contours because within an already-isolated
    region the lines are cleanly separated in y, and projection will not split
    a line into fragments the way per-glyph contours can.
    """
    binary, ox, oy = _crop_binary(region, page)
    if binary is None:
        return []

    row_ink = (binary > 0).sum(axis=1)
    min_gap = max(1, points_to_px(1.0, page.dpi))

    lines: list[BBox] = []
    start: int | None = None
    blank = 0

    for y, value in enumerate(row_ink):
        if value > 0:
            if start is None:
                start = y
            blank = 0
        elif start is not None:
            blank += 1
            if blank >= min_gap:
                lines.append(BBox(ox, oy + start, binary.shape[1], (y - blank) - start + 1))
                start = None
                blank = 0

    if start is not None:
        lines.append(BBox(ox, oy + start, binary.shape[1], len(row_ink) - start))

    # Trim each line horizontally to its actual ink extent.
    trimmed: list[BBox] = []
    min_height = max(2, points_to_px(2.0, page.dpi))
    for line in lines:
        if line.height < min_height:
            continue
        strip = binary[line.y - oy: line.y - oy + line.height, :]
        col_ink = (strip > 0).sum(axis=0)
        nonzero = col_ink.nonzero()[0]
        if nonzero.size == 0:
            continue
        trimmed.append(
            BBox(ox + int(nonzero[0]), line.y, int(nonzero[-1] - nonzero[0]) + 1, line.height)
        )
    return trimmed


def words_from_image(region: BBox, page: PageContext) -> list[BBox]:
    """Word boxes inside *region*, split on inter-word whitespace.

    Glyphs are merged horizontally by a kernel sized to typical inter-letter
    spacing, so letters join into words but words stay apart. The kernel is
    derived from DPI, so this holds at any render resolution.
    """
    boxes: list[BBox] = []

    for line in lines_from_image(region, page):
        binary, ox, oy = _crop_binary(line, page)
        if binary is None:
            continue

        # Inter-letter and inter-word spacing both scale with font size, so the
        # bridging kernel is derived from the line's own height rather than a
        # fixed measurement. Roughly: letter gaps sit near 0.1x line height,
        # word gaps near 0.3x, so ~0.22x separates them at any font size.
        kernel_w = max(2, int(line.height * 0.22))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, 1))
        merged = cv2.dilate(binary, kernel, iterations=1)

        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        min_w = max(1, int(line.height * 0.08))

        line_boxes = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            if w < min_w:
                continue
            line_boxes.append(BBox(ox + x, oy + y, w, h))

        line_boxes.sort(key=lambda b: b.x)
        boxes.extend(line_boxes)

    return boxes
