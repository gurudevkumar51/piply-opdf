"""Footer detection from the rendered page, for scanned documents."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import find_text_blocks_in_zone

__all__ = ["CvFooterStrategy"]


class CvFooterStrategy(DetectionStrategy):
    """Finds footer blocks in the bottom band of the rendered page."""

    name = "cv-zone"
    priority = 10

    def __init__(self, bottom_margin_ratio: float = 0.88, max_gap_ratio: float = 0.25) -> None:
        self.bottom_margin_ratio = bottom_margin_ratio
        self.max_gap_ratio = max_gap_ratio

    def is_applicable(self, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        zone_top = int(page.height * self.bottom_margin_ratio)
        zone_height = page.height - zone_top
        zone = BBox(0, zone_top, page.width, zone_height)

        blocks = find_text_blocks_in_zone(
            page.image,
            zone,
            dpi=page.dpi,
            exclusions=exclusions,
            max_line_gap=int(zone_height * self.max_gap_ratio),
        )

        footers: list[DetectedComponent] = []
        idx = 1
        for block in blocks:
            footers.append(
                DetectedComponent(
                    id=f"footer_{page.page_number:03d}_{idx:03d}",
                    type=ComponentType.FOOTER,
                    page=page.page_number,
                    bbox=block,
                    text="",  # filled by the OCR phase
                    confidence=0.70,
                    metadata={"strategy": self.name, "needs_ocr": True},
                )
            )
            idx += 1

        return footers
