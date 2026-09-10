"""Graphic and residual region detection.

    from piply_opdf.detectors.graphic import GraphicDetector

    # must run last, with every other detection as exclusions
    regions = GraphicDetector().detect(page_context, everything_claimed)

Emits SIGNATURE / HANDWRITING / LOGO / IMAGE, or UNKNOWN when the content
classifier cannot type a region confidently.
"""

from piply_opdf.detectors.graphic.base import GraphicDetector
from piply_opdf.detectors.graphic.cv_strategy import CvGraphicStrategy

__all__ = ["GraphicDetector", "CvGraphicStrategy"]
