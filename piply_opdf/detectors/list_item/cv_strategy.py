"""List-item detection from the rendered page, for scanned documents.

A bullet cannot be read without OCR, but it has a distinctive *shape*: a small
ink run at the start of a line, separated from the body text by a clear gap,
appearing at a repeated left offset down the page. That signature is detectable
from geometry alone.
"""

from __future__ import annotations

from collections import Counter

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import binarize, find_text_lines, points_to_px, to_grayscale

__all__ = ["CvListItemStrategy"]


class CvListItemStrategy(DetectionStrategy):
    """Finds lines that begin with a small, detached marker glyph."""

    name = "cv-marker"
    priority = 10

    def __init__(
        self,
        *,
        max_marker_width_points: float = 14.0,
        min_marker_gap_ratio: float = 0.15,
        marker_width_tolerance: float = 0.45,
        top_margin_ratio: float = 0.12,
        bottom_margin_ratio: float = 0.88,
        min_repeats: int = 2,
    ) -> None:
        self.max_marker_width_points = max_marker_width_points
        #: Minimum gap after the marker, as a fraction of text height.
        self.min_marker_gap_ratio = min_marker_gap_ratio
        #: Allowed spread of marker widths within one list, as a fraction.
        self.marker_width_tolerance = marker_width_tolerance
        self.top_margin_ratio = top_margin_ratio
        self.bottom_margin_ratio = bottom_margin_ratio
        #: A single detached glyph is usually noise; a list has repeats at a
        #: shared indent. Requiring repetition keeps false positives down.
        self.min_repeats = min_repeats

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

        max_marker_px = points_to_px(self.max_marker_width_points, page.dpi)

        candidates: list[tuple[BBox, int, int]] = []  # (line, indent, marker width)
        for line in find_text_lines(binary, dpi=page.dpi):
            # Purely relative to text height: an absolute floor would be
            # proportionally huge on small formats and tiny on large ones.
            min_gap_px = max(2, int(line.height * self.min_marker_gap_ratio))
            width = self._leading_marker(binary, line, max_marker_px, min_gap_px)
            if width is not None:
                candidates.append((line, line.x, width))

        if len(candidates) < self.min_repeats:
            return []

        # Keep only the indent level that actually repeats — a real list.
        tolerance = max(1, points_to_px(4.0, page.dpi))
        buckets = Counter(indent // tolerance for _, indent, _ in candidates)
        dominant, count = buckets.most_common(1)[0]
        if count < self.min_repeats:
            return []

        at_indent = [c for c in candidates if c[1] // tolerance == dominant]

        # A real bullet repeats the *same glyph*, so marker widths cluster.
        # Prose lines that merely begin with a short word do not, which is what
        # keeps a relaxed gap threshold from generating false positives.
        widths = sorted(w for _, _, w in at_indent)
        median = widths[len(widths) // 2]
        consistent = [
            c for c in at_indent
            if abs(c[2] - median) <= max(1, median * self.marker_width_tolerance)
        ]
        if len(consistent) < self.min_repeats:
            return []

        items: list[DetectedComponent] = []
        index = 1
        for line, _indent, _width in consistent:
            items.append(
                DetectedComponent(
                    id=f"list_item_{page.page_number:03d}_{index:03d}",
                    type=ComponentType.LIST_ITEM,
                    page=page.page_number,
                    bbox=BBox(line.x, line.y + body_top, line.width, line.height),
                    text="",
                    confidence=0.65,
                    index=index,
                    metadata={"strategy": self.name, "needs_ocr": True},
                )
            )
            index += 1

        return items

    def _leading_marker(
        self,
        binary,
        line: BBox,
        max_marker_px: int,
        min_gap_px: int,
    ) -> int | None:
        """Return the width of the leading marker glyph, or None if absent.

        A marker is a narrow ink run at the start of the line, followed by
        whitespace, followed by the item text.
        """
        strip = binary[line.y:line.y1, line.x:line.x1]
        if strip.size == 0:
            return None

        column_ink = (strip > 0).sum(axis=0)

        # find_text_lines returns the *dilated* extent, so the box is padded
        # with blank columns. Skip to where ink actually starts.
        ink_start = 0
        while ink_start < len(column_ink) and column_ink[ink_start] == 0:
            ink_start += 1
        if ink_start >= len(column_ink):
            return None

        marker_end = ink_start
        while marker_end < len(column_ink) and column_ink[marker_end] > 0:
            marker_end += 1

        marker_width = marker_end - ink_start
        if marker_width == 0 or marker_width > max_marker_px:
            return None

        # A clear gap must follow, then more ink (the item body).
        gap_end = marker_end
        while gap_end < len(column_ink) and column_ink[gap_end] == 0:
            gap_end += 1
        if (gap_end - marker_end) < min_gap_px or gap_end >= len(column_ink):
            return None

        return marker_width
