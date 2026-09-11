"""
What the system knows about a *region*, in a form worth storing.

Text knowledge answers "what does this say?". Layout knowledge answers a
different question — **"what kind of region is this?"** — and the answer has to
survive being carried to a document nobody has seen before. That rules out
pixels and page coordinates, and it is why everything here is either a ratio or
a relationship.

Three groups of signal, and the third is the one that earns its keep:

``appearance``
    How the ink looks. Measured by :func:`piply_opdf.classification.measure`,
    the same function the classifier uses — one extractor, so the two cannot
    drift apart and start disagreeing about the same region.

``geometry``
    Where it sits, as a fraction of the page. A header is near the top at 150
    DPI and near the top at 400 DPI; it is at y=180 in neither sense that
    transfers.

``relationships``
    What is around it. This is what makes a record reusable rather than a
    description of one page: a logo is a colourful blob *in a corner, above a
    heading*; a header row is text *above rows sharing its column edges*. Take
    the neighbours away and every wide dark strip near the top looks alike.

Nothing here needs an image. Geometry and relationships are arithmetic on
boxes, so a region can be described — and matched — on a page whose crops were
never kept.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Mapping, Sequence

from piply_opdf.core.types import BBox, DetectedComponent

__all__ = [
    "LayoutFeatures",
    "PAGE_BANDS",
    "describe",
    "describe_page",
    "page_band",
    "to_json",
]

#: Coarse vertical position, in reading order. Five bands rather than three:
#: with three, a title at 20% of the page and a table at 45% both land in
#: "middle", which throws away the one thing that separates them.
#:
#: The outer edges are 0.15 and 0.85 because that is where headers and footers
#: conventionally live, so "top" means "the band headers occupy" rather than an
#: arbitrary fifth.
PAGE_BANDS = ("top", "upper", "middle", "lower", "bottom")

_BAND_EDGES: tuple[tuple[float, str], ...] = (
    (0.15, "top"),
    (0.40, "upper"),
    (0.60, "middle"),
    (0.85, "lower"),
)

#: A neighbour must cover at least this share of **the region asking**.
#:
#: Measured against the asker, not against the smaller of the two, and the
#: asymmetry is the point. A page number in the right margin covers 2% of a
#: full-width table, so the table does not call it a neighbour; the same table
#: covers all of the page number, so the page number does call it one. That is
#: how the relationship actually reads on the page.
#:
#: Measuring against the smaller box instead — the obvious first choice, and
#: what fusion uses for a different job — makes every narrow region a neighbour
#: of every wide one it brushes past, because a small box is nearly always
#: mostly inside a large one's span.
_MIN_SPAN_OVERLAP = 0.2

#: Edges within this fraction of the page dimension are treated as aligned.
#: 0.5% is about 12px on a 2480px-wide A4 scan at 300 DPI — tight enough to
#: mean something, loose enough to survive a scanner's drift.
_ALIGNMENT_TOLERANCE = 0.005


@dataclass(frozen=True, slots=True)
class LayoutFeatures:
    """One region, described so it can be recognised somewhere else."""

    component_type: str

    # ── geometry, normalised so page size and DPI do not matter ──────────────
    rel_x: float
    rel_y: float
    rel_w: float
    rel_h: float
    page_band: str
    #: width / height of the box. Defined even when no crop was available.
    aspect_ratio: float

    # ── relationships ───────────────────────────────────────────────────────
    parent_type: str | None = None
    above_type: str | None = None
    below_type: str | None = None
    left_type: str | None = None
    right_type: str | None = None
    #: How many siblings share this region's left / right edge.
    aligns_left_with: int = 0
    aligns_right_with: int = 0

    # ── appearance, from classification.measure ─────────────────────────────
    #: ``None`` throughout when no crop was supplied. Absent is recorded as
    #: absent rather than as zero: a region with no ink and a region nobody
    #: measured are not the same thing, and averaging them together would be a
    #: quiet lie.
    ink_ratio: float | None = None
    stroke_width_cv: float | None = None
    component_density: float | None = None
    baseline_scatter: float | None = None
    colour_clusters: int | None = None

    # ── shape, for recognising a region somewhere else ──────────────────────
    #: Perceptual hash of the region's pixels — a **structural** signature,
    #: not an identity.
    #:
    #: Measured rather than assumed: rescaling a region by 2x moves it 2-4 bits
    #: of 64, and an empty region sits 26 bits away. But two text blocks with
    #: *different words* and the same three-line layout sit only 6 bits apart,
    #: because a DCT over the low frequencies sees the arrangement of light and
    #: dark, not the letters.
    #:
    #: So it answers "is this laid out like that one?" and must not be read as
    #: "is this the same region?". For identity, the text knowledge base hashes
    #: a much smaller crop, where the letters *are* the low frequencies.
    region_phash: str | None = None
    #: Hu's seven moment invariants of the ink, log-scaled. Invariant to
    #: position, scale and rotation, so unlike a hash they *do* carry across
    #: documents: they describe how a region's ink is distributed rather than
    #: what it says.
    hu_moments: str | None = None

    # HOG is deliberately absent. It is 1,764 floats per region, and the text
    # knowledge base shows what that costs when stored as JSON: 41 MB of its
    # 44 MB is the `hog_features` column alone, about 26 KB a row for 1,656
    # rows. A descriptor that large belongs in a training export, not in a
    # store meant to be small enough to hand to somebody.

    @property
    def has_appearance(self) -> bool:
        """Whether this record was measured from an image."""
        return self.ink_ratio is not None

    def as_row(self) -> dict[str, Any]:
        """Flatten to the store's column names."""
        return asdict(self)


