"""Graphic / residual detector."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.graphic.cv_strategy import CvGraphicStrategy

__all__ = ["GraphicDetector"]


@registry.register(ComponentType.UNKNOWN)
class GraphicDetector(Detector):
    """Claims every region no other detector recognised.

    Unlike the other detectors this one is not looking for a specific shape —
    it is the sweep that guarantees a page loses nothing. It must run **last**,
    with all other detections passed as exclusions.

    Emits ``SIGNATURE``, ``HANDWRITING``, ``LOGO``, ``IMAGE`` or ``UNKNOWN``
    depending on what the content classifier makes of each region. There is no
    text-layer strategy: by definition these regions have no recoverable text.
    """

    component_type = ComponentType.UNKNOWN

    def __init__(self, strategies: list[DetectionStrategy] | None = None) -> None:
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [CvGraphicStrategy()]
