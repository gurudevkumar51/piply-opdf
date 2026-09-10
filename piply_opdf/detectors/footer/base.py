"""Footer detector: text-layer first, CV fallback for scanned pages."""

from __future__ import annotations

from piply_opdf.core.detector import DetectionStrategy, Detector, registry
from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.footer.cv_strategy import CvFooterStrategy
from piply_opdf.detectors.footer.text_strategy import TextFooterStrategy

__all__ = ["FooterDetector"]


@registry.register(ComponentType.FOOTER)
class FooterDetector(Detector):
    """Detects page footers in the bottom band of a page.

    Mirrors :class:`~piply_opdf.detectors.header.HeaderDetector`: exact text
    when a text layer exists, region geometry from the raster otherwise.
    """

    component_type = ComponentType.FOOTER

    def __init__(
        self,
        strategies: list[DetectionStrategy] | None = None,
        *,
        bottom_margin_ratio: float = 0.88,
    ) -> None:
        self.bottom_margin_ratio = bottom_margin_ratio
        super().__init__(strategies)

    def default_strategies(self) -> list[DetectionStrategy]:
        return [
            TextFooterStrategy(bottom_margin_ratio=self.bottom_margin_ratio),
            CvFooterStrategy(bottom_margin_ratio=self.bottom_margin_ratio),
        ]
