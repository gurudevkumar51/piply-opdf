"""Paragraph detection from the rendered page, for scanned documents.

Locates paragraph blocks and their constituent lines. Word-level boxes are not
produced here — without a text layer, word segmentation needs OCR, which runs
as a later phase. Each line becomes a SENTENCE child, which is the smallest
unit obtainable from geometry alone.
"""

from __future__ import annotations

from piply_opdf.classification.content import classify, measure
from piply_opdf.core.detector import DetectionStrategy
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.detectors.common import (
    binarize,
    find_text_lines,
    group_lines_into_blocks,
    points_to_px,
    to_grayscale,
)

__all__ = ["CvParagraphStrategy"]

#: Graphic types confident enough to override a text reading. UNKNOWN is
#: excluded on purpose — see the note in CvParagraphStrategy.detect.
_CONFIDENT_GRAPHICS = (
    ComponentType.LOGO,
    ComponentType.STAMP,
    ComponentType.IMAGE,
    ComponentType.SIGNATURE,
)


class CvParagraphStrategy(DetectionStrategy):
    """Groups raster text lines into paragraph blocks."""

    name = "cv-blocks"
    priority = 10

    def __init__(
        self,
        *,
        top_margin_ratio: float = 0.12,
        bottom_margin_ratio: float = 0.88,
        max_line_gap_points: float = 12.0,
    ) -> None:
        #: Body zone excludes the header/footer bands so those are not
        #: re-detected here as paragraphs.
        self.top_margin_ratio = top_margin_ratio
        self.bottom_margin_ratio = bottom_margin_ratio
        self.max_line_gap_points = max_line_gap_points

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

        # Erase claimed regions before grouping, so a paragraph adjacent to a
        # table is not merged into one block with it.
        for ex in exclusions:
            ex_y0 = max(0, ex.y - body_top)
            ex_y1 = min(body_bottom - body_top, ex.y1 - body_top)
            ex_x0 = max(0, ex.x)
            ex_x1 = min(page.width, ex.x1)
            if ex_x1 > ex_x0 and ex_y1 > ex_y0:
                binary[ex_y0:ex_y1, ex_x0:ex_x1] = 0

        lines = find_text_lines(binary, dpi=page.dpi)
        if not lines:
            return []

        max_gap = points_to_px(self.max_line_gap_points, page.dpi)
        blocks = group_lines_into_blocks(lines, max_gap)

        components: list[DetectedComponent] = []
        counters = {ComponentType.PARAGRAPH: 1, ComponentType.SENTENCE: 1}

        for block in blocks:
            block_lines = [ln for ln in lines if _within(ln, block)]
            if not block_lines:
                continue

            # Ink is not automatically text. Without this check a photograph or
            # a signature inside the body zone is grouped into a "paragraph",
            # which both mislabels it and hides it from the residual sweep.
            #
            # Only *confident* graphics are rejected. UNKNOWN deliberately stays
            # a paragraph: this is a text-first pipeline, and misfiling real
            # prose as an unclassified graphic loses it from OCR entirely,
            # whereas the reverse merely produces a low-confidence paragraph.
            page_block = BBox(block.x, block.y + body_top, block.width, block.height)
            crop = page.image[page_block.y:page_block.y1, page_block.x:page_block.x1]
            component_type = classify(measure(crop)).type
            if component_type in _CONFIDENT_GRAPHICS:
                continue

            comp_type = (
                ComponentType.SENTENCE if len(block_lines) == 1 else ComponentType.PARAGRAPH
            )
            index = counters[comp_type]
            counters[comp_type] += 1

            page_bbox = page_block

            children = [
                DetectedComponent(
                    id=f"sentence_{page.page_number:03d}_{index:03d}_{i:03d}",
                    type=ComponentType.SENTENCE,
                    page=page.page_number,
                    bbox=BBox(ln.x, ln.y + body_top, ln.width, ln.height),
                    text="",
                    confidence=0.70,
                    index=i,
                    metadata={"needs_ocr": True},
                )
                for i, ln in enumerate(block_lines, start=1)
            ] if comp_type == ComponentType.PARAGRAPH else []

            components.append(
                DetectedComponent(
                    id=f"{comp_type.lower()}_{page.page_number:03d}_{index:03d}",
                    type=comp_type,
                    page=page.page_number,
                    bbox=page_bbox,
                    text="",
                    confidence=0.70,
                    index=index,
                    children=children,
                    metadata={
                        "strategy": self.name,
                        "needs_ocr": True,
                        "line_count": len(block_lines),
                    },
                )
            )

        return components


def _within(line: BBox, block: BBox) -> bool:
    cx, cy = line.center
    return block.contains_point(cx, cy)
