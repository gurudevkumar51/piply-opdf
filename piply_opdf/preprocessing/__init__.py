"""Page preprocessing applied before detection.

    from piply_opdf.preprocessing import deskew

    corrected, applied_angle = deskew(page_image)

Correction happens once, at page level, before any detector runs. Per-component
correction is deliberately avoided: rotating a page is a single affine warp,
whereas rotating components individually puts every bounding box in its own
rotated frame, making the manifest and any reconstruction intractable to
reassemble.
"""

from piply_opdf.preprocessing.deskew import (
    DEFAULT_MAX_ANGLE,
    DEFAULT_MIN_CORRECTION,
    deskew,
    estimate_skew_angle,
    rotate_image,
)

__all__ = [
    "deskew",
    "estimate_skew_angle",
    "rotate_image",
    "DEFAULT_MAX_ANGLE",
    "DEFAULT_MIN_CORRECTION",
]
