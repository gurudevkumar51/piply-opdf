"""
Content classification for non-prose regions.

Given a cropped region, decide what it actually is: printed text, a signature,
handwriting, a logo, a photograph, or something we cannot type confidently.

This is one place rather than four competing detectors. Signature, handwriting,
logo and photo detection all need the same measurements from the same crop;
running four separate page scans to compute them would be wasteful and would
let the four disagree about the same region.

Every threshold is a **ratio or a normalised statistic**, never an absolute
pixel count, so the same rules hold at any render DPI and any page size.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import cv2
import numpy as np

from piply_opdf.core.types import ComponentType
from piply_opdf.detectors.common import binarize, to_grayscale

__all__ = ["RegionFeatures", "Classification", "measure", "classify"]


@dataclass(frozen=True, slots=True)
class RegionFeatures:
    """Scale-free measurements of a cropped region."""

    #: Fraction of pixels that are ink after binarisation.
    ink_ratio: float
    #: Connected components per megapixel — texture density.
    component_density: float
    #: Std/mean of component areas. Text is uniform; drawings are not.
    component_area_cv: float
    #: Std/mean of stroke width from the distance transform.
    stroke_width_cv: float
    #: Mean HSV saturation, 0-1. Print is grey; logos and photos are coloured.
    saturation: float
    #: Fraction of distinct quantised colours present. Photos are rich.
    colour_richness: float
    #: Fraction of pixels that are edges.
    edge_density: float
    #: width / height.
    aspect_ratio: float
    #: Fraction of rows containing ink — solid artwork fills; text has gaps.
    row_coverage: float
    #: Distinct dominant hue clusters among saturated pixels. **Rule 2**: a
    #: rubber stamp deposits one ink, a designed logo is normally polychrome.
    colour_clusters: int
    #: Runs of connected ink separated by more than the within-word gap.
    #: **Rule 3**: a signature is a name (1-2 groups); handwriting is a
    #: sentence (3 or more).
    word_groups: int
    #: Spread of component bottom edges within a text row, relative to row
    #: height. Printing sits on a ruled baseline so this is near zero; a pen
    #: drifts off the line. ``-1`` when there is too little to measure.
    #:
    #: This is what separates printed text from handwriting **on a scan**.
    #: Stroke width cannot: real scanned print measures 0.34-0.40 and
    #: handwriting 0.43, which is no gap at all.
    baseline_scatter: float


def measure(crop: np.ndarray) -> RegionFeatures | None:
    """Measure *crop*. Returns None when the region is too small to judge."""
    if crop is None or crop.size == 0:
        return None
    height, width = crop.shape[:2]
    if height < 4 or width < 4:
        return None

    grey = to_grayscale(crop)
    binary = binarize(grey)
    area = float(height * width)

    ink_ratio = float((binary > 0).sum()) / area

    count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)
    areas = stats[1:, cv2.CC_STAT_AREA] if count > 1 else np.array([])
    component_density = (len(areas) / area) * 1_000_000
    component_area_cv = (
        float(areas.std() / areas.mean()) if areas.size and areas.mean() > 0 else 0.0
    )

    # Stroke width via distance transform: uniform for print, variable for pen.
    distance = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    widths = distance[binary > 0]
    stroke_width_cv = (
        float(widths.std() / widths.mean()) if widths.size and widths.mean() > 0 else 0.0
    )

    if crop.ndim == 3 and crop.shape[2] >= 3:
        hsv = cv2.cvtColor(crop[:, :, :3], cv2.COLOR_BGR2HSV)
        saturation = float(hsv[:, :, 1].mean()) / 255.0
        quantised = (crop[:, :, :3] // 32).reshape(-1, 3)
        colour_richness = len(np.unique(quantised, axis=0)) / 512.0  # 8^3 buckets
    else:
        saturation = 0.0
        colour_richness = 0.0

    edges = cv2.Canny(grey, 50, 150)
    edge_density = float((edges > 0).sum()) / area

    row_coverage = float(((binary > 0).sum(axis=1) > 0).sum()) / height

    return RegionFeatures(
        ink_ratio=ink_ratio,
        component_density=component_density,
        component_area_cv=component_area_cv,
        stroke_width_cv=stroke_width_cv,
        saturation=saturation,
        colour_richness=min(1.0, colour_richness),
        edge_density=edge_density,
        aspect_ratio=width / height,
        row_coverage=row_coverage,
        colour_clusters=_count_colour_clusters(crop),
        word_groups=_count_word_groups(binary),
        baseline_scatter=_baseline_scatter(stats[1:] if count > 1 else np.array([])),
    )


#: A component smaller than this is speckle, not a glyph.
_MIN_GLYPH_AREA = 4
#: Bottom edges within this multiple of glyph height count as the same row.
_ROW_GROUPING = 0.6


def _baseline_scatter(stats: np.ndarray) -> float:
    """How tightly component bottoms line up within each row.

    Printing rests on a ruled baseline, so the bottoms of the glyphs in a row
    agree closely. A pen wanders. Returns ``-1`` when there is too little ink
    to say anything.
    """
    if stats.size == 0:
        return -1.0

    boxes = stats[stats[:, cv2.CC_STAT_AREA] >= _MIN_GLYPH_AREA]
    if len(boxes) < 4:
        return -1.0

    median_height = float(np.median(boxes[:, cv2.CC_STAT_HEIGHT]))
    if median_height <= 0:
        return -1.0

    bottoms = np.sort(boxes[:, cv2.CC_STAT_TOP] + boxes[:, cv2.CC_STAT_HEIGHT]).astype(float)

    rows: list[list[float]] = []
    current = [bottoms[0]]
    for value in bottoms[1:]:
        if value - current[-1] <= median_height * _ROW_GROUPING:
            current.append(value)
        else:
            rows.append(current)
            current = [value]
    rows.append(current)

    # Spread measured as median absolute deviation, not standard deviation.
    # Descenders (p, j, q) sit below the baseline and are a minority, so they
    # inflate a standard deviation badly — enough that ordinary prose scored
    # worse than a line of digits. MAD ignores a minority that disagrees.
    def spread(row: list[float]) -> float:
        centre = np.median(row)
        return float(np.median(np.abs(np.asarray(row) - centre))) / median_height

    # A row of one or two pieces says nothing about alignment.
    spreads = [spread(r) for r in rows if len(r) >= 3]
    return float(np.median(spreads)) if spreads else -1.0


#: A pixel must be at least this saturated to carry a usable hue. Below it the
#: hue channel is numerically unstable and reports nonsense for grey pixels.
_MIN_HUE_SATURATION = 40

#: A hue cluster must hold at least this share of the coloured pixels to count.
#: Without it, anti-aliasing fringes register as extra colours and every logo
#: looks polychrome.
_MIN_CLUSTER_SHARE = 0.12


def _count_colour_clusters(crop: np.ndarray) -> int:
    """Distinct dominant hues, ignoring grey pixels and thin fringes.

    Rule 2 rests on this: one ink means a stamp, several mean a logo. Hue is
    binned coarsely (15 degrees) because scanning shifts colour slightly, and
    a stamp must not split into two clusters just because the ink faded.
    """
    if crop is None or crop.ndim != 3 or crop.shape[2] < 3:
        return 0

    hsv = cv2.cvtColor(crop[:, :, :3], cv2.COLOR_BGR2HSV)
    hue, saturation = hsv[:, :, 0], hsv[:, :, 1]

    coloured = hue[saturation >= _MIN_HUE_SATURATION]
    if coloured.size == 0:
        return 0

    # 12 bins of 15 degrees over OpenCV's 0-179 hue range.
    histogram = np.bincount(coloured // 15, minlength=12).astype(float)
    histogram /= histogram.sum()

    return int((histogram >= _MIN_CLUSTER_SHARE).sum())


def _count_word_groups(binary: np.ndarray) -> int:
    """Runs of ink separated by more than the gap within a word.

    Rule 3 rests on this: one or two groups is a name, three or more is a
    sentence. The gap threshold scales with the region's height, so it holds
    for a large signature and a small one alike.
    """
    if binary.size == 0:
        return 0

    height = binary.shape[0]
    column_ink = (binary > 0).sum(axis=0)
    gap = max(2, int(height * 0.25))

    groups = 0
    blank = gap                     # start "in a gap" so leading ink counts
    for value in column_ink:
        if value > 0:
            if blank >= gap:
                groups += 1
            blank = 0
        else:
            blank += 1
    return groups


# Thresholds sit in the gaps between measured per-class ranges rather than being
# guessed. Medians over the calibration corpus (12 samples per class):
#
#   class        ink  density  areaCV  strokeCV   sat   rich  COLOURS  GROUPS
#   printed     0.05   1139     0.39     0.09    0.00  0.016     0       1
#   signature   0.04     18     0.00     0.32    0.00  0.016     0       1
#   handwriting 0.04    704     0.69     0.43    0.00  0.004     0       4
#   logo        0.72     25     0.00     0.60    0.59  0.006     2       1
#   stamp       0.07    213     0.76     0.40    0.05  0.023     1       1
#   photo       0.50    284     4.09     0.71    0.08  0.068     0       1
#
# NOTE: calibrated on generated samples. Real signatures, stamps and scanned
# photographs vary more widely; revisit once labelled real samples exist.

#: Below this there is not enough ink to judge anything. Without the floor an
#: empty region satisfies "few components, sparse ink" and reads as a signature.
_MIN_INK_FOR_CONTENT = 0.005

# Photograph
_IMAGE_MIN_RICHNESS = 0.04
_IMAGE_MIN_INK = 0.25
_IMAGE_MIN_AREA_CV = 1.8

# Rule 2 — stamp versus logo, by colour count
_STAMP_MIN_DENSITY = 100.0      # a seal is broken and fragmented; a logo is solid
#: A stamp or logo is a *dense mark*. Coloured line-work — a table ruled in blue
#: ink, a coloured underline — is sparse, and without this floor it satisfied
#: "one colour" and came back as a logo, which then disqualified it from being
#: a table. Measured: stamps from 0.06, logos from 0.37, a ruled table 0.012.
_MARK_MIN_INK = 0.04
#: Above this, stroke width varies the way a pen's does rather than a printing
#: plate's. Generated stamps sit at 0.40-0.41; the one real signature measured
#: 0.463. Used only to add SIGNATURE as an alternative, never to decide alone —
#: the margin is too thin for that on the evidence available.
_PEN_LIKE_STROKE_CV = 0.43

# Printed text
#: Clean print has near-uniform strokes. This holds for digital renders and
#: good scans, but **not** for ordinary office scans, which measure 0.34-0.40.
_TEXT_MAX_STROKE_CV = 0.20
#: Text is many small pieces. Every other class sits far below this: logo 25,
#: stamp 213, photo 284, signature 18 — against 585-1139 for text. That gap is
#: what makes it safe to ask "is this text?" before asking about colour.
_TEXT_MIN_DENSITY = 400.0
#: Printing rests on a ruled baseline. Measured on real scanned print:
#: 0.019-0.131. Handwriting reaches 0.89. This is the discriminator that
#: survives a scan, where stroke width does not.
_TEXT_MAX_BASELINE_SCATTER = 0.15
#: Neat handwriting can sit close to a line, so baseline alignment alone is not
#: enough — the ranges touch at 0.10-0.15. Stroke width still *narrows* the
#: gap even though it cannot close it: scanned print reaches 0.396 and
#: handwriting starts at 0.43. Requiring both leaves no overlap.
_TEXT_MAX_STROKE_CV_SCANNED = 0.41

# Ruled lines — dividers, box edges, underlines
#: A line is far longer than it is thick. Measured on real documents: the false
#: signatures were 2386x27 and 1937x27, giving 88 and 72. Genuine marks sit far
#: below — signature 2.4, logo 1.7, photograph 1.0.
_SEPARATOR_MIN_ASPECT = 12.0
#: A rule puts its ink in a couple of scan lines. Text spread over the same
#: width fills much more of the region's height.
_SEPARATOR_MAX_ROW_COVERAGE = 0.60

# Rule 3 — signature versus handwriting, by word-group count
_SIGNATURE_MAX_GROUPS = 2
_SIGNATURE_MAX_DENSITY = 120.0
_SIGNATURE_MAX_INK = 0.20
_SIGNATURE_MAX_AREA_CV = 1.50
_HANDWRITING_MIN_STROKE_CV = 0.30


class Classification(NamedTuple):
    """What a region is, how sure we are, and the runners-up.

    ``candidates`` is populated only for a near-tie, so an operator can pick
    from a short list instead of being asked an open question (R13).
    """

    type: str
    confidence: float
    candidates: list[dict] = []


def classify(features: RegionFeatures | None) -> Classification:
    """Decide what a region is.

    Ordered most specific first. Where two types share every measurable
    property the boundary is set by a **rule**, not inferred — see
    docs/components.md.

    Anything matching nothing becomes :attr:`ComponentType.UNKNOWN`. A
    confidently wrong label is worse than an honest "needs a human", because a
    mistyped component is parsed with the wrong rules and the error spreads
    silently.
    """
    if features is None:
        return Classification(ComponentType.UNKNOWN, 0.0)

    f = features

    # Effectively blank: no rule below can say anything meaningful.
    if f.ink_ratio < _MIN_INK_FOR_CONTENT:
        return Classification(ComponentType.UNKNOWN, 0.10)

    # Photograph: rich colour with heavy coverage, or wildly uneven components.
    if (f.colour_richness > _IMAGE_MIN_RICHNESS and f.ink_ratio > _IMAGE_MIN_INK) or (
        f.component_area_cv > _IMAGE_MIN_AREA_CV and f.ink_ratio > _IMAGE_MIN_INK
    ):
        return Classification(ComponentType.IMAGE, 0.75)

    # ── Printed text ─────────────────────────────────────────────────────────
    #
    # Asked **before** colour, deliberately. Text is text whether it is black,
    # blue, or printed over a yellow highlight. Asking about colour first meant
    # every hyperlink came back STAMP and every heading on a shaded band came
    # back LOGO, because those rules only ever looked at hue.
    #
    # Safe to put first because the density floor excludes every other class:
    # logo 25, stamp 213, photo 284, signature 18 — all far below 400.
    #
    # Two ways to qualify, because one measurement does not cover both cases:
    #   * uniform strokes    — clean digital text and good scans
    #   * tight baselines    — ordinary office scans, where strokes are ragged
    #                          (0.34-0.40) but the line is still ruled
    scanned_text = (
        0.0 <= f.baseline_scatter < _TEXT_MAX_BASELINE_SCATTER
        and f.stroke_width_cv < _TEXT_MAX_STROKE_CV_SCANNED
    )
    if f.component_density > _TEXT_MIN_DENSITY and (
        f.stroke_width_cv < _TEXT_MAX_STROKE_CV or scanned_text
    ):
        return Classification(ComponentType.PARAGRAPH, 0.70)

    # ── Ruled lines ──────────────────────────────────────────────────────────
    #
    # A divider, a box edge, an underline. Asked after text so that a wide
    # single line of prose — which is also long and thin — has already been
    # claimed, and before the pen rules, which used to swallow these: a 2386x27
    # rule satisfied "sparse ink, few pieces, one word-group" and was reported
    # as a signature on nearly every document with a divider in it.
    aspect = f.aspect_ratio if f.aspect_ratio >= 1.0 else (
        1.0 / f.aspect_ratio if f.aspect_ratio > 0 else 0.0
    )
    if aspect >= _SEPARATOR_MIN_ASPECT and f.row_coverage <= _SEPARATOR_MAX_ROW_COVERAGE:
        return Classification(ComponentType.SEPARATOR, 0.80)

    # ── Rule 2: stamp versus logo, by colour count ───────────────────────────
    #
    # Only for a dense mark. Sparse coloured ink is line-work or text, and
    # deciding "logo versus stamp" about a ruled table is meaningless.
    if f.colour_clusters >= 2 and f.ink_ratio >= _MARK_MIN_INK:
        return Classification(ComponentType.LOGO, 0.85)

    if f.colour_clusters == 1 and f.ink_ratio >= _MARK_MIN_INK:
        # One ink. A seal is applied by hand, so its edges break up and it
        # fragments into many pieces; a printed logo stays solid.
        if f.component_density > _STAMP_MIN_DENSITY:
            # A signature is also one ink, also broken, also compact — a real
            # one measured density 133 against a stamp's 137, which is no gap.
            # Where the strokes vary like a pen's, say so and keep SIGNATURE as
            # the alternative rather than answering STAMP with confidence
            # (R13). Reported as a near-tie because the evidence is thin: this
            # boundary rests on very few real signatures.
            if f.stroke_width_cv >= _PEN_LIKE_STROKE_CV and f.word_groups <= _SIGNATURE_MAX_GROUPS:
                return Classification(
                    ComponentType.STAMP, 0.50,
                    [{"type": ComponentType.STAMP, "confidence": 0.50},
                     {"type": ComponentType.SIGNATURE, "confidence": 0.45}],
                )
            return Classification(ComponentType.STAMP, 0.75)

        # Single colour and solid — a monochrome logo and a clean stamp look
        # the same. Report the likelier one and keep the alternative, rather
        # than refusing to answer (R13).
        return Classification(
            ComponentType.LOGO, 0.55,
            [{"type": ComponentType.LOGO, "confidence": 0.55},
             {"type": ComponentType.STAMP, "confidence": 0.45}],
        )

    # ── Rule 3: signature versus handwriting, by word-group count ────────────
    #
    # A signature is a name: one or two groups of connected ink. Handwriting is
    # a sentence: three or more. Density backs the count up, because words
    # written close together can merge into a single group — a signature is a
    # few long strokes, handwriting is many short ones.
    if (
        f.word_groups <= _SIGNATURE_MAX_GROUPS
        and f.component_density < _SIGNATURE_MAX_DENSITY
        and _MIN_INK_FOR_CONTENT <= f.ink_ratio < _SIGNATURE_MAX_INK
        and f.component_area_cv < _SIGNATURE_MAX_AREA_CV
    ):
        return Classification(ComponentType.SIGNATURE, 0.70)

    # Pen strokes that are not a signature are handwriting. This is also the
    # agreed fallback when the two cannot be told apart: a signature read as
    # handwriting is sent for OCR and review, which is recoverable, whereas
    # handwriting read as a signature is never read at all.
    if f.stroke_width_cv > _HANDWRITING_MIN_STROKE_CV:
        return Classification(ComponentType.HANDWRITING, 0.60)

    return Classification(ComponentType.UNKNOWN, 0.30)
