"""
Segmenters for prose-shaped regions.

    PARAGRAPH -> SENTENCE -> WORD
    HEADER / FOOTER / TITLE / LIST_ITEM / SENTENCE -> WORD

Header, footer and title are prose in every respect that matters here, so they
share the machinery rather than each growing a near-identical copy.
"""

from __future__ import annotations

from piply_opdf.core.segmenter import SegmentationStrategy, Segmenter, segmenter_registry
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.segmentation.common import (
    lines_from_image,
    lines_from_text_layer,
    words_from_image,
    words_from_text_layer,
)

__all__ = [
    "SentenceSegmenter",
    "WordSegmenter",
    "TextSentenceStrategy",
    "CvSentenceStrategy",
    "TextWordStrategy",
    "CvWordStrategy",
]


def _child_id(parent: DetectedComponent, kind: str, index: int) -> str:
    return f"{parent.id}_{kind}{index:03d}"


# ── PARAGRAPH -> SENTENCE ────────────────────────────────────────────────────


class TextSentenceStrategy(SegmentationStrategy):
    """One sentence per visual line, read from the text layer."""

    name = "text-layer"
    priority = 100

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return page.has_text_layer

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        return [
            DetectedComponent(
                id=_child_id(component, "s", index),
                type=ComponentType.SENTENCE,
                page=component.page,
                bbox=bbox,
                text=text,
                confidence=component.confidence,
                index=index,
                metadata={"strategy": self.name},
            )
            for index, (bbox, text, _words) in enumerate(
                lines_from_text_layer(component.bbox, page), start=1
            )
        ]


class CvSentenceStrategy(SegmentationStrategy):
    """One sentence per ink line, found by horizontal projection."""

    name = "cv-lines"
    priority = 10

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        return [
            DetectedComponent(
                id=_child_id(component, "s", index),
                type=ComponentType.SENTENCE,
                page=component.page,
                bbox=bbox,
                text="",
                confidence=component.confidence,
                index=index,
                metadata={"strategy": self.name, "needs_ocr": True},
            )
            for index, bbox in enumerate(lines_from_image(component.bbox, page), start=1)
        ]


@segmenter_registry.register(ComponentType.PARAGRAPH)
class SentenceSegmenter(Segmenter):
    """PARAGRAPH -> SENTENCE."""

    component_type = ComponentType.PARAGRAPH
    produces = ComponentType.SENTENCE

    def default_strategies(self) -> list[SegmentationStrategy]:
        return [TextSentenceStrategy(), CvSentenceStrategy()]


# ── SENTENCE / HEADER / FOOTER / TITLE / LIST_ITEM -> WORD ───────────────────


class TextWordStrategy(SegmentationStrategy):
    """Exact word boxes from the text layer."""

    name = "text-layer"
    priority = 100

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return page.has_text_layer

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        return [
            DetectedComponent(
                id=_child_id(component, "w", index),
                type=ComponentType.WORD,
                page=component.page,
                bbox=bbox,
                text=text,
                confidence=0.88,
                index=index,
                metadata={"strategy": self.name},
            )
            for index, (bbox, text) in enumerate(
                words_from_text_layer(component.bbox, page), start=1
            )
        ]


class CvWordStrategy(SegmentationStrategy):
    """Word boxes from connected-component analysis of the crop."""

    name = "cv-words"
    priority = 10

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        return [
            DetectedComponent(
                id=_child_id(component, "w", index),
                type=ComponentType.WORD,
                page=component.page,
                bbox=bbox,
                text="",
                confidence=0.65,
                index=index,
                metadata={"strategy": self.name, "needs_ocr": True},
            )
            for index, bbox in enumerate(words_from_image(component.bbox, page), start=1)
        ]


class WordSegmenter(Segmenter):
    """Any single-line prose region -> WORD."""

    produces = ComponentType.WORD

    def default_strategies(self) -> list[SegmentationStrategy]:
        return [TextWordStrategy(), CvWordStrategy()]


def _register_word_segmenter(component_type: str) -> None:
    """Register a WordSegmenter bound to *component_type*."""
    def factory() -> Segmenter:
        segmenter = WordSegmenter()
        segmenter.component_type = component_type
        return segmenter

    segmenter_registry.register_factory(component_type, factory)


# Every prose-shaped region splits to words. HEADER and FOOTER are included
# here, which is what makes them reachable as review units instead of dead ends.
for _type in (
    ComponentType.SENTENCE,
    ComponentType.HEADER,
    ComponentType.FOOTER,
    ComponentType.TITLE,
    ComponentType.LIST_ITEM,
):
    _register_word_segmenter(_type)
