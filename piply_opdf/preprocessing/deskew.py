"""
Skew estimation and correction.

Why this matters more than it looks
-----------------------------------
Nearly every detection technique in the package assumes the page is axis
aligned: horizontal ink projection, baseline grouping, column gap analysis,
header and footer bands, table grid-line morphology. A few degrees of rotation
degrades all of them at once, and no threshold tuning compensates — the
assumption itself has broken. Because the primary input is scanned documents,
this affects the majority of real pages.

Method: projection-profile variance maximisation
------------------------------------------------
When text lines are horizontal, the row-wise ink projection is spiky — dense
rows through the lines, near-empty rows between them. Rotate the page and those
peaks smear together. So the correct angle is the one that maximises the
"sharpness" of the projection, measured as the summed squared difference
between adjacent rows.

This is preferred over Hough line detection for text pages: Hough needs actual
long straight lines, which prose does not have, and it is easily dominated by
table rules or a page border. Projection sharpness responds to the text itself.

Search is coarse-to-fine on a downscaled copy — the angle of a page does not
depend on its resolution, so there is no reason to pay for full resolution
while searching.

Only for pages with no text layer
---------------------------------
A PDF that carries embedded text reports coordinates in the *original* page
frame. Rotating the raster would put the image and the text layer in different
coordinate systems, breaking every text-layer strategy. Digital PDFs are also
not skewed in the first place — skew is an artefact of scanning. So callers
should deskew only when :attr:`PageContext.has_text_layer` is False, which is
exactly the population that needs it.
"""

from __future__ import annotations

import logging

import cv2
import numpy as np

from piply_opdf.detectors.common import binarize, to_grayscale
from piply_opdf.utils.image import rotate_image

logger = logging.getLogger(__name__)

__all__ = [
    "estimate_skew_angle",
    "rotate_image",
    "deskew",
    "DEFAULT_MAX_ANGLE",
    "DEFAULT_MIN_CORRECTION",
]

#: Search range, degrees either side of horizontal. Scanner skew beyond this is
#: really a misfeed, and a wider search invites locking onto the wrong axis.
DEFAULT_MAX_ANGLE = 10.0

#: Below this the correction is not worth an interpolation pass — resampling
#: costs a little sharpness, which would hurt OCR more than the skew does.
#:
#: Raised from 0.15 after a real failure: on `sample.pdf` the estimator found
#: 0.20 degrees of skew on an already-straight page, and correcting it took
#: table detection from one table with 171 cells to none at all. Rotating by a
#: fifth of a degree cannot straighten anything that was not already straight,
#: but the resampling still softens the thin rules a table is found by.
#:
#: 0.5 sits below the smallest skew worth correcting — over a 2550 px page a
#: half-degree displaces content by 22 px, which does matter — and above the
#: noise the estimator produces on straight pages.
DEFAULT_MIN_CORRECTION = 0.5

#: Width the image is reduced to for the angle search.
_SEARCH_WIDTH = 800


def _projection_sharpness(binary: np.ndarray) -> float:
    """Score how cleanly *binary* separates into horizontal text lines.

    The row-wise ink profile of well-aligned text alternates between dense rows
    (through glyphs) and sparse rows (between lines). Summed squared difference
    between adjacent rows rewards exactly that alternation, and collapses as
    lines smear across rows under rotation.
    """
    row_ink = binary.sum(axis=1, dtype=np.float64)
    if row_ink.size < 2:
        return 0.0
    return float(np.square(np.diff(row_ink)).sum())


def _rotate_for_search(binary: np.ndarray, angle: float) -> np.ndarray:
    """Rotate about the centre, keeping the same canvas.

    Corners are lost, which is irrelevant here: the score is a bulk statistic
    over the whole page and the search only needs relative comparisons.
    """
    height, width = binary.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2, height / 2), angle, 1.0)
    return cv2.warpAffine(
        binary, matrix, (width, height),
        flags=cv2.INTER_NEAREST, borderMode=cv2.BORDER_CONSTANT, borderValue=0,
    )


def estimate_skew_angle(
    image: np.ndarray,
    *,
    max_angle: float = DEFAULT_MAX_ANGLE,
    coarse_step: float = 1.0,
    fine_step: float = 0.1,
) -> float:
    """Estimate the page's skew in degrees.

    Positive means the page content is rotated anticlockwise, so correcting it
    requires rotating by the *negative* of this value — which is what
    :func:`deskew` does.

    Returns 0.0 for a blank or near-blank page, where no angle is meaningful.
    """
    if image is None or image.size == 0:
        return 0.0

    grey = to_grayscale(image)

    # The angle is a property of the layout, not of the resolution.
    height, width = grey.shape[:2]
    if width > _SEARCH_WIDTH:
        scale = _SEARCH_WIDTH / width
        grey = cv2.resize(
            grey, (_SEARCH_WIDTH, max(1, int(height * scale))), interpolation=cv2.INTER_AREA
        )

    binary = binarize(grey)
    if binary.sum() == 0:
        return 0.0

    def best_in(angles: np.ndarray) -> tuple[float, float]:
        best_angle, best_score = 0.0, -1.0
        for angle in angles:
            score = _projection_sharpness(_rotate_for_search(binary, float(angle)))
            if score > best_score:
                best_angle, best_score = float(angle), score
        return best_angle, best_score

    coarse_angle, _ = best_in(np.arange(-max_angle, max_angle + coarse_step, coarse_step))

    # Refine within one coarse step either side.
    fine_angle, _ = best_in(
        np.arange(coarse_angle - coarse_step, coarse_angle + coarse_step + fine_step, fine_step)
    )

    # The search finds the rotation that *straightens* the page; the skew of the
    # content is its negation. Returning the skew rather than the correction
    # keeps the sign consistent with how skew is normally reported, and leaves
    # the single negation to happen in deskew().
    return round(-fine_angle, 2)


def deskew(
    image: np.ndarray,
    *,
    max_angle: float = DEFAULT_MAX_ANGLE,
    min_correction: float = DEFAULT_MIN_CORRECTION,
) -> tuple[np.ndarray, float]:
    """Straighten *image*.

    Returns ``(corrected_image, applied_angle)``. When the estimated skew is
    below *min_correction* the original array is returned unchanged and the
    applied angle is 0.0 — resampling costs sharpness that OCR cares about more
    than it cares about a fraction of a degree.
    """
    angle = estimate_skew_angle(image, max_angle=max_angle)

    if abs(angle) < min_correction:
        return image, 0.0

    logger.debug("Deskewing page by %.2f degrees", -angle)
    # expand=False keeps the page frame, which every ratio-based zone depends on.
    return rotate_image(image, -angle, expand=False), -angle
