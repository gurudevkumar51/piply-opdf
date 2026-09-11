"""
Where each piece of evidence comes from.

:mod:`piply_opdf.confidence.evidence` decides how signals combine. This module
decides what they are, reading whatever the pipeline already produced rather
than asking twenty detectors to change at once.

Four of the six can be measured today. Two — knowledge agreement and
historical reliability — need data that does not exist yet (an empty layout
store, an empty feedback log), so they return ``None``. That is the point of
"missing is not zero": the architecture is right now, and the signals turn on
by themselves as the data arrives, with no code change and no silent penalty
in the meantime.
"""

from __future__ import annotations

from typing import Any, Mapping

from piply_opdf.confidence.evidence import Confidence, Signal, SignalKind, score
from piply_opdf.core.types import ComponentType, DetectedComponent
from piply_opdf.knowledge.layout import describe, page_band

__all__ = [
    "assess",
    "signals_for",
    "detector_signal",
    "geometry_signal",
    "structural_signal",
    "model_signal",
    "knowledge_signal",
    "historical_signal",
]


# ── detector ─────────────────────────────────────────────────────────────────

def detector_signal(component: DetectedComponent) -> Signal:
    """The literal the detector already carries.

    It is kept rather than discarded: "the text-layer key-value rule fired at
    0.85" is real evidence about the region. The change is that it is now *one*
    input with a name, instead of the entire answer wearing a disguise.
    """
    detector = component.metadata.get("detector") or component.metadata.get("strategy")
    reason = f"{detector} rule fired" if detector else "detector rule fired"
    return Signal(SignalKind.DETECTOR, float(component.confidence), reason)


# ── geometry ─────────────────────────────────────────────────────────────────

#: A separator is a ruled line. Below this ratio it is a thin box, which is a
#: different thing. Matches ``_SEPARATOR_MIN_ASPECT`` in the classifier so the
#: two cannot disagree about what a line is.
_LINE_ASPECT = 12.0

#: A container has to be big enough to hold something. 2% of the page in both
#: directions is about 50 x 70px on an A4 scan at 300 DPI — smaller than any
#: real table cell, let alone a table.
_MIN_CONTAINER_SIDE = 0.02

#: Bands next to the expected one. A header in the band below the top is
#: probably still a header on a page with a wide margin; a header in the middle
#: is not.
_ADJACENT_BAND = 0.5
_WRONG_BAND = 0.1


def geometry_signal(
    component: DetectedComponent, page_size: tuple[int, int]
) -> Signal:
    """Does the shape agree with the claimed type?

    Only **definitional** constraints are checked — a header is at the top
    because that is what the word means, a separator is long and thin because a
    rule is a line. Stylistic expectations are deliberately absent: "titles are
    usually centred" is a habit of some documents, and encoding it would turn
    this into a per-layout rule set that fails on the next customer's forms.

    Types with no definitional geometry return ``None``. A paragraph can be any
    shape, and pretending otherwise would invent evidence.
    """
    features = describe(component, page_size)
    kind = component.type

    if kind == ComponentType.HEADER:
        return _band_signal(features.page_band, "top", "upper", "a header sits at the top")
    if kind == ComponentType.FOOTER:
        return _band_signal(features.page_band, "bottom", "lower", "a footer sits at the bottom")

    if kind == ComponentType.SEPARATOR:
        value = min(1.0, features.aspect_ratio / _LINE_ASPECT)
        return Signal(SignalKind.GEOMETRY, value,
                      f"aspect {features.aspect_ratio:.1f}:1 against {_LINE_ASPECT:.0f}:1 for a rule")

    if kind in ComponentType.CONTAINER:
        smaller = min(features.rel_w, features.rel_h)
        value = min(1.0, smaller / _MIN_CONTAINER_SIDE)
        return Signal(SignalKind.GEOMETRY, value,
                      f"shortest side {smaller:.1%} of the page")

    if kind in (ComponentType.KEY_VALUE, ComponentType.TITLE,
                ComponentType.HEADING, ComponentType.SUBHEADING):
        value = min(1.0, features.aspect_ratio)
        return Signal(SignalKind.GEOMETRY, value,
                      f"{features.aspect_ratio:.1f}:1 — a line of text is wider than tall")

    return Signal(SignalKind.GEOMETRY, None, f"no definitional shape for {kind}")


def _band_signal(actual: str, expected: str, adjacent: str, reason: str) -> Signal:
    if actual == expected:
        return Signal(SignalKind.GEOMETRY, 1.0, f"{reason}, and it is in the {actual} band")
    if actual == adjacent:
        return Signal(SignalKind.GEOMETRY, _ADJACENT_BAND,
                      f"{reason}; this one is one band off, in {actual}")
    return Signal(SignalKind.GEOMETRY, _WRONG_BAND,
                  f"{reason}; this one is in the {actual} band")


# ── structural ───────────────────────────────────────────────────────────────

#: The classifier answers a different question from the detectors: it names
#: what the ink *looks like*, not what role the region plays. It has no concept
#: of a header. So "this is text" supports a header claim without confirming
#: it, and this is how much of a confirmation that is worth.
_SAME_FAMILY = 0.8


