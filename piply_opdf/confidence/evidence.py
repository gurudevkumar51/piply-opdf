"""
Confidence as an evidence score.

Every confidence a *detector* produces is a **literal written in the code** — a
paragraph is always 0.70, a logo always 0.85. Each one means one thing: *this
rule fired*. They are not wrong so much as empty: two paragraphs on the same
page score identically whether one is a clean block of text and the other is a
misread strip of table.

A measurement, so this is not an assumption. On `sample.pdf` the components
already carry 45 distinct values between 0.25 and 1.0 — so they are not all
identical. But the ones that vary are grid cells, whose number comes from the
grid builder; the detector-level regions are literals, and nothing anywhere
says *why* any of them is what it is. That is the gap this closes.

The replacement is not a better literal. It is a number **derived from named,
itemised evidence**, so that a component's score can be taken apart:

    detector_evidence      0.70   text-layer key-value rule
    geometry_evidence      0.40   separator column is unusually wide
    knowledge_agreement    ——     nothing similar seen
    structural_evidence    0.65   aligned, but only two rows
    historical_reliability 0.88   this rule is usually right
    model_confidence       ——     baseline did not run

Three rules hold this together:

1. **Missing is not zero.** A signal nobody could measure is ``None`` and takes
   no part in the average. Scoring an unmeasured signal as 0 punishes a region
   for the pipeline's gaps rather than its own weakness — the same mistake as
   recording an unmeasured region's ink as 0.0.
2. **A single contradiction outranks a good average.** Five agreeable signals
   and one that says 0.1 is not a 0.75 component; it is a component with
   something wrong with it. The average stays honest, and the *decision* to
   review is taken separately.
3. **This is a ranking, not a probability.** Until the weights are fitted
   against the labelled corpus (Phase E), a score of 0.9 does not mean "right
   nine times out of ten". It means "stronger evidence than a 0.6". Every
   consumer is told which it is holding, and nothing here pretends otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

__all__ = [
    "SignalKind",
    "Signal",
    "Confidence",
    "WEIGHTS",
    "REVIEW_BELOW",
    "score",
]


class SignalKind:
    """The six things confidence is made of."""

    #: How strongly the rule or model that proposed this region fired. Today
    #: this is the literal the detector carries — kept, because "this rule
    #: fired" is genuine evidence. It is just not the *only* evidence.
    DETECTOR = "detector_evidence"

    #: Does the shape agree with the claimed type? A header that is not near
    #: the top, a separator that is not a line.
    GEOMETRY = "geometry_evidence"

    #: Does the layout knowledge base concur? This one traces back to a human
    #: decision, which is why it is weighted as heavily as the detector.
    KNOWLEDGE = "knowledge_agreement"

    #: Do the ink, rules and alignment support the type — measured from the
    #: image rather than assumed from the rule that fired.
    STRUCTURAL = "structural_evidence"

    #: How often this detector has been right about this type before.
    HISTORICAL = "historical_reliability"

    #: The baseline model's own score, when a model ran at all.
    MODEL = "model_confidence"

    ALL: tuple[str, ...] = (
        DETECTOR, GEOMETRY, KNOWLEDGE, STRUCTURAL, HISTORICAL, MODEL,
    )


#: How much each signal counts.
#:
#: These are **starting weights, not fitted ones**. Each is argued rather than
#: measured, and every one of them is expected to move once the labelled corpus
#: exists. What matters now is that they are visible and few.
#:
#: * ``DETECTOR`` and ``KNOWLEDGE`` weigh most. The first is the reasoning that
#:   produced the answer; the second is a person having agreed with it before,
#:   and human agreement is the only thing this system treats as truth.
#: * ``GEOMETRY``, ``STRUCTURAL`` and ``MODEL`` are independent checks on that
#:   answer, each worth less alone than the claim they are checking.
#: * ``HISTORICAL`` weighs least **on purpose**. A detector that has been right
#:   90% of the time is not thereby right about *this* region, and letting a
#:   good track record carry the score would hide exactly the regions where a
#:   reliable detector went wrong.
WEIGHTS: dict[str, float] = {
    SignalKind.DETECTOR: 3.0,
    SignalKind.KNOWLEDGE: 3.0,
    SignalKind.GEOMETRY: 2.0,
    SignalKind.STRUCTURAL: 2.0,
    SignalKind.MODEL: 2.0,
    SignalKind.HISTORICAL: 1.0,
}

#: Default cutoff for "send this to a person". Pre-calibration this is a
#: **ranking cutoff**, not a probability: it decides who goes to the front of
#: the queue, and it is chosen to be re-derived once Phase E can say what a
#: given score is actually worth. Prefer :func:`piply_opdf.confidence.queue.
#: review_queue` where review capacity is what is really limited.
REVIEW_BELOW = 0.75

#: A single signal this low is not a weak vote — it is a contradiction. One is
#: enough to send a region to a person no matter how agreeable the rest are,
#: because the failure worth preventing is *confidently wrong and unreviewed*.
ALARM_BELOW = 0.35


@dataclass(frozen=True, slots=True)
class Signal:
    """One piece of evidence, and why it says what it says."""

    kind: str
    #: ``None`` means "could not be measured", which is not the same as 0.0 and
    #: is never averaged in as though it were.
    value: float | None
    reason: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SignalKind.ALL:
            raise ValueError(
                f"unknown signal {self.kind!r}; expected one of "
                f"{', '.join(SignalKind.ALL)}"
            )
        if self.value is not None and not 0.0 <= self.value <= 1.0:
            raise ValueError(f"{self.kind} must be between 0 and 1, got {self.value}")

    @property
    def measured(self) -> bool:
        return self.value is not None


@dataclass(frozen=True, slots=True)
class Confidence:
    """A score, everything it was built from, and what to do about it."""

    score: float
    signals: tuple[Signal, ...] = ()
    #: Whether the weights behind ``score`` have been fitted against labelled
    #: data. ``False`` everywhere today: read ``score`` as a ranking.
    calibrated: bool = False

    @property
    def measured_signals(self) -> tuple[Signal, ...]:
        return tuple(s for s in self.signals if s.measured)

    @property
    def contradictions(self) -> tuple[Signal, ...]:
        """Signals low enough to overrule an agreeable average."""
        return tuple(
            s for s in self.measured_signals if s.value is not None
            and s.value < ALARM_BELOW
        )

    def needs_review(self, below: float = REVIEW_BELOW) -> bool:
        """Whether a person should look at this.

        Deliberately separate from the score. Distorting the number to force a
        review would make the number a worse ranking *and* a worse
        explanation; the decision is its own thing.
        """
        return self.score < below or bool(self.contradictions)

    def why(self) -> str:
        """The operator's answer to "why is this only 0.55?".

        Unmeasured signals are printed as ``——`` rather than omitted, because
        "nothing similar has been seen before" is itself worth knowing.
        """
        lines = []
        for kind in SignalKind.ALL:
            signal = next((s for s in self.signals if s.kind == kind), None)
            if signal is None or signal.value is None:
                lines.append(f"  {kind:<22} ——     "
                             f"{signal.reason if signal else 'not measured'}")
            else:
                lines.append(f"  {kind:<22} {signal.value:.2f}   {signal.reason}")

        header = f"{self.score:.2f}" + ("" if self.calibrated else "  (ranking, not a probability)")
        return header + "\n" + "\n".join(lines)

    def as_metadata(self) -> dict[str, object]:
        """The shape stored on a component, per the governing principle.

        The evidence travels with the answer. A score with its reasoning thrown
        away cannot be argued with, and an operator who cannot argue with it
        will either trust it blindly or ignore it entirely.
        """
        return {
            "score": round(self.score, 4),
            "calibrated": self.calibrated,
            "signals": {
                s.kind: {"value": s.value, "reason": s.reason} for s in self.signals
            },
        }


def score(signals: Iterable[Signal], *, calibrated: bool = False) -> Confidence:
    """Combine evidence into one number.

    A weighted mean over the signals that could actually be measured. Not a
    product, which drives everything toward zero as more checks are added and
    so punishes thoroughness; not a minimum, which throws away every signal but
    one.

    With no measurable evidence at all the score is 0.0 — the correct answer,
    since a region nobody could say anything about is precisely one a person
    should see.
    """
    collected = tuple(signals)
    _reject_duplicates(collected)

    total = weight_used = 0.0
    for signal in collected:
        if signal.value is None:
            continue
        weight = WEIGHTS.get(signal.kind, 1.0)
        total += signal.value * weight
        weight_used += weight

    value = total / weight_used if weight_used else 0.0
    return Confidence(score=value, signals=collected, calibrated=calibrated)


def _reject_duplicates(signals: Sequence[Signal]) -> None:
    """Two readings of the same signal would silently double its weight."""
    seen: set[str] = set()
    for signal in signals:
        if signal.kind in seen:
            raise ValueError(f"{signal.kind} given twice")
        seen.add(signal.kind)