def page_band(relative_y: float) -> str:
    """Which band a normalised y-position falls in."""
    for edge, name in _BAND_EDGES:
        if relative_y < edge:
            return name
    return "bottom"


def describe_page(
    components: Sequence[DetectedComponent],
    page_size: tuple[int, int],
    *,
    crops: Mapping[str, Any] | None = None,
) -> list[tuple[DetectedComponent, LayoutFeatures]]:
    """Describe every component on a page, including nested ones.

    Returns ``(component, features)`` pairs rather than bare features, because
    storing a record needs both: the features are the knowledge, and the
    component carries the detector that proposed it, which goes into the
    version block. Returning features alone would leave every caller
    re-walking the tree in parallel and trusting the two walks to stay in step.

    ``page_size`` is ``(width, height)`` in the same pixel frame as the boxes.
    ``crops`` maps component id to an image array; components missing from it
    are described from geometry alone.

    Relationships are worked out **among siblings** — the children of a table
    are positioned against each other, not against things outside the table.
    Geometry stays relative to the whole page, so a cell's position is still
    comparable across documents.
    """
    described: list[tuple[DetectedComponent, LayoutFeatures]] = []

    def walk(level: Sequence[DetectedComponent], parent: DetectedComponent | None) -> None:
        for component in level:
            described.append((
                component,
                describe(
                    component,
                    page_size,
                    siblings=level,
                    parent=parent,
                    crop=(crops or {}).get(component.id),
                ),
            ))
            if component.children:
                walk(component.children, component)

    walk(components, None)
    return described


def describe(
    component: DetectedComponent,
    page_size: tuple[int, int],
    *,
    siblings: Iterable[DetectedComponent] = (),
    parent: DetectedComponent | None = None,
    crop: Any | None = None,
) -> LayoutFeatures:
    """Describe one region. ``crop`` is optional; without it, geometry only."""
    page_width, page_height = page_size
    if page_width <= 0 or page_height <= 0:
        raise ValueError(f"page size must be positive, got {page_size!r}")

    box = component.bbox
    others = [s for s in siblings if s is not component]

    rel_y = box.y / page_height
    centre_y = box.center[1] / page_height

    appearance = _appearance(crop)

    return LayoutFeatures(
        component_type=component.type,
        rel_x=_round(box.x / page_width),
        rel_y=_round(rel_y),
        rel_w=_round(box.width / page_width),
        rel_h=_round(box.height / page_height),
        page_band=page_band(centre_y),
        aspect_ratio=_round(box.width / box.height if box.height else 0.0),
        parent_type=parent.type if parent is not None else None,
        above_type=_type_of(_nearest(box, others, "above")),
        below_type=_type_of(_nearest(box, others, "below")),
        left_type=_type_of(_nearest(box, others, "left")),
        right_type=_type_of(_nearest(box, others, "right")),
        aligns_left_with=_aligned_count(box, others, "left", page_width),
        aligns_right_with=_aligned_count(box, others, "right", page_width),
        **appearance,
    )


# ── appearance ───────────────────────────────────────────────────────────────

