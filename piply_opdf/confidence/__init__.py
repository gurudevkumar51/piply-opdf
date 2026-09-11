"""
Confidence, derived from evidence rather than written as a literal.

The problem this replaces: every confidence a detector produces is a constant
in the source. A paragraph is 0.70, a logo is 0.85, and each means only "this
rule fired" — so nothing anywhere says *why* a region scored what it did, and
two regions scoring alike may be alike in no other way.

Downstream, the review screen cuts at 0.95 and selects 167 of 202 components on
`sample.pdf`. A list that long is a list nobody works through.

The three pieces:

``evidence``
    Six named signals, how they combine, and the rule that missing is not zero.

``signals``
    Where each signal comes from. Four are measurable today; knowledge
    agreement and historical reliability wait on data that does not exist yet
    and say so, rather than scoring zero.

``queue``
    Who to look at first. Capacity-based, because "the worst twenty" is
    answerable from a ranking and "everything probably wrong" is not.

**The score is a ranking, not a probability.** Fitting it so that 0.90 means
right nine times in ten needs the labelled corpus from Phase E.
``Confidence.calibrated`` is ``False`` everywhere until then, and callers
should read it rather than assume.
"""

from .evidence import (
    ALARM_BELOW,
    REVIEW_BELOW,
    WEIGHTS,
    Confidence,
    Signal,
    SignalKind,
    score,
)
from .queue import Reviewable, Spread, review_queue, spread
from .signals import (
    assess,
    detector_signal,
    geometry_signal,
    historical_signal,
    knowledge_signal,
    model_signal,
    signals_for,
    structural_signal,
)

__all__ = [
    # the model
    "Signal",
    "SignalKind",
    "Confidence",
    "score",
    "WEIGHTS",
    "REVIEW_BELOW",
    "ALARM_BELOW",
    # gathering
    "assess",
    "signals_for",
    "detector_signal",
    "geometry_signal",
    "knowledge_signal",
    "structural_signal",
    "historical_signal",
    "model_signal",
    # using it
    "review_queue",
    "Reviewable",
    "spread",
    "Spread",
]
