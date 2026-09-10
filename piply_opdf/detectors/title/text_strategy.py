"""Title detection from the PDF text layer."""

from __future__ import annotations

import statistics

from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.text_layer import extract_words, group_into_lines

__all__ = ["TextTitleStrategy"]


class TextTitleStrategy(DetectionStrategy):
    """A title is text that is prominent *relative to this page's body text*.

    Prominence is measured against the page's own median line height rather
    than an absolute font size, so the rule holds for a dense A5 form and a
    sparse A3 poster alike.
    """

    name = "text-layer"
    priority = 100

    def __init__(
        self,
        *,
        min_height_ratio: float = 1.35,
        search_ratio: float = 0.45,
        max_words: int = 20,
    ) -> None:
        #: How much taller than the median line a title must be.
        self.min_height_ratio = min_height_ratio
        #: Only consider lines in the top fraction of the page.
        self.search_ratio = search_ratio
        self.max_words = max_words

    def is_applicable(self, page: PageContext) -> bool:
        return page.has_text_layer

    def detect(
        self,
        page: PageContext,
        exclusions: list[BBox] | None = None,
    ) -> list[DetectedComponent]:
        exclusions = exclusions or []
        lines = group_into_lines(extract_words(page))
        if len(lines) < 2:
            return []

        heights = [ln.bbox.height for ln in lines if ln.bbox.height > 0]
        if not heights:
            return []
        median_height = statistics.median(heights)
        if median_height <= 0:
            return []

        limit = (page.height / page.scale) * self.search_ratio

        titles: list[DetectedComponent] = []
        index = 1
        for line in lines:
            if line.bbox.y > limit:
                break
            if line.bbox.height < median_height * self.min_height_ratio:
                continue
            if len(line.text.split()) > self.max_words:
                continue

            pixel_bbox = page.to_pixels(line.bbox)
            if pixel_bbox.is_excluded_by(exclusions):
                continue

            titles.append(
                DetectedComponent(
                    id=f"title_{page.page_number:03d}_{index:03d}",
                    type=ComponentType.TITLE,
                    page=page.page_number,
                    bbox=pixel_bbox,
                    text=line.text,
                    confidence=0.80,
                    index=index,
                    metadata={
                        "strategy": self.name,
                        "height_ratio": round(line.bbox.height / median_height, 2),
                    },
                )
            )
            index += 1

        return titles