def structural_signal(component: DetectedComponent, crop: Any | None) -> Signal:
    """Does the ink support the claimed type?

    Measured from the image, independently of whatever rule proposed the
    region. This is the signal that catches a detector firing on the right
    place for the wrong reason.
    """
    if crop is None:
        return Signal(SignalKind.STRUCTURAL, None, "no crop available")

    # A container's ink belongs to its children, and the classifier has no
    # concept of "container" — it names what it sees. Found by running this on
    # `sample.pdf`: a PANEL holding a signature scored 0.30 structural
    # evidence, reason "the ink reads as SIGNATURE, not PANEL". True about the
    # ink, and no evidence at all about the panel claim. Judging a box by its
    # contents would penalise every container for containing something.
    if component.type in ComponentType.CONTAINER:
        return Signal(SignalKind.STRUCTURAL, None,
                      f"a {component.type} is judged by its children, not its own ink")

    from piply_opdf.classification import classify, measure

    verdict = classify(measure(crop))
    if verdict is None or verdict.type == ComponentType.UNKNOWN:
        return Signal(SignalKind.STRUCTURAL, None, "the ink says nothing either way")

    claimed, seen = component.type, verdict.type

    if claimed == seen:
        return Signal(SignalKind.STRUCTURAL, verdict.confidence,
                      f"the ink reads as {seen}, which is what was claimed")

    if _family(claimed) is not None and _family(claimed) == _family(seen):
        return Signal(SignalKind.STRUCTURAL, verdict.confidence * _SAME_FAMILY,
                      f"the ink reads as {seen} — same family as {claimed}, "
                      f"so it supports without confirming")

    return Signal(SignalKind.STRUCTURAL, max(0.0, 1.0 - verdict.confidence),
                  f"the ink reads as {seen}, not {claimed}")


def _family(kind: str) -> str | None:
    if kind in ComponentType.TEXTUAL:
        return "text"
    if kind in ComponentType.GRAPHIC and kind != ComponentType.UNKNOWN:
        return "graphic"
    return None


# ── the baseline model ───────────────────────────────────────────────────────

def model_signal(component: DetectedComponent) -> Signal:
    """The baseline model's own score, when a model ran.

    Fusion records this on components it matched. Absent means the baseline was
    switched off or found nothing there — not that the model disagreed.
    """
    value = component.metadata.get("model_confidence")
    if value is None:
        return Signal(SignalKind.MODEL, None, "baseline did not run on this region")

    agreed = component.metadata.get("baseline_agreed")
    reason = ("the baseline agreed on the type" if agreed
              else "the baseline saw this region")
    return Signal(SignalKind.MODEL, float(value), reason)


# ── the layout knowledge base ────────────────────────────────────────────────

def knowledge_signal(
    component: DetectedComponent,
    page_size: tuple[int, int],
    store: Any | None = None,
) -> Signal:
    """Does the layout knowledge base concur?

    Returns ``None`` today whatever is passed, and the reason is worth stating
    plainly: comparing a live region against stored records is the
    LayoutPredictor, and it does not exist yet (Phase T). The store can be read,
    but nothing can yet say *how close* two records are, and a similarity
    invented here would be a second, competing definition of the same thing.

    What this does check is whether there is anything to compare against at
    all, so an operator sees "nothing similar seen" rather than a silent gap.
    """
    if store is None:
        return Signal(SignalKind.KNOWLEDGE, None, "no layout knowledge base attached")

    known = store.candidates(component.type, limit=1)
    if not known:
        return Signal(SignalKind.KNOWLEDGE, None,
                      f"nothing of type {component.type} has been confirmed before")

    return Signal(SignalKind.KNOWLEDGE, None,
                  "records exist, but matching needs the LayoutPredictor (Phase T)")


# ── track record ─────────────────────────────────────────────────────────────

def historical_signal(
    component: DetectedComponent,
    history: Mapping[str, Any] | None = None,
) -> Signal:
    """How often this detector has been right about this type.

    Reads ``tally()`` over the layout feedback log. Empty log, no signal — and
    that is the common case today, because nothing writes to it yet.

    Weighted lowest of the six deliberately. A detector's track record is about
    the detector, not about the region in front of it, and a good record that
    carried the score would hide precisely the cases worth catching.
    """
    if not history:
        return Signal(SignalKind.HISTORICAL, None, "no review history yet")

    detector = component.metadata.get("detector") or component.metadata.get("strategy")
    record = history.get(detector) if detector else None
    if record is None:
        return Signal(SignalKind.HISTORICAL, None,
                      f"no review history for {detector or 'this detector'}")

    accuracy = record.type_accuracy
    if accuracy is None:
        return Signal(SignalKind.HISTORICAL, None,
                      f"{detector} has been reviewed, but never on a named type")

    return Signal(SignalKind.HISTORICAL, accuracy,
                  f"{detector} named the type correctly "
                  f"{record.confirmed} of {record.confirmed + record.corrected} times")


# ── all six ──────────────────────────────────────────────────────────────────

def signals_for(
    component: DetectedComponent,
    page_size: tuple[int, int],
    *,
    crop: Any | None = None,
    store: Any | None = None,
    history: Mapping[str, Any] | None = None,
) -> list[Signal]:
    """Every signal that can be gathered for one region.

    Nothing here is optional in the output: a signal that could not be measured
    is still returned, carrying the reason why. An operator reading "nothing
    similar seen" learns something; a missing row teaches them nothing.
    """
    return [
        detector_signal(component),
        geometry_signal(component, page_size),
        knowledge_signal(component, page_size, store),
        structural_signal(component, crop),
        historical_signal(component, history),
        model_signal(component),
    ]


def assess(
    component: DetectedComponent,
    page_size: tuple[int, int],
    *,
    crop: Any | None = None,
    store: Any | None = None,
    history: Mapping[str, Any] | None = None,
) -> Confidence:
    """Gather the evidence for one region and combine it. The front door.

    The result is a **ranking**, not a probability, until the weights are
    fitted against the labelled corpus. ``Confidence.calibrated`` says so, and
    every consumer should read it rather than assume.
    """
    return score(signals_for(
        component, page_size, crop=crop, store=store, history=history,
    ))
