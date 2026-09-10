"""Title detector: text-layer first, CV fallback for scanned pages."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.title.cv_strategy import CvTitleStrategy
from piply_opdf.detectors.title.text_strategy import TextTitleStrategy

__all__ = ["TitleDetector"]


@registry.register(ComponentType.TITLE)
class TitleDetector(Detector):
    """Detects document and section titles by typographic prominence."""

    component_type = ComponentType.TITLE

    def __init__(self, strategies: list[DetectionStrategy] | None = None) -> None:
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [TextTitleStrategy(), CvTitleStrategy()]
