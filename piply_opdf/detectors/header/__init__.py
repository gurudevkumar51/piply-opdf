"""Header detection.

    from piply_opdf.detectors.header import HeaderDetector

    headers = HeaderDetector().detect(page_context)
"""

from piply_opdf.detectors.header.base import HeaderDetector
from piply_opdf.detectors.header.cv_strategy import CvHeaderStrategy
from piply_opdf.detectors.header.text_strategy import TextHeaderStrategy

__all__ = ["HeaderDetector", "TextHeaderStrategy", "CvHeaderStrategy"]
