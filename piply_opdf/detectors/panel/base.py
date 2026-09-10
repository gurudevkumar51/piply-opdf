"""Panel detector — closed frames with no internal division."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.panel.cv_strategy import CvPanelStrategy

__all__ = ["PanelDetector"]


@registry.register(ComponentType.PANEL)
class PanelDetector(Detector):
    """Detects boxed regions.

    Must run **before** the table detector: a frame has to be checked for
    internal structure before anything claims it as a table. A frame with one
    cell is a panel; with two or more it is left for the table detector.
    """

    component_type = ComponentType.PANEL

    def __init__(self, strategies: list[DetectionStrategy] | None = None) -> None:
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [CvPanelStrategy()]
