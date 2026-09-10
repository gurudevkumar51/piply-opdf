"""List-item detector: text-layer first, CV fallback for scanned pages."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.list_item.cv_strategy import CvListItemStrategy
from piply_opdf.detectors.list_item.text_strategy import TextListItemStrategy

__all__ = ["ListItemDetector"]


@registry.register(ComponentType.LIST_ITEM)
class ListItemDetector(Detector):
    """Detects bulleted and enumerated list items."""

    component_type = ComponentType.LIST_ITEM

    def __init__(self, strategies: list[DetectionStrategy] | None = None) -> None:
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [TextListItemStrategy(), CvListItemStrategy()]
