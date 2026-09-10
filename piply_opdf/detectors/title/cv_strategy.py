"""Title detection from the rendered page, for scanned documents."""

from __future__ import annotations

import statistics

from piply_opdf.classification.content import classify, measure
from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import binarize, find_text_lines, to_grayscale

__all__ = ["CvTitleStrategy"]

#: Graphic types confident enough to disqualify a region from being a title.
#: UNKNOWN is excluded so ambiguous text still becomes a title.
_CONFIDENT_GRAPHICS = (
    ComponentType.LOGO,
    ComponentType.STAMP,
    ComponentType.IMAGE,
    ComponentType.SIGNATURE,
)


class CvTitleStrategy(DetectionStrategy):
    """Finds unusually tall ink lines in the upper part of the page."""

    name = "cv-prominence"
    priority = 10

    def __init__(
        self,
        *,
        min_height_ratio: float = 1.35,
        search_ratio: float = 0.45,
    ) -> None:
        self.min_height_ratio = min_height_ratio
        self.search_ratio = search_ratio

    def is_applicable(self, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []

        binary = binarize(to_grayscale(page.image))
        for ex in exclusions:
            x0, y0 = max(0, ex.x), max(0, ex.y)
            x1, y1 = min(page.width, ex.x1), min(page.height, ex.y1)
            if x1 > x0 and y1 > y0:
                binary[y0:y1, x0:x1] = 0

        lines = find_text_lines(binary, dpi=page.dpi)
        if len(lines) < 2:
            return []

        median_height = statistics.median([ln.height for ln in lines if ln.height > 0] or [0])
        if median_height <= 0:
            return []

        limit = page.height * self.search_ratio

        titles: list[DetectedComponent] = []
        index = 1
        for line in sorted(lines, key=lambda b: b.y):
            if line.y > limit:
                break
            if line.height < median_height * self.min_height_ratio:
                continue

            # "Tall ink run" also describes a logo or a photograph. Without this
            # check a graphic in the top band is claimed as a title, which both
            # mislabels it and prevents the residual sweep from ever seeing it.
            crop = page.image[line.y:line.y1, line.x:line.x1]
            component_type = classify(measure(crop)).type
            if component_type in _CONFIDENT_GRAPHICS:
                continue

            titles.append(
                DetectedComponent(
                    id=f"title_{page.page_number:03d}_{index:03d}",
                    type=ComponentType.TITLE,
                    page=page.page_number,
                    bbox=line,
                    text="",
                    confidence=0.60,
                    index=index,
                    metadata={
                        "strategy": self.name,
                        "needs_ocr": True,
                        "height_ratio": round(line.height / median_height, 2),
                    },
                )
            )
            index += 1

        return titles
