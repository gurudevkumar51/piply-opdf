"""Content classification for detected regions.

    from piply_opdf.classification import measure, classify

    component_type, confidence = classify(measure(crop))
"""

from piply_opdf.classification.content import (
    Classification,
    RegionFeatures,
    classify,
    measure,
)

__all__ = ["RegionFeatures", "Classification", "measure", "classify"]