def _appearance(crop: Any | None) -> dict[str, Any]:
    """The measured signals, or all-``None`` when there is nothing to measure.

    ``measure`` is imported here rather than at module scope so that geometry
    and relationships stay usable without the imaging stack loaded.
    """
    empty: dict[str, Any] = {
        "ink_ratio": None,
        "stroke_width_cv": None,
        "component_density": None,
        "baseline_scatter": None,
        "colour_clusters": None,
        "region_phash": None,
        "hu_moments": None,
    }
    if crop is None:
        return empty

    from piply_opdf.classification import measure

    features = measure(crop)
    if features is None:                      # too small to judge — say so
        return empty

    return {
        "ink_ratio": _round(features.ink_ratio),
        "stroke_width_cv": _round(features.stroke_width_cv),
        "component_density": _round(features.component_density),
        "baseline_scatter": _round(features.baseline_scatter),
        "colour_clusters": features.colour_clusters,
        "region_phash": _region_phash(crop),
        "hu_moments": _hu_moments(crop),
    }


def _region_phash(crop: Any) -> str | None:
    from piply_opdf.utils.hash import phash_array

    try:
        return phash_array(crop)
    except Exception:            # an odd crop is not worth failing a page over
        return None


def _hu_moments(crop: Any) -> str | None:
    """Hu's seven invariants, log-scaled.

    Raw Hu moments span many orders of magnitude, so the sixth and seventh are
    numerically invisible beside the first. The usual log transform, sign
    preserved, puts them on a comparable scale — without it, any distance
    between two records is decided entirely by ``h1``.
    """
    import cv2
    import numpy as np

    from piply_opdf.detectors.common import binarize, to_grayscale

    try:
        binary = binarize(to_grayscale(crop))
        moments = cv2.HuMoments(cv2.moments(binary)).flatten()
        scaled = [
            0.0 if value == 0 else
            float(-np.sign(value) * np.log10(abs(value)))
            for value in moments
        ]
        return json.dumps([round(v, 4) for v in scaled])
    except Exception:
        return None


# ── relationships ────────────────────────────────────────────────────────────

def _nearest(
    box: BBox, others: Sequence[DetectedComponent], direction: str
) -> DetectedComponent | None:
    """The closest region in *direction* that genuinely lines up with *box*.

    "Closest" is measured by the gap between the facing edges, not between
    centres: a tall neighbour and a short one at the same distance are equally
    adjacent, and centre distance would prefer the short one for no reason.
    """
    best: DetectedComponent | None = None
    best_gap: float | None = None

    for other in others:
        gap = _gap(box, other.bbox, direction)
        if gap is None:
            continue
        if best_gap is None or gap < best_gap:
            best, best_gap = other, gap

    return best


def _gap(box: BBox, other: BBox, direction: str) -> float | None:
    """Distance from *box* to *other* in *direction*, or None if not a neighbour."""
    if direction in ("above", "below"):
        if _covered_share(box.x, box.x1, other.x, other.x1) < _MIN_SPAN_OVERLAP:
            return None
        if direction == "above":
            return box.y - other.y1 if other.y1 <= box.y else None
        return other.y - box.y1 if other.y >= box.y1 else None

    if _covered_share(box.y, box.y1, other.y, other.y1) < _MIN_SPAN_OVERLAP:
        return None
    if direction == "left":
        return box.x - other.x1 if other.x1 <= box.x else None
    if direction == "right":
        return other.x - box.x1 if other.x >= box.x1 else None

    raise ValueError(f"unknown direction {direction!r}")


def _covered_share(mine0: float, mine1: float, theirs0: float, theirs1: float) -> float:
    """How much of *my* span the other one covers. See :data:`_MIN_SPAN_OVERLAP`."""
    mine = mine1 - mine0
    if mine <= 0:
        return 0.0
    return max(0.0, min(mine1, theirs1) - max(mine0, theirs0)) / mine


def _aligned_count(
    box: BBox, others: Sequence[DetectedComponent], edge: str, page_width: int
) -> int:
    """How many of *others* share this box's left or right edge."""
    tolerance = page_width * _ALIGNMENT_TOLERANCE
    mine = box.x if edge == "left" else box.x1
    return sum(
        1
        for other in others
        if abs((other.bbox.x if edge == "left" else other.bbox.x1) - mine) <= tolerance
    )


def _type_of(component: DetectedComponent | None) -> str | None:
    return component.type if component is not None else None


def _round(value: float) -> float:
    """Six places. Beyond that is scanner noise stored as if it were signal."""
    return round(float(value), 6)


def to_json(features: LayoutFeatures) -> str:
    """Serialise, for export and for the CLI."""
    return json.dumps(features.as_row(), sort_keys=True)
