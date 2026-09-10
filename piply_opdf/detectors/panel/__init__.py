"""Panel detection — boxed regions that are not tables.

    from piply_opdf.detectors.panel import PanelDetector

    panels = PanelDetector().detect(page_context, exclusions)
"""

from piply_opdf.detectors.panel.base import PanelDetector
from piply_opdf.detectors.panel.cv_strategy import CvPanelStrategy

__all__ = ["PanelDetector", "CvPanelStrategy"]
