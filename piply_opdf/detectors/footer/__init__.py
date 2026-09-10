"""Footer detection.

    from piply_opdf.detectors.footer import FooterDetector

    footers = FooterDetector().detect(page_context)
"""

from piply_opdf.detectors.footer.base import FooterDetector
from piply_opdf.detectors.footer.cv_strategy import CvFooterStrategy
from piply_opdf.detectors.footer.text_strategy import TextFooterStrategy

__all__ = ["FooterDetector", "TextFooterStrategy", "CvFooterStrategy"]
