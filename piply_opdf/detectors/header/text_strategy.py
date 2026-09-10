"""Header detection from the PDF text layer."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext

__all__ = ["TextHeaderStrategy"]


class TextHeaderStrategy(DetectionStrategy):
    """Reads headers straight from embedded text blocks.

    Preferred whenever the page has a text layer: the text is exact, so no OCR
    pass is needed for these regions.
    """

    name = "text-layer"
    priority = 100

    def __init__(self, top_margin_ratio: float = 0.12, max_gap_points: float = 20.0) -> None:
        self.top_margin_ratio = top_margin_ratio
        self.max_gap_points = max_gap_points

    def is_applicable(self, page: PageContext) -> bool:
        return page.has_text_layer

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        # Page height in points, recovered from the render scale.
        page_height_points = page.height / page.scale
        y_limit = page_height_points * self.top_margin_ratio

        headers: list[DetectedComponent] = []
        previous_bottom: float | None = None
        idx = 1

        for block in page.text_blocks:
            # Ordered top-down; the first block past the zone ends the search.
            if block.bbox.y1 > y_limit:
                break

            # A large vertical gap means the header band has ended.
            if previous_bottom is not None and (block.bbox.y - previous_bottom) > self.max_gap_points:
                break

            pixel_bbox = page.to_pixels(block.bbox)
            if not pixel_bbox.is_excluded_by(exclusions):
                headers.append(
                    DetectedComponent(
                        id=f"header_{page.page_number:03d}_{idx:03d}",
                        type=ComponentType.HEADER,
                        page=page.page_number,
                        bbox=pixel_bbox,
                        text=block.text,
                        confidence=0.85,
                        metadata={"strategy": self.name},
                    )
                )
                idx += 1

            previous_bottom = block.bbox.y1

        return headers
