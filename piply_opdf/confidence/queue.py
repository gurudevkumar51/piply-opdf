"""
Who a person should look at first.

The screen today offers "review everything below 95%", which on a real page
selects 167 of 202 components — a list nobody works through, so in practice
nothing is reviewed at all. A threshold is the wrong control while the score is
a ranking rather than a probability: it asks a question the number cannot yet
answer ("which of these are probably wrong?") instead of the one it can
("which of these are weakest?").

So the primary control here is **capacity**. An operator has an hour; the queue
returns the twenty regions worth that hour, worst first. That is answerable
from a ranking, and it stays answerable after calibration.

:func:`spread` exists to keep this honest. A ranking is only useful if the
scores actually separate — if every component lands within a hair of every
other, the queue is arbitrary no matter how it is sorted, and you should be
told rather than left to assume the ordering means something.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from piply_opdf.confidence.evidence import Confidence
from piply_opdf.core.types import DetectedComponent

__all__ = ["Reviewable", "review_queue", "spread"]


@dataclass(frozen=True, slots=True)
class Reviewable:
    """One region and the case for looking at it."""

    component: DetectedComponent
    confidence: Confidence

    @property
    def score(self) -> float:
        return self.confidence.score

    @property
    def contradicted(self) -> bool:
        return bool(self.confidence.contradictions)

    def why(self) -> str:
        return self.confidence.why()


def review_queue(
    assessed: Iterable[tuple[DetectedComponent, Confidence]],
    *,
    capacity: int | None = None,
    below: float | None = None,
) -> list[Reviewable]:
    """Order regions worst-first, and optionally cut the list.

    **Contradicted regions come first**, ahead of everything else, whatever
    their average. A component with five agreeable signals and one saying 0.1
    has something specific wrong with it, and that is a better use of a
    person's attention than the next region down a smooth ranking.

    ``capacity`` takes the worst N — the honest control while the score is a
    ranking. ``below`` applies a threshold as well, for callers that genuinely
    want one; passing both takes the worst N *of those* below the line.
    """
    items = [Reviewable(component, confidence) for component, confidence in assessed]

    if below is not None:
        items = [item for item in items if item.confidence.needs_review(below)]

    # Contradiction first, then weakest first. Python's sort is stable, so
    # equal scores keep the order the caller supplied — normally reading order,
    # which is what an operator expects to work through.
    items.sort(key=lambda item: (not item.contradicted, item.score))

    if capacity is not None:
        items = items[:max(0, capacity)]
    return items


@dataclass(frozen=True, slots=True)
class Spread:
    """How well a set of scores separates."""

    count: int
    lowest: float
    highest: float
    #: Mean absolute deviation from the mean. Chosen over standard deviation
    #: because it is not dominated by one outlier, and here a single very low
    #: score should not make a flat set look varied.
    variation: float

    @property
    def is_useful(self) -> bool:
        """Whether ranking by these scores tells you anything.

        The failure this catches is the one being replaced: when every value is
        a literal, the scores bunch, and a queue sorted by them is arbitrary
        dressed as considered.
        """
        return self.count > 1 and self.variation >= _MIN_USEFUL_VARIATION

    def summary(self) -> str:
        verdict = "usable ranking" if self.is_useful else "scores are too alike to rank"
        return (f"{self.count} components, {self.lowest:.2f}–{self.highest:.2f}, "
                f"variation {self.variation:.3f} — {verdict}")


#: Below this average spread, the ordering is noise. 0.02 on a 0–1 scale means
#: a typical component sits within two points of the average — closer together
#: than any threshold could meaningfully cut.
_MIN_USEFUL_VARIATION = 0.02


def spread(confidences: Sequence[Confidence]) -> Spread:
    """Measure whether these scores separate enough to be worth sorting."""
    scores = [c.score for c in confidences]
    if not scores:
        return Spread(count=0, lowest=0.0, highest=0.0, variation=0.0)

    mean = sum(scores) / len(scores)
    variation = sum(abs(s - mean) for s in scores) / len(scores)
    return Spread(
        count=len(scores),
        lowest=min(scores),
        highest=max(scores),
        variation=variation,
    )
