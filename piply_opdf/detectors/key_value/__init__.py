"""Key-value detection.

    from piply_opdf.detectors.key_value import KeyValueDetector

    pairs = KeyValueDetector().detect(page_context, exclusions)
"""

from piply_opdf.detectors.key_value.base import KeyValueDetector
from piply_opdf.detectors.key_value.cv_strategy import CvKeyValueStrategy
from piply_opdf.detectors.key_value.text_strategy import TextKeyValueStrategy

__all__ = ["KeyValueDetector", "TextKeyValueStrategy", "CvKeyValueStrategy"]
