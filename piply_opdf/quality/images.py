"""
The three images a page is carried through the pipeline as.

One scan, three representations, because layout detection and OCR want opposite
things from the same pixels:

.. code-block:: text

                        ORIGINAL
                   immutable source of truth
                            |
                  orientation + safe deskew
                            |
                     STRUCTURAL
                geometry only - no sharpening,
                  no thresholding, no denoise
                            |
             +--------------+--------------+
             |                             |
   Layout detection                enhancement, when it helps
   Table detection                          |
   Fingerprinting                        WORKING
   Geometry verification                     |
                                            OCR

Why this shape
--------------

**The original is never modified.** Reconstruction, export and any later audit
refer back to it, so whatever the pipeline does can always be checked against
what actually arrived.

**Layout reads the structural image, not the working one.** Measured on
``sample.pdf``: the enhanced page lost a 171-cell table at 0.05 degrees of
rotation, where the unenhanced page survived 2 degrees. Sharpening for
legibility thins the hairline rules that table detection depends on. The two
stages want different pictures.

**The working image descends from the structural one**, not from the raw scan,
so OCR inherits the orientation and deskew rather than reading a crooked page.

**Enhancement is never allowed to make structure worse.** It is applied only
when the assessment says the page needs it, and kept only when the page still
has as much line structure afterwards as it had before.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from piply_opdf.detectors.common import binarize, to_grayscale
from piply_opdf.preprocessing.deskew import deskew
from piply_opdf.quality.orientation import OrientationEstimate, estimate_orientation

__all__ = ["PageImages", "build_page_images", "structure_evidence"]

#: Enhancement is rejected when it leaves the page with less than this share of
#: the structure it had before. Not 1.0: enhancement legitimately removes some
#: speckle, and a little loss is the price of a cleaner page.
_MIN_STRUCTURE_KEPT = 0.9

#: A run of ink this fraction of the page wide counts as a ruled line.
_RULE_LENGTH_SHARE = 1 / 12


@dataclass(frozen=True, slots=True)
class PageImages:
    """One page, in the three forms the pipeline needs."""

    #: Exactly what arrived. Never modified.
    original: np.ndarray
    #: Orientation and deskew only. Layout, tables, fingerprints and geometry
    #: verification all read this.
    structural: np.ndarray
    #: Enhanced for legibility, when that helped. OCR reads this. Is the same
    #: array as :attr:`structural` when no enhancement was applied or kept.
    working: np.ndarray

    #: Degrees of skew corrected, 0.0 when none was worth applying.
    skew_corrected: float = 0.0
    #: What could be worked out about which way round the page is.
    orientation: OrientationEstimate | None = None
    #: True when a quarter turn was applied.
    orientation_applied: bool = False
    #: Why the working image ended up as it did — for diagnosis and for the
    #: evidence record a component carries.
    notes: dict[str, object] = field(default_factory=dict)

    @property
    def was_enhanced(self) -> bool:
        return self.working is not self.structural

    @property
    def needs_orientation_review(self) -> bool:
        """True when a person still has to say which way up the page goes."""
        return bool(self.orientation and self.orientation.needs_review)


def structure_evidence(image: np.ndarray) -> float:
    """How much ruled-line structure a page shows, as a share of its ink.

    Long horizontal runs surviving a morphological opening. This is what table
    detection needs and what over-eager sharpening destroys, so it is the right
    thing to compare before and after enhancing.
    """
    if image is None or image.size == 0:
        return 0.0

    binary = binarize(to_grayscale(image))
    total = float((binary > 0).sum())
    if total <= 0:
        return 0.0

    length = max(12, int(binary.shape[1] * _RULE_LENGTH_SHARE))
    horizontal = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (length, 1))
    )
    vertical = cv2.morphologyEx(
        binary, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, length))
    )
    return float((horizontal > 0).sum() + (vertical > 0).sum()) / total


def build_page_images(
    image: np.ndarray,
    *,
    enhance: "callable[[np.ndarray], np.ndarray] | None" = None,
    orientation_rotation: int | None = None,
    has_text_layer: bool = False,
) -> PageImages:
    """Derive the structural and working images from one page.

    *enhance* is called only when supplied; the caller decides from the quality
    assessment whether the page needs it. Its result is kept only if the page
    still shows comparable line structure afterwards.

    *orientation_rotation* applies a quarter turn a person has chosen. Nothing
    is turned automatically: the direction cannot be decided from ink alone, so
    guessing risks putting a page upside down.

    *has_text_layer* skips deskew, because PyMuPDF reports text coordinates in
    the original page frame and rotating the raster would put the image and the
    text layer in different coordinate systems.
    """
    notes: dict[str, object] = {}

    if image is None or image.size == 0:
        raise ValueError("build_page_images needs a page image")

    orientation = estimate_orientation(image)
    notes["orientation_verdict"] = orientation.verdict

    structural = image
    applied = False
    if orientation_rotation:
        structural = np.rot90(structural, k=(orientation_rotation // 90) % 4).copy()
        applied = True
        notes["orientation_rotation"] = orientation_rotation

    # Deskew. Pages with a text layer are left alone — see the docstring.
    skew = 0.0
    if not has_text_layer:
        straightened, skew = deskew(structural)
        if skew:
            structural = straightened
            notes["skew_corrected"] = round(skew, 3)

    working = structural
    if enhance is not None:
        working = _enhanced_if_it_helps(structural, enhance, notes)

    return PageImages(
        original=image,
        structural=structural,
        working=working,
        skew_corrected=skew,
        orientation=orientation,
        orientation_applied=applied,
        notes=notes,
    )


def _enhanced_if_it_helps(
    structural: np.ndarray,
    enhance: "callable[[np.ndarray], np.ndarray]",
    notes: dict[str, object],
) -> np.ndarray:
    """Enhance, and keep the result only if the page is still as structured.

    A page that comes back with its rules thinned away is worse for every stage
    except OCR, and OCR reads a copy anyway — so the safe answer is to keep the
    structural image and let OCR work from that.
    """
    try:
        enhanced = enhance(structural)
    except Exception as exc:                      # a bad page must not stop the run
        notes["enhancement"] = f"failed: {type(exc).__name__}"
        return structural

    if enhanced is None or enhanced.size == 0:
        notes["enhancement"] = "produced nothing"
        return structural

    before = structure_evidence(structural)
    after = structure_evidence(enhanced)
    notes["structure_before"] = round(before, 5)
    notes["structure_after"] = round(after, 5)

    if before > 0 and after < before * _MIN_STRUCTURE_KEPT:
        notes["enhancement"] = "rejected: destroyed line structure"
        return structural

    notes["enhancement"] = "kept"
    return enhanced
