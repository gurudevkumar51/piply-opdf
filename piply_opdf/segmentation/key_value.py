"""
KEY_VALUE -> KEY / SEPARATOR / VALUE.

The three parts are emitted as separate units so each can be OCR'd, verified
and learned independently — a key like ``Invoice Number`` recurs across every
document of a form type and only ever needs verifying once, whereas its value
differs every time.

The separator is emitted only when it is a real glyph (``:`` or ``=``). When
the two halves were split on whitespace alone there is nothing between them to
recognise, so no separator unit is produced.
"""

from __future__ import annotations

from piply_opdf.core.segmenter import SegmentationStrategy, Segmenter, segmenter_registry
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.segmentation.common import words_from_text_layer

__all__ = ["KeyValueSegmenter", "TextKeyValueSplitStrategy", "CvKeyValueSplitStrategy"]

#: Role names recorded in child metadata.
ROLE_KEY = "key"
ROLE_SEPARATOR = "separator"
ROLE_VALUE = "value"


def _unit(
    parent: DetectedComponent,
    role: str,
    index: int,
    bbox: BBox,
    text: str,
    confidence: float,
    strategy: str,
    needs_ocr: bool = False,
) -> DetectedComponent:
    metadata: dict = {"role": role, "strategy": strategy}
    if needs_ocr:
        metadata["needs_ocr"] = True
    return DetectedComponent(
        id=f"{parent.id}_{role}",
        type=ComponentType.WORD,
        page=parent.page,
        bbox=bbox,
        text=text,
        confidence=confidence,
        index=index,
        metadata=metadata,
    )


class TextKeyValueSplitStrategy(SegmentationStrategy):
    """Split using the key/value/separator the detector already parsed.

    The text detector recorded these in metadata; geometry for each part is
    recovered by matching the parsed strings back onto word boxes.
    """

    name = "text-layer"
    priority = 100

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return page.has_text_layer and "key" in component.metadata

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        key_text = str(component.metadata.get("key", "")).strip()
        value_text = str(component.metadata.get("value", "")).strip()
        separator = str(component.metadata.get("separator", ""))
        if not key_text or not value_text:
            return []

        words = words_from_text_layer(component.bbox, page)
        if not words:
            return []

        # Walk the words until the accumulated text covers the key; the rest is
        # the value. Comparison ignores spacing and the separator glyph, which
        # the detector strips during parsing.
        def normalise(s: str) -> str:
            return "".join(ch for ch in s.lower() if ch.isalnum())

        target = normalise(key_text)
        accumulated = ""
        split_at = 0
        for i, (_bbox, text) in enumerate(words):
            accumulated += normalise(text)
            if accumulated.startswith(target) or target.startswith(accumulated) and accumulated == target:
                split_at = i + 1
                break
            if len(accumulated) >= len(target):
                split_at = i + 1
                break

        if split_at == 0 or split_at >= len(words):
            return []

        key_boxes = [b for b, _ in words[:split_at]]
        value_boxes = [b for b, _ in words[split_at:]]

        units = [
            _unit(component, ROLE_KEY, 1, _union(key_boxes), key_text, 0.88, self.name),
        ]

        # A real separator glyph occupies the gap between the halves.
        if separator in (":", "="):
            gap = BBox.from_xyxy(
                _union(key_boxes).x1,
                component.bbox.y,
                _union(value_boxes).x,
                component.bbox.y1,
            )
            if gap.width > 0:
                units.append(
                    _unit(component, ROLE_SEPARATOR, 2, gap, separator, 0.88, self.name)
                )

        units.append(
            _unit(component, ROLE_VALUE, 3, _union(value_boxes), value_text, 0.88, self.name)
        )
        return units


class CvKeyValueSplitStrategy(SegmentationStrategy):
    """Build units from the split geometry the CV detector recorded.

    The detector stores ``key_bbox`` / ``value_bbox`` in metadata rather than
    attaching children, so segmentation stays the sole owner of unit creation.
    """

    name = "cv-gap"
    priority = 10

    def is_applicable(self, component: DetectedComponent, page: PageContext) -> bool:
        return "key_bbox" in component.metadata and "value_bbox" in component.metadata

    def segment(
        self,
        component: DetectedComponent,
        page: PageContext,
    ) -> list[DetectedComponent]:
        key_bbox = BBox.from_any(component.metadata.get("key_bbox"))
        value_bbox = BBox.from_any(component.metadata.get("value_bbox"))
        if key_bbox is None or value_bbox is None:
            return []

        units = [
            _unit(component, ROLE_KEY, 1, key_bbox, "", 0.65, self.name, needs_ocr=True),
        ]

        # Prefer the separator's real geometry when detection isolated the glyph
        # as its own cluster; otherwise fall back to the gap between the halves,
        # which is where a separator would sit if there is one.
        separator_bbox = BBox.from_any(component.metadata.get("separator_bbox"))
        if separator_bbox is None:
            separator_bbox = BBox.from_xyxy(
                key_bbox.x1, component.bbox.y, value_bbox.x, component.bbox.y1
            )
            separator_confidence = 0.50
        else:
            separator_confidence = 0.65

        if separator_bbox.width > 0:
            units.append(
                _unit(
                    component, ROLE_SEPARATOR, 2, separator_bbox, "",
                    separator_confidence, self.name, needs_ocr=True,
                )
            )

        units.append(
            _unit(component, ROLE_VALUE, 3, value_bbox, "", 0.65, self.name, needs_ocr=True)
        )
        return units


@segmenter_registry.register(ComponentType.KEY_VALUE)
class KeyValueSegmenter(Segmenter):
    """KEY_VALUE -> KEY / SEPARATOR / VALUE."""

    component_type = ComponentType.KEY_VALUE
    produces = ComponentType.WORD

    def default_strategies(self) -> list[SegmentationStrategy]:
        return [TextKeyValueSplitStrategy(), CvKeyValueSplitStrategy()]


def _union(boxes: list[BBox]) -> BBox:
    return BBox.from_xyxy(
        min(b.x for b in boxes),
        min(b.y for b in boxes),
        max(b.x1 for b in boxes),
        max(b.y1 for b in boxes),
    )
