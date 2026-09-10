"""Header detector: text-layer first, CV fallback for scanned pages."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.header.cv_strategy import CvHeaderStrategy
from piply_opdf.detectors.header.text_strategy import TextHeaderStrategy

__all__ = ["HeaderDetector"]


@registry.register(ComponentType.HEADER)
class HeaderDetector(Detector):
    """Detects page headers in the top band of a page.

    Resolution order:

    1. :class:`TextHeaderStrategy` — exact text from the PDF text layer.
    2. :class:`CvHeaderStrategy` — region geometry from the rendered raster,
       used when the page has no text layer (scans, image inputs). Text for
       these regions is supplied later by the OCR phase.
    """

    component_type = ComponentType.HEADER

    def __init__(
        self,
        strategies: list[DetectionStrategy] | None = None,
        *,
        top_margin_ratio: float = 0.12,
    ) -> None:
        self.top_margin_ratio = top_margin_ratio
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [
            TextHeaderStrategy(top_margin_ratio=self.top_margin_ratio),
            CvHeaderStrategy(top_margin_ratio=self.top_margin_ratio),
        ]
