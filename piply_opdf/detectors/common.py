"""
Shared computer-vision helpers for detectors that must work without a PDF text
layer (scanned documents and image inputs).

These functions locate *regions* only — they never call OCR. Text is filled in
later by the OCR phase, exactly as it already is for table cells. That keeps
detection free of any OCR dependency and means a scanned page flows through the
same extract → OCR → knowledge path as a digital one.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from piply_opdf.core.types import BBox

logger = logging.getLogger(__name__)

__all__ = [
    "to_grayscale",
    "binarize",
    "points_to_px",
    "find_text_lines",
    "group_lines_into_blocks",
    "find_text_blocks_in_zone",
    "grid_masks",
    "find_frames",
    "count_cells",
]


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """Return a single-channel view of *image*, whatever its channel count."""
    if image.ndim == 2:
        return image
    if image.shape[2] == 4:
        return cv2.cvtColor(image, cv2.COLOR_BGRA2GRAY)
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def binarize(gray: np.ndarray) -> np.ndarray:
    """Otsu inverse-binary threshold: text becomes white on black.

    Otsu is used rather than a fixed threshold because scan brightness varies
    widely; the inverse polarity is what the morphology below expects.
    """
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return binary


#: Minimum glyph height that still counts as text, in typographic points.
#: ~3pt is below any readable body text, so anything smaller is speckle noise.
MIN_TEXT_HEIGHT_PT = 3.0

#: Minimum run width that still counts as a text line, in points (~0.2 inch).
MIN_TEXT_WIDTH_PT = 14.0

#: Maximum stroke height for something to be treated as a printed rule, in points.
MAX_RULE_HEIGHT_PT = 1.5


def points_to_px(points: float, dpi: int) -> int:
    """Convert a typographic measurement to pixels at *dpi*."""
    return max(1, int(round(points * dpi / 72.0)))


def find_text_lines(
    binary: np.ndarray,
    *,
    dpi: int = 300,
    min_width: int | None = None,
    min_height: int | None = None,
    dilate_ratio: float = 0.02,
) -> list[BBox]:
    """Locate individual text lines inside a binarised region.

    Characters are merged into lines with a wide, flat dilation kernel, then
    recovered as contour bounding boxes.

    All size thresholds are derived from *dpi* rather than being fixed pixel
    counts, so the same logic holds whether a page is rendered at 150, 300 or
    600 DPI, and regardless of page dimensions.

    Parameters
    ----------
    dilate_ratio:
        Kernel width as a fraction of region width. Larger values bridge wider
        inter-word gaps but risk merging separate columns.
    min_width, min_height:
        Explicit pixel overrides. When omitted they are computed from *dpi*.
    """
    if binary.size == 0:
        return []

    h, w = binary.shape[:2]

    if min_height is None:
        min_height = points_to_px(MIN_TEXT_HEIGHT_PT, dpi)
    if min_width is None:
        min_width = points_to_px(MIN_TEXT_WIDTH_PT, dpi)
    max_rule_height = points_to_px(MAX_RULE_HEIGHT_PT, dpi)

    # Kernel height scales with DPI too, so vertically adjacent glyph parts
    # (dots on i/j, accents) merge into their line at any resolution.
    kernel_w = max(points_to_px(2.0, dpi), int(w * dilate_ratio))
    kernel_h = max(1, points_to_px(0.8, dpi))
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_w, kernel_h))
    merged = cv2.dilate(binary, kernel, iterations=1)

    contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    lines: list[BBox] = []
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        if cw < min_width or ch < min_height:
            continue
        # Reject long thin runs: printed rules and table borders, not text.
        if ch <= max_rule_height and cw > w * 0.8:
            continue
        lines.append(BBox(x, y, cw, ch))

    lines.sort(key=lambda b: (b.y, b.x))
    return lines


def group_lines_into_blocks(lines: list[BBox], max_gap: int) -> list[BBox]:
    """Merge vertically adjacent lines into blocks.

    A gap larger than *max_gap* starts a new block — the raster equivalent of
    the "large vertical gap ends the header" rule the text strategies use.
    """
    if not lines:
        return []

    blocks: list[BBox] = []
    current = [lines[0]]

    for line in lines[1:]:
        previous_bottom = max(b.y1 for b in current)
        if line.y - previous_bottom > max_gap:
            blocks.append(_union(current))
            current = [line]
        else:
            current.append(line)

    blocks.append(_union(current))
    return blocks


def _union(boxes: list[BBox]) -> BBox:
    x0 = min(b.x for b in boxes)
    y0 = min(b.y for b in boxes)
    x1 = max(b.x1 for b in boxes)
    y1 = max(b.y1 for b in boxes)
    return BBox.from_xyxy(x0, y0, x1, y1)


def find_text_blocks_in_zone(
    image: np.ndarray,
    zone: BBox,
    *,
    dpi: int = 300,
    exclusions: list[BBox] | None = None,
    max_line_gap: int | None = None,
    min_width: int | None = None,
    min_height: int | None = None,
) -> list[BBox]:
    """Find text blocks inside *zone*, returned in **full-page** coordinates.

    The zone is cropped, analysed independently (so thresholding adapts to the
    local brightness of a header or footer strip), then results are translated
    back to page coordinates.

    *exclusions* (already-claimed regions such as detected tables) are erased
    from the binary image **before** lines are grouped. Masking rather than
    filtering afterwards matters: a header sitting directly above a table would
    otherwise be merged into one block with the table's first rows, and
    discarding that block would lose the header along with it.
    """
    page_h, page_w = image.shape[:2]

    x0 = max(0, zone.x)
    y0 = max(0, zone.y)
    x1 = min(page_w, zone.x1)
    y1 = min(page_h, zone.y1)
    if x1 <= x0 or y1 <= y0:
        return []

    crop = image[y0:y1, x0:x1]
    binary = binarize(to_grayscale(crop))

    for ex in exclusions or []:
        # Translate the exclusion into crop-local coordinates and clamp.
        ex_x0 = max(0, ex.x - x0)
        ex_y0 = max(0, ex.y - y0)
        ex_x1 = min(x1 - x0, ex.x1 - x0)
        ex_y1 = min(y1 - y0, ex.y1 - y0)
        if ex_x1 > ex_x0 and ex_y1 > ex_y0:
            binary[ex_y0:ex_y1, ex_x0:ex_x1] = 0

    # Default gap ≈ one line of leading; ends a block at a paragraph break.
    if max_line_gap is None:
        max_line_gap = max(points_to_px(6.0, dpi), int(crop.shape[0] * 0.25))

    lines = find_text_lines(
        binary, dpi=dpi, min_width=min_width, min_height=min_height,
    )
    blocks = group_lines_into_blocks(lines, max_line_gap)

    return [BBox(b.x + x0, b.y + y0, b.width, b.height) for b in blocks]


# ── Frames and cell counting ──────────────────────────────────────────────────
#
# A closed rectangular frame is either a table or a panel, and the only thing
# that separates them is how many cells sit inside. A one-cell table and a boxed
# paragraph are pixel-identical, so the boundary is set by definition:
#
#     2 or more cells  ->  TABLE
#     exactly 1 cell   ->  PANEL
#
# See docs/components.md, Rule 1.

#: Minimum frame side, as a fraction of page width. Smaller closed shapes are
#: glyph parts (O, D, 8) or noise, not layout.
MIN_FRAME_SIDE_RATIO = 0.06

#: How much of the interior an internal rule must span to count as a divider.
#: A short rule is an underline or a strike-through, not a cell boundary.
MIN_DIVIDER_SPAN = 0.70

#: Thickest a divider may be, as a fraction of the interior. A printed rule is
#: hairline-thin. Without this cap, dense content — a photograph, a solid block
#: of colour — spans the full width on every row and reads as a divider, so a
#: framed picture would be mistaken for a table.
MAX_DIVIDER_THICKNESS = 0.03


def grid_masks(binary: np.ndarray, *, min_line_ratio: float = 0.025) -> tuple[np.ndarray, np.ndarray]:
    """Return (horizontal, vertical) rule masks for a binarised region.

    Line length thresholds scale with the region, so the same call works on a
    full page and on the inside of a small box.
    """
    height, width = binary.shape[:2]

    h_len = max(8, int(width * min_line_ratio))
    v_len = max(8, int(height * min_line_ratio))

    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
    )
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
    )
    return horizontal, vertical


def find_frames(image: np.ndarray, *, min_side_ratio: float = MIN_FRAME_SIDE_RATIO) -> list[BBox]:
    """Find closed rectangular frames — boxes drawn around content.

    Detects the *outline*, not the content: horizontal and vertical rules are
    isolated, combined, and any resulting shape that approximates a four-sided
    axis-aligned rectangle of reasonable size is returned.
    """
    if image is None or image.size == 0:
        return []

    page_height, page_width = image.shape[:2]
    binary = binarize(to_grayscale(image))

    horizontal, vertical = grid_masks(binary)
    grid = cv2.bitwise_or(horizontal, vertical)

    # Close small breaks so a frame with a gap at a corner still reads as closed.
    grid = cv2.morphologyEx(
        grid, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    )

    contours, _ = cv2.findContours(grid, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    min_width = int(page_width * min_side_ratio)
    min_height = int(page_height * min_side_ratio)

    frames: list[BBox] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < min_width or h < min_height:
            continue

        # The contour must actually be rectangular, not an L-shape or a blob:
        # its area should nearly fill its bounding box.
        if cv2.contourArea(contour) < 0.55 * (w * h):
            # A frame is hollow, so contourArea of the *outline* is small.
            # Compare the filled shape instead.
            filled = np.zeros((h, w), np.uint8)
            cv2.drawContours(filled, [contour - [x, y]], -1, 255, cv2.FILLED)
            if (filled > 0).sum() < 0.55 * (w * h):
                continue

        # Four corners after simplification means a rectangle.
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) < 4 or len(approx) > 6:
            continue

        frames.append(BBox(x, y, w, h))

    frames.sort(key=lambda b: (b.y, b.x))
    return frames


def count_cells(image: np.ndarray, frame: BBox) -> int:
    """Count cells inside *frame*.

    Only rules that span most of the interior divide it — a short line is an
    underline or a strike-through, not a cell boundary. Cells are then simply
    ``(horizontal dividers + 1) x (vertical dividers + 1)``.

    Returns 1 for an undivided frame, which by Rule 1 makes it a panel.
    """
    page_height, page_width = image.shape[:2]

    # Step inside the border so the frame's own edges are not counted.
    inset = max(3, int(min(frame.width, frame.height) * 0.04))
    x0 = max(0, frame.x + inset)
    y0 = max(0, frame.y + inset)
    x1 = min(page_width, frame.x1 - inset)
    y1 = min(page_height, frame.y1 - inset)
    if x1 - x0 < 10 or y1 - y0 < 10:
        return 1

    interior = binarize(to_grayscale(image[y0:y1, x0:x1]))
    inner_height, inner_width = interior.shape[:2]

    horizontal, vertical = grid_masks(interior)

    # A divider is a row/column of the mask inked across most of the span.
    h_rows = (horizontal > 0).sum(axis=1) >= inner_width * MIN_DIVIDER_SPAN
    v_cols = (vertical > 0).sum(axis=0) >= inner_height * MIN_DIVIDER_SPAN

    h_dividers = _count_runs(h_rows, max(4, int(inner_height * MAX_DIVIDER_THICKNESS)))
    v_dividers = _count_runs(v_cols, max(4, int(inner_width * MAX_DIVIDER_THICKNESS)))

    return (h_dividers + 1) * (v_dividers + 1)


def _count_runs(flags: np.ndarray, max_thickness: int) -> int:
    """Count separate True runs, ignoring any thicker than *max_thickness*.

    One rule counts once however many pixels thick it is. A run far thicker
    than a rule is filled content, not a divider, so it is not counted at all.
    """
    runs = 0
    length = 0

    for value in flags:
        if value:
            length += 1
        else:
            if 0 < length <= max_thickness:
                runs += 1
            length = 0

    if 0 < length <= max_thickness:
        runs += 1

    return runs
