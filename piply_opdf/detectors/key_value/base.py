"""Key-value detector: text-layer first, CV fallback for scanned pages."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.key_value.cv_strategy import CvKeyValueStrategy
from piply_opdf.detectors.key_value.text_strategy import TextKeyValueStrategy

__all__ = ["KeyValueDetector"]


@registry.register(ComponentType.KEY_VALUE)
class KeyValueDetector(Detector):
    """Detects ``key: value`` rows outside of tables."""

    component_type = ComponentType.KEY_VALUE

    def __init__(self, strategies: list[DetectionStrategy] | None = None) -> None:
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [TextKeyValueStrategy(), CvKeyValueStrategy()]
