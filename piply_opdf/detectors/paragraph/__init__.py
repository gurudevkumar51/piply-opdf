"""Paragraph and sentence detection.

    from piply_opdf.detectors.paragraph import ParagraphDetector

    components = ParagraphDetector().detect(page_context, exclusions)
"""

from piply_opdf.detectors.paragraph.base import ParagraphDetector
from piply_opdf.detectors.paragraph.cv_strategy import CvParagraphStrategy
from piply_opdf.detectors.paragraph.text_strategy import TextParagraphStrategy

__all__ = ["ParagraphDetector", "TextParagraphStrategy", "CvParagraphStrategy"]
