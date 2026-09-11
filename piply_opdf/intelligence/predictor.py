"""
Reading the layout knowledge base back.

The store fills as people review, but until something compares a live region
against what is in it, the knowledge only accumulates — it never pays. This is
the comparison.

**What it is allowed to do.** It answers "have people seen regions like this,
and what did they call them?" That answer becomes the `knowledge_agreement`
signal, one of six inputs to a confidence score. It is evidence.

**What it is not allowed to do.** It does not change a region's type. Ever. The
governing principle is that a match can never override the geometry, and the
shape of that rule here is simple: this module returns findings, and the only
consumer is a confidence signal. A predictor that could relabel a region would
be a way for one wrong human decision to propagate silently through every
document that followed, which is the exact failure the store's "only humans
teach it" rule exists to prevent — reintroduced at the other end.

**Why absence proves nothing yet.** With a few dozen records, a region matching
nothing means the store is sparse, not that the region is odd. So a non-match
returns *unmeasured*, not *low*. That changes once the store is dense and Phase
E can say what "no match among five hundred" is worth; until then, claiming it
as evidence against would be inventing a measurement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Sequence

from piply_opdf.knowledge.layout import LayoutFeatures
from piply_opdf.knowledge.store import StoredLayout

__all__ = ["Match", "LayoutPredictor", "similarity", "GROUP_WEIGHTS"]

#: How much each group of features counts toward similarity.
#:
#: **Relationships and geometry lead**, because they are what transfers. A logo
#: is a colourful blob *in a corner, above a heading*; a header row is text
#: *above rows sharing its column edges*. Strip the neighbours out and every
#: wide dark strip near the top of a page looks alike.
#:
#: **Appearance counts less** because it moves with content: the same field on
#: two invoices holds different words, so its ink ratio and stroke width differ
#: for reasons that say nothing about what kind of region it is.
#:
#: **Shape counts least.** Measured: a region pHash reads layout rather than
#: content, so two unrelated text blocks with the same line count sit six bits
#: apart. Useful as a tiebreak, dangerous as a primary signal.
#:
#: Argued, not fitted — the same caveat as the confidence weights. These move
#: once there is a corpus to move them against.
GROUP_WEIGHTS: dict[str, float] = {
    "relationships": 3.0,
    "geometry": 3.0,
    "appearance": 2.0,
    "shape": 1.0,
}

#: Positions closer than this fraction of the page are treated as the same
#: place, and the score falls to zero at this distance. A tenth of a page is
#: about 25mm on A4 — wide enough to absorb a different number of rows above a
#: field, tight enough that the top and the middle of a page do not agree.
_POSITION_TOLERANCE = 0.1

#: Below this, a record is not offered as a match at all. Deliberately high:
#: the dangerous failure for this subsystem is not missing a match, it is
#: announcing one that is wrong, because a confident wrong answer stops anybody
#: looking again.
DEFAULT_MIN_SIMILARITY = 0.7


@dataclass(frozen=True, slots=True)
class Match:
    """One stored record that resembles the region being asked about."""

    stored: StoredLayout
    score: float
    #: Per-group similarity, so a match can be argued with rather than
    #: believed. Groups neither record could supply are absent.
    groups: dict[str, float]

    @property
    def component_type(self) -> str:
        return self.stored.features.component_type

    def why(self) -> str:
        parts = ", ".join(f"{name} {value:.2f}"
                          for name, value in sorted(self.groups.items()))
        return (f"{self.score:.0%} like a {self.component_type} confirmed in "
                f"{self.stored.provenance.source_document or 'an earlier document'} "
                f"({parts})")


class LayoutPredictor:
    """Compares a region against what people have confirmed before."""

    def __init__(
        self,
        store: Any,
        *,
        min_similarity: float = DEFAULT_MIN_SIMILARITY,
    ) -> None:
        self.store = store
        self.min_similarity = min_similarity

    def match(
        self, features: LayoutFeatures, *, limit: int = 5,
    ) -> list[Match]:
        """Records resembling *features*, best first.

        Searched across **all** types, not just the one claimed. The useful
        case is precisely the one where the claim is wrong: a region called
        `PARAGRAPH` that looks like every confirmed `HEADING` is worth knowing
        about, and filtering by the claimed type would hide it.

        Only records at the current feature version are considered — `store`
        enforces that, because features built by a different extractor are not
        comparable.
        """
        found = [
            Match(record, *_score_against(features, record.features))
            for record in self.store.candidates()
        ]
        strong = [m for m in found if m.score >= self.min_similarity]
        strong.sort(key=lambda m: -m.score)
        return strong[:limit]

    def verdict(self, features: LayoutFeatures) -> tuple[float | None, str]:
        """A ``(value, reason)`` pair for the `knowledge_agreement` signal.

        Three outcomes, and the middle one is the point of the whole module:

        * Nothing comparable in the store — **unmeasured**. With a sparse store
          a non-match says nothing about the region.
        * The best match agrees with the claimed type — its similarity, as
          evidence for.
        * The best match is a *different* type — evidence **against**, because
          people have already decided what regions like this are. Scored low
          enough to register as a contradiction.
        """
        matches = self.match(features, limit=1)
        if not matches:
            total = len(self.store.candidates())
            if not total:
                return None, "nothing has been confirmed yet"
            return None, (
                f"none of the {total} confirmed regions resemble this one — "
                f"too few to read as disagreement"
            )

        best = matches[0]
        if best.component_type == features.component_type:
            return best.score, f"matches a confirmed {best.component_type} ({best.score:.0%})"

        return round(1.0 - best.score, 4), (
            f"people confirmed regions like this as {best.component_type}, "
            f"not {features.component_type} ({best.score:.0%} alike)"
        )


def similarity(first: LayoutFeatures, second: LayoutFeatures) -> float:
    """How alike two regions are, 0 to 1."""
    return _score_against(first, second)[0]


def _score_against(
    first: LayoutFeatures, second: LayoutFeatures,
) -> tuple[float, dict[str, float]]:
    """Weighted mean over the groups both records could supply.

    A group neither side has is skipped rather than scored zero — the same rule
    the confidence score follows, and for the same reason: a record described
    from geometry alone is not *unlike* one with appearance measured, it is
    simply quieter.
    """
    groups: dict[str, float] = {}

    groups["geometry"] = _geometry_similarity(first, second)
    groups["relationships"] = _relationship_similarity(first, second)

    appearance = _appearance_similarity(first, second)
    if appearance is not None:
        groups["appearance"] = appearance

    shape = _shape_similarity(first, second)
    if shape is not None:
        groups["shape"] = shape

    total = sum(GROUP_WEIGHTS[name] * value for name, value in groups.items())
    weight = sum(GROUP_WEIGHTS[name] for name in groups)
    return (round(total / weight, 4) if weight else 0.0), groups


def _geometry_similarity(first: LayoutFeatures, second: LayoutFeatures) -> float:
    """Same place, same size, same band."""
    placement = [
        _within(first.rel_x, second.rel_x),
        _within(first.rel_y, second.rel_y),
        _within(first.rel_w, second.rel_w),
        _within(first.rel_h, second.rel_h),
    ]
    band = _band_similarity(first.page_band, second.page_band)
    return round((sum(placement) / len(placement) + band) / 2, 4)


def _within(a: float, b: float) -> float:
    """1.0 at the same position, falling linearly to 0 at the tolerance."""
    return max(0.0, 1.0 - abs(a - b) / _POSITION_TOLERANCE)


def _band_similarity(first: str, second: str) -> float:
    from piply_opdf.knowledge.layout import PAGE_BANDS

    if first == second:
        return 1.0
    try:
        gap = abs(PAGE_BANDS.index(first) - PAGE_BANDS.index(second))
    except ValueError:
        return 0.0
    return 0.5 if gap == 1 else 0.0       # one band off is a near miss


def _relationship_similarity(first: LayoutFeatures, second: LayoutFeatures) -> float:
    """What is around it — the signal that actually transfers.

    Two regions with *nothing* above them agree about that, so matching Nones
    counts as agreement rather than as a gap. A region at the top of a page and
    a region with a table above it genuinely differ.
    """
    slots = ("parent_type", "above_type", "below_type", "left_type", "right_type")
    matches = sum(
        1.0 for slot in slots
        if getattr(first, slot) == getattr(second, slot)
    )

    alignment = (
        _count_similarity(first.aligns_left_with, second.aligns_left_with)
        + _count_similarity(first.aligns_right_with, second.aligns_right_with)
    ) / 2

    return round((matches / len(slots) + alignment) / 2, 4)


def _count_similarity(a: int, b: int) -> float:
    """Two counts, compared relatively — 3 and 4 are alike, 0 and 4 are not."""
    if a == b:
        return 1.0
    return 1.0 - abs(a - b) / float(max(a, b, 1))


def _appearance_similarity(
    first: LayoutFeatures, second: LayoutFeatures,
) -> float | None:
    """How the ink looks. ``None`` when either side was never measured."""
    if not (first.has_appearance and second.has_appearance):
        return None

    scores = [
        _relative(first.ink_ratio, second.ink_ratio),
        _relative(first.stroke_width_cv, second.stroke_width_cv),
        _relative(first.component_density, second.component_density),
        _count_similarity(first.colour_clusters or 0, second.colour_clusters or 0),
    ]
    return round(sum(scores) / len(scores), 4)


def _relative(a: float | None, b: float | None) -> float:
    """Scale-free closeness of two positive measures.

    Relative rather than absolute because these quantities live on wildly
    different scales — ink ratio is a fraction, component density is hundreds
    per megapixel — and a single absolute tolerance would be meaningless for
    one of them and useless for the other.
    """
    if a is None or b is None:
        return 0.0
    total = abs(a) + abs(b)
    if total == 0:
        return 1.0                         # both zero is agreement, not a gap
    return 1.0 - abs(a - b) / total


def _shape_similarity(
    first: LayoutFeatures, second: LayoutFeatures,
) -> float | None:
    """Perceptual hash and moment invariants, when both records carry them."""
    scores: list[float] = []

    if first.region_phash and second.region_phash:
        from piply_opdf.utils.hash import hash_distance

        try:
            bits = hash_distance(first.region_phash, second.region_phash)
            scores.append(max(0.0, 1.0 - bits / 64.0))
        except Exception:
            pass

    moments = _moment_similarity(first.hu_moments, second.hu_moments)
    if moments is not None:
        scores.append(moments)

    return round(sum(scores) / len(scores), 4) if scores else None


def _moment_similarity(first: str | None, second: str | None) -> float | None:
    if not first or not second:
        return None
    try:
        a, b = json.loads(first), json.loads(second)
    except (ValueError, TypeError):
        return None
    if len(a) != len(b) or not a:
        return None
    return sum(_relative(x, y) for x, y in zip(a, b)) / len(a)
