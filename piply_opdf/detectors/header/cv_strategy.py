"""Header detection from the rendered page, for scanned documents.

Used when the page carries no extractable text. Locates header *regions*
only — their text is recognised later by the OCR phase, the same path table
cells already take.
"""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import find_text_blocks_in_zone

__all__ = ["CvHeaderStrategy"]


class CvHeaderStrategy(DetectionStrategy):
    """Finds header blocks in the top band of the rendered page."""

    name = "cv-zone"
    priority = 10  # below the text strategy: only used when that declines

    def __init__(self, top_margin_ratio: float = 0.12, max_gap_ratio: float = 0.25) -> None:
        self.top_margin_ratio = top_margin_ratio
        self.max_gap_ratio = max_gap_ratio

    def is_applicable(self, page: PageContext) -> bool:
        # The raster always exists, so this is the universal fallback.
        return page.image is not None and page.image.size > 0

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        zone_height = int(page.height * self.top_margin_ratio)
        zone = BBox(0, 0, page.width, zone_height)

        blocks = find_text_blocks_in_zone(
            page.image,
            zone,
            dpi=page.dpi,
            exclusions=exclusions,
            max_line_gap=int(zone_height * self.max_gap_ratio),
        )

        headers: list[DetectedComponent] = []
        idx = 1
        for block in blocks:
            headers.append(
                DetectedComponent(
                    id=f"header_{page.page_number:03d}_{idx:03d}",
                    type=ComponentType.HEADER,
                    page=page.page_number,
                    bbox=block,
                    text="",  # filled by the OCR phase
                    confidence=0.70,  # lower than text-layer: geometry only
                    metadata={"strategy": self.name, "needs_ocr": True},
                )
            )
            idx += 1

        return headers
