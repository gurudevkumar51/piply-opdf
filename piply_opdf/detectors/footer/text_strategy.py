"""Footer detection from the PDF text layer."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext

__all__ = ["TextFooterStrategy"]


class TextFooterStrategy(DetectionStrategy):
    """Reads footers straight from embedded text blocks, scanning bottom-up."""

    name = "text-layer"
    priority = 100

    def __init__(self, bottom_margin_ratio: float = 0.88, max_gap_points: float = 20.0) -> None:
        #: Fraction of page height below which a block counts as footer.
        self.bottom_margin_ratio = bottom_margin_ratio
        self.max_gap_points = max_gap_points

    def is_applicable(self, page: PageContext) -> bool:
        return page.has_text_layer

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        page_height_points = page.height / page.scale
        y_limit = page_height_points * self.bottom_margin_ratio

        # Walk upwards from the bottom of the page.
        blocks = sorted(page.text_blocks, key=lambda b: b.bbox.y, reverse=True)

        collected: list[tuple[BBox, str]] = []
        previous_top: float | None = None

        for block in blocks:
            if block.bbox.y < y_limit:
                break

            if previous_top is not None and (previous_top - block.bbox.y1) > self.max_gap_points:
                break

            pixel_bbox = page.to_pixels(block.bbox)
            if not pixel_bbox.is_excluded_by(exclusions):
                collected.append((pixel_bbox, block.text))

            previous_top = block.bbox.y

        # Restore reading order (top-down) before numbering.
        collected.reverse()

        return [
            DetectedComponent(
                id=f"footer_{page.page_number:03d}_{idx:03d}",
                type=ComponentType.FOOTER,
                page=page.page_number,
                bbox=bbox,
                text=text,
                confidence=0.85,
                metadata={"strategy": self.name},
            )
            for idx, (bbox, text) in enumerate(collected, start=1)
        ]
