"""
The fusion rules.

See the package docstring for why fusion exists at all. This module is the
mechanics: match regions, decide what each match means, and record the reasoning
on every component that comes out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from piply_opdf.core.types import BBox, ComponentType, DetectedComponent

__all__ = ["FusionOutcome", "fuse", "specificity", "SPECIFICITY"]

#: Two regions are the same region above this overlap. Deliberately generous:
#: a trained model and a rule-based detector draw boundaries differently — the
#: model wraps a paragraph loosely, the rules hug the ink — so demanding a tight
#: match would call every pair a disagreement.
DEFAULT_MIN_OVERLAP = 0.5

#: ...but overlap alone is not enough. A sentence sitting *inside* a table
#: overlaps it completely, and without this guard the first small component
#: inside a large region claims it as a match.
#:
#: Found by running it: on `Sbizhub_C2219080509040.pdf` the model's two table
#: regions — the borderless statement the rules miss entirely — were each
#: swallowed by a sentence inside them, so the one finding worth having was
#: reported as "already known". Two boxes are the same region only when they
#: are also comparable in size; otherwise one contains the other, which is
#: nesting, not disagreement.
DEFAULT_MIN_SIZE_RATIO = 0.4

#: How specific a type is. When two detectors describe the same region, the more
#: specific answer is more useful: "key-value pair" tells an operator more than
#: "text", and a wrong specific answer is easier to spot than a vague one.
#:
#: The baseline model only ever produces the generic end of this scale, so in
#: practice this encodes "Piply's specialities beat the model's generalities,
#: and the model's headings beat having nothing".
SPECIFICITY: dict[str, int] = {
    ComponentType.UNKNOWN: 0,
    ComponentType.PARAGRAPH: 1,
    ComponentType.SENTENCE: 2,
    ComponentType.IMAGE: 2,
    ComponentType.HEADER: 3,
    ComponentType.FOOTER: 3,
    ComponentType.TITLE: 3,
    ComponentType.HEADING: 3,
    ComponentType.SUBHEADING: 3,
    ComponentType.LIST_ITEM: 4,
    ComponentType.SEPARATOR: 4,
    ComponentType.TABLE: 5,
    ComponentType.BORDERLESS_TABLE: 5,
    ComponentType.PANEL: 5,
    ComponentType.LOGO: 5,
    ComponentType.STAMP: 5,
    ComponentType.SIGNATURE: 5,
    ComponentType.HANDWRITING: 5,
    # The most specific thing either side produces: a named field.
    ComponentType.KEY_VALUE: 6,
}

#: Confidence multiplier when both detectors agree. Capped at 1.0 by the caller.
_AGREEMENT_BOOST = 1.15

#: Confidence for a component both detectors claimed but named differently.
#: Low on purpose — it is going to a person either way.
_DISAGREEMENT_CONFIDENCE = 0.45


def specificity(component_type: str) -> int:
    """How specific a type is. Unknown types sort as least specific."""
    return SPECIFICITY.get(component_type, 0)


@dataclass
class FusionOutcome:
    """What came out, and what happened along the way."""

    components: list[DetectedComponent] = field(default_factory=list)
    agreed: int = 0
    disagreed: int = 0
    baseline_only: int = 0
    piply_only: int = 0

    @property
    def needs_review(self) -> list[DetectedComponent]:
        return [c for c in self.components if c.metadata.get("fusion_review")]

    def summary(self) -> str:
        return (
            f"{len(self.components)} components: {self.agreed} agreed, "
            f"{self.disagreed} disagreed, {self.baseline_only} baseline only, "
            f"{self.piply_only} rules only"
        )


def fuse(
    piply: list[DetectedComponent],
    baseline: list[DetectedComponent],
    *,
    min_overlap: float = DEFAULT_MIN_OVERLAP,
    min_size_ratio: float = DEFAULT_MIN_SIZE_RATIO,
) -> FusionOutcome:
    """Combine two sets of detections for one page.

    Piply's components are the spine: they carry children, text and everything
    the rules worked out. The baseline either confirms one, disagrees with one,
    or contributes a region nobody else found.
    """
    outcome = FusionOutcome()
    matched_baseline: set[int] = set()

    for component in piply:
        index = _best_match(
            component, baseline, matched_baseline, min_overlap, min_size_ratio
        )

        if index is None:
            component.metadata["fusion"] = "rules only"
            outcome.piply_only += 1
            outcome.components.append(component)
            continue

        matched_baseline.add(index)
        other = baseline[index]

        if other.type == component.type:
            _mark_agreement(component, other)
            outcome.agreed += 1
        else:
            _mark_disagreement(component, other)
            outcome.disagreed += 1

        outcome.components.append(component)

    # Regions only the model found. A borderless table the rules missed lives
    # here, and it is the main reason the baseline is worth running.
    for index, region in enumerate(baseline):
        if index in matched_baseline:
            continue
        region.metadata["fusion"] = "baseline only"
        outcome.baseline_only += 1
        outcome.components.append(region)

    return outcome


def _best_match(
    component: DetectedComponent,
    baseline: list[DetectedComponent],
    taken: set[int],
    min_overlap: float,
    min_size_ratio: float,
) -> int | None:
    """Index of the baseline region describing the same area, if any.

    Both tests have to pass: the boxes must overlap, **and** be comparable in
    size. Overlap alone confuses "these are the same thing" with "one is inside
    the other".
    """
    best_index, best_overlap = None, min_overlap
    for index, region in enumerate(baseline):
        if index in taken:
            continue
        if _size_ratio(component.bbox, region.bbox) < min_size_ratio:
            continue                                # containment, not identity
        overlap = _mutual_overlap(component.bbox, region.bbox)
        if overlap > best_overlap:
            best_index, best_overlap = index, overlap
    return best_index


def _size_ratio(first: BBox, second: BBox) -> float:
    """Smaller area over larger. 1.0 means the same size, near 0 means nested."""
    if not first.area or not second.area:
        return 0.0
    return min(first.area, second.area) / float(max(first.area, second.area))


def _mutual_overlap(first: BBox, second: BBox) -> float:
    """Overlap as a share of the *smaller* box.

    Not intersection-over-union: the model wraps a paragraph loosely while the
    rules hug the ink, so IoU punishes a pair that plainly describes the same
    region. What matters is whether one sits inside the other.
    """
    if not first.area or not second.area:
        return 0.0
    return first.intersection_area(second) / float(min(first.area, second.area))


def _mark_agreement(component: DetectedComponent, other: DetectedComponent) -> None:
    """Two independent detectors said the same thing. That is evidence."""
    component.confidence = min(1.0, component.confidence * _AGREEMENT_BOOST)
    component.metadata["fusion"] = "agreed"
    component.metadata["baseline_agreed"] = True
    component.metadata["model_confidence"] = other.metadata.get("model_confidence")


def _mark_disagreement(component: DetectedComponent, other: DetectedComponent) -> None:
    """Both claimed the region and named it differently.

    The more specific type wins, because it says more and a wrong specific
    answer is easier for a person to spot than a vague one. But the component is
    **flagged**, and both opinions are kept: this is exactly the case the
    governing principle is about.
    """
    mine, theirs = specificity(component.type), specificity(other.type)
    rejected = component.type

    if theirs > mine:
        component.type = other.type
        component.metadata["fusion_winner"] = "baseline"
    else:
        component.metadata["fusion_winner"] = "rules"

    component.confidence = _DISAGREEMENT_CONFIDENCE
    component.metadata["fusion"] = "disagreed"
    component.metadata["fusion_review"] = True
    component.candidates = [
        {"type": component.type, "confidence": _DISAGREEMENT_CONFIDENCE},
        {
            "type": other.type if component.type == rejected else rejected,
            "confidence": round(1.0 - _DISAGREEMENT_CONFIDENCE, 2),
        },
    ]
