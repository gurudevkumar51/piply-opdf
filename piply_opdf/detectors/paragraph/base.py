"""Paragraph detector: text-layer first, CV fallback for scanned pages."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.paragraph.cv_strategy import CvParagraphStrategy
from piply_opdf.detectors.paragraph.text_strategy import TextParagraphStrategy

__all__ = ["ParagraphDetector"]


@registry.register(ComponentType.PARAGRAPH)
class ParagraphDetector(Detector):
    """Detects prose blocks.

    Emits SENTENCE for single-line runs and PARAGRAPH for multi-line runs, in
    one flat list — callers split on ``component.type``.
    """

    component_type = ComponentType.PARAGRAPH

    def __init__(self, strategies: list[DetectionStrategy] | None = None) -> None:
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [TextParagraphStrategy(), CvParagraphStrategy()]
