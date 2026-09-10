"""
Page orientation: was this page fed through the scanner sideways?

Skew is a fraction of a degree and is corrected by
:mod:`piply_opdf.preprocessing.deskew`. **Orientation** is a quarter turn, and
until now nothing detected it at all. A sideways page fails every later stage at
once — text lines run the wrong way, header and footer bands look at the wrong
edges, table morphology finds nothing — and nothing notices.

What this module does and does not do
-------------------------------------

**It reliably answers: are the text lines horizontal or vertical?**

Upright text produces a row-ink profile that swings hard between dense rows
(through glyphs) and sparse rows (between lines). Turned a quarter turn, that
variation moves to the columns. Measured across the sample documents, the
upright page scores 2.0-2.7 times the sideways one.

**It deliberately does NOT answer: which way up?**

Telling 0 from 180 — or 90 from 270 — was tried four ways and none worked:

===========================  ==========================================
Signal                       Result
===========================  ==========================================
Ink mass above vs below      2/8. Worse than chance.
the densest row in a line
Baseline scatter of glyph    Identical for both. A 180 turn negates the
bottoms                      coordinates and the measure is invariant
                             under negation — structurally incapable.
Top-edge vs bottom-edge      1/10. At any sane working resolution the
raggedness                   spread quantises to zero.
Long ruled lines             Made it worse: a tall table's column rules
                             are longer than its row rules.
===========================  ==========================================

This is a genuinely hard problem without reading characters — it is why
Tesseract ships a separate orientation-and-script-detection mode that runs
recognition to decide. Guessing at 75% accuracy would turn one page in four
upside down, which is far worse than saying so.

So a sideways page is reported as **ambiguous, with both candidates**, and goes
to a human. That is the governing principle applied honestly: insufficient
confidence means review, not a confident guess.

Everything here works on ink alone — no text layer, no OCR, no model.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from piply_opdf.detectors.common import binarize, to_grayscale

__all__ = [
    "OrientationEstimate",
    "estimate_orientation",
    "correct_orientation",
    "UPRIGHT",
    "SIDEWAYS",
    "UNDECIDED",
]

#: The page's text lines already run across the page.
UPRIGHT = "UPRIGHT"
#: The text runs down the page. Which of the two quarter turns is needed cannot
#: be decided from ink alone — see the module docstring.
SIDEWAYS = "SIDEWAYS"
#: Too little line structure to judge: a photograph, a full-page grid, a nearly
#: blank page.
UNDECIDED = "UNDECIDED"

#: Width the page is reduced to before scoring. Orientation is a property of the
#: layout, not the resolution, and a small copy is far faster.
_SEARCH_WIDTH = 700

#: The upright score must beat the sideways score by this much to decide.
#: Measured across the samples: clear pages score 2.0-2.7, and the two
#: genuinely ambiguous ones scored 1.03 and 1.20. Set above both so those are
#: reported as undecided rather than guessed.
_MIN_RATIO = 1.5

_CONFIDENT = 0.85
_UNSURE = 0.30


@dataclass(frozen=True, slots=True)
class OrientationEstimate:
    """What could be worked out about which way round the page is."""

    #: UPRIGHT, SIDEWAYS or UNDECIDED.
    verdict: str
    #: 0..1. How strongly the horizontal/vertical question was answered.
    confidence: float
    #: Rotations that would stand the page up. Empty when upright; **two
    #: entries when sideways**, because the direction cannot be decided here.
    candidates: tuple[int, ...] = ()
    #: True when a person has to choose. Always true for SIDEWAYS.
    needs_review: bool = False
    #: Line-structure score each way, for diagnosis.
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def is_upright(self) -> bool:
        return self.verdict == UPRIGHT


def _line_variation(binary: np.ndarray) -> float:
    """How strongly the ink separates into bands across the rows.

    Coefficient of variation of the row-ink profile: standard deviation over
    mean. Text lines alternate dense and empty, so it is high; a sideways page
    spreads ink through every row, so it is low.

    Dimensionless, so the two orientations are comparable even though rotating
    swaps the image's width and height.
    """
    rows = binary.sum(axis=1, dtype=np.float64)
    mean = rows.mean() if rows.size else 0.0
    return float(rows.std() / mean) if mean > 0 else 0.0


def _prepare(image: np.ndarray) -> np.ndarray:
    grey = to_grayscale(image)
    height, width = grey.shape[:2]
    if width > _SEARCH_WIDTH:
        scale = _SEARCH_WIDTH / float(width)
        grey = cv2.resize(
            grey, (_SEARCH_WIDTH, max(1, int(height * scale))), interpolation=cv2.INTER_AREA
        )
    return binarize(grey)


def estimate_orientation(image: np.ndarray) -> OrientationEstimate:
    """Decide whether *image*'s text runs across the page or down it.

    A quarter turn is applied with :func:`numpy.rot90`, which is exact — no
    interpolation, so nothing is softened by the measurement itself.
    """
    if image is None or image.size == 0:
        return OrientationEstimate(UNDECIDED, 0.0, needs_review=True)

    binary = _prepare(image)

    across = _line_variation(binary)
    down = _line_variation(np.rot90(binary))
    scores = {"across": across, "down": down}

    best, worst = max(across, down), min(across, down)
    if worst <= 0 or best / worst < _MIN_RATIO:
        # A full-page grid or a photograph. Leaving it alone is the safe answer.
        return OrientationEstimate(UNDECIDED, _UNSURE, needs_review=True, scores=scores)

    if across >= down:
        return OrientationEstimate(UPRIGHT, _CONFIDENT, scores=scores)

    # Sideways, and which way is genuinely undecidable from ink. Both offered.
    return OrientationEstimate(
        SIDEWAYS, _CONFIDENT, candidates=(90, 270), needs_review=True, scores=scores
    )


def correct_orientation(
    image: np.ndarray, *, rotation: int | None = None
) -> tuple[np.ndarray, OrientationEstimate]:
    """Stand *image* upright where that can be done safely.

    Without *rotation* the image is returned untouched unless the page is
    clearly upright already — a sideways page is **not** turned, because the
    direction would be a guess. Pass *rotation* once a person has chosen.
    """
    estimate = estimate_orientation(image)

    if rotation is None:
        return image, estimate

    if rotation % 360 == 0:
        return image, estimate
    return np.rot90(image, k=(rotation // 90) % 4).copy(), estimate
