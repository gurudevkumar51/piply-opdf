"""List-item detection.

    from piply_opdf.detectors.list_item import ListItemDetector

    items = ListItemDetector().detect(page_context, exclusions)
"""

from piply_opdf.detectors.list_item.base import ListItemDetector
from piply_opdf.detectors.list_item.cv_strategy import CvListItemStrategy
from piply_opdf.detectors.list_item.text_strategy import TextListItemStrategy

__all__ = ["ListItemDetector", "TextListItemStrategy", "CvListItemStrategy"]
