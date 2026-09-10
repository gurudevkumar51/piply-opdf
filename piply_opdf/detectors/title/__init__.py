"""Title detection.

    from piply_opdf.detectors.title import TitleDetector

    titles = TitleDetector().detect(page_context, exclusions)
"""

from piply_opdf.detectors.title.base import TitleDetector
from piply_opdf.detectors.title.cv_strategy import CvTitleStrategy
from piply_opdf.detectors.title.text_strategy import TextTitleStrategy

__all__ = ["TitleDetector", "TextTitleStrategy", "CvTitleStrategy"]
