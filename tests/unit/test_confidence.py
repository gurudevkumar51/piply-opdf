"""
Confidence as an evidence score.

The behaviour being protected is the one that made the old scores useless: when
every value is a literal meaning "this rule fired", the scores bunch, and
"review the doubtful ones" selects everything. So the tests here are less about
any particular number than about three properties:

* a signal nobody could measure must not be scored as zero,
* one contradiction must outrank a comfortable average,
* and the resulting scores must actually **separate**, or the ranking is
  arbitrary however carefully it is sorted.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from piply_opdf.confidence import (
    ALARM_BELOW,
    Confidence,
    Signal,
    SignalKind,
    assess,
    detector_signal,
    geometry_signal,
    historical_signal,
    knowledge_signal,
    model_signal,
    review_queue,
    score,
    signals_for,
    spread,
    structural_signal,
)
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent
from piply_opdf.knowledge import DetectorScore

A4_300DPI = (2480, 3508)


def _component(
    kind: str, box: tuple[int, int, int, int], *,
    confidence: float = 0.7, **metadata,
) -> DetectedComponent:
    return DetectedComponent(
        id=f"{kind.lower()}_{box[0]}_{box[1]}",
        type=kind, page=1, bbox=BBox(*box),
        confidence=confidence, metadata=metadata,
    )


# ── missing is not zero ──────────────────────────────────────────────────────

def test_an_unmeasured_signal_does_not_drag_the_score_down():
    """The rule the whole design rests on.

    Scoring an unmeasured signal as 0 would punish a region for the pipeline's
    gaps rather than its own weakness — and today four of six signals are
    frequently unmeasurable, so this is not a corner case.
    """
    alone = score([Signal(SignalKind.DETECTOR, 0.9, "")])
    with_gaps = score([
        Signal(SignalKind.DETECTOR, 0.9, ""),
        Signal(SignalKind.KNOWLEDGE, None, "nothing seen"),
        Signal(SignalKind.MODEL, None, "baseline did not run"),
    ])

    assert alone.score == with_gaps.score == pytest.approx(0.9)


def test_a_region_nobody_could_measure_scores_zero():
    """Not 1.0. A region nothing can be said about is one to look at."""
    result = score([
        Signal(SignalKind.DETECTOR, None, ""),
        Signal(SignalKind.GEOMETRY, None, ""),
    ])
    assert result.score == 0.0


def test_signals_are_weighted_not_averaged_flat():
    """Track record must not carry the score. See WEIGHTS."""
    detector_high = score([
        Signal(SignalKind.DETECTOR, 1.0, ""),
        Signal(SignalKind.HISTORICAL, 0.0, ""),
    ])
    history_high = score([
        Signal(SignalKind.DETECTOR, 0.0, ""),
        Signal(SignalKind.HISTORICAL, 1.0, ""),
    ])

    assert detector_high.score == pytest.approx(0.75)   # 3:1 in the detector's favour
    assert history_high.score == pytest.approx(0.25)
    assert detector_high.score > history_high.score


def test_the_same_signal_twice_is_refused():
    """It would silently double that signal's weight."""
    with pytest.raises(ValueError, match="given twice"):
        score([Signal(SignalKind.DETECTOR, 0.5, ""),
               Signal(SignalKind.DETECTOR, 0.9, "")])


def test_an_unknown_signal_is_refused():
    with pytest.raises(ValueError, match="unknown signal"):
        Signal("vibes", 0.9, "")


def test_a_signal_outside_zero_to_one_is_refused():
    with pytest.raises(ValueError, match="between 0 and 1"):
        Signal(SignalKind.DETECTOR, 1.4, "")


# ── one contradiction outranks a good average ────────────────────────────────

def test_a_single_contradiction_sends_a_comfortable_component_to_review():
    """Five agreeable signals and one saying 0.1 is not a 0.75 component."""
    result = score([
        Signal(SignalKind.DETECTOR, 0.9, ""),
        Signal(SignalKind.STRUCTURAL, 0.9, ""),
        Signal(SignalKind.MODEL, 0.9, ""),
        Signal(SignalKind.GEOMETRY, 0.1, "shape is wrong for the type"),
    ])

    assert result.score > 0.7, "the average stays honest"
    assert result.needs_review(), "but the decision does not"
    assert len(result.contradictions) == 1


def test_the_score_itself_is_not_distorted_to_force_a_review():
    """Bending the number would make it both a worse ranking and a worse
    explanation. The decision is kept separate on purpose."""
    signals = [Signal(SignalKind.DETECTOR, 0.9, ""), Signal(SignalKind.GEOMETRY, 0.1, "")]
    plain = (0.9 * 3.0 + 0.1 * 2.0) / 5.0

    assert score(signals).score == pytest.approx(plain)


def test_a_merely_low_signal_is_not_a_contradiction():
    result = score([Signal(SignalKind.GEOMETRY, ALARM_BELOW + 0.05, "")])
    assert result.contradictions == ()


# ── the explanation ──────────────────────────────────────────────────────────

def test_an_operator_can_ask_why():
    result = score([
        Signal(SignalKind.DETECTOR, 0.70, "text-layer key-value rule"),
        Signal(SignalKind.KNOWLEDGE, None, "nothing similar seen"),
    ])
    explanation = result.why()

    assert "text-layer key-value rule" in explanation
    assert "nothing similar seen" in explanation
    assert "ranking, not a probability" in explanation


def test_unmeasured_signals_are_shown_not_hidden():
    """"Nothing similar has been seen before" is itself worth knowing."""
    explanation = score([Signal(SignalKind.DETECTOR, 0.7, "rule")]).why()

    for kind in SignalKind.ALL:
        assert kind in explanation


def test_the_evidence_travels_with_the_answer():
    """Per the governing principle — a score with its reasoning thrown away
    cannot be argued with."""
    stored = score([Signal(SignalKind.DETECTOR, 0.7, "rule fired")]).as_metadata()

    assert stored["calibrated"] is False
    assert stored["signals"][SignalKind.DETECTOR]["reason"] == "rule fired"


def test_nothing_claims_to_be_calibrated_yet():
    assert Confidence(score=0.9).calibrated is False


# ── geometry ─────────────────────────────────────────────────────────────────

def test_a_header_at_the_top_satisfies_its_definition():
    header = _component(ComponentType.HEADER, (100, 60, 2280, 140))
    assert geometry_signal(header, A4_300DPI).value == 1.0


def test_a_header_in_the_middle_of_the_page_does_not():
    header = _component(ComponentType.HEADER, (100, 1700, 2280, 140))
    signal = geometry_signal(header, A4_300DPI)

    assert signal.value is not None and signal.value < ALARM_BELOW
    assert "band" in signal.reason


def test_a_header_one_band_off_is_doubted_not_condemned():
    """A page with a wide top margin is not a broken detection."""
    header = _component(ComponentType.HEADER, (100, 700, 2280, 140))
    signal = geometry_signal(header, A4_300DPI)

    assert signal.value == pytest.approx(0.5)


def test_a_footer_is_judged_from_the_bottom():
    at_bottom = _component(ComponentType.FOOTER, (100, 3300, 2280, 120))
    at_top = _component(ComponentType.FOOTER, (100, 60, 2280, 120))

    assert geometry_signal(at_bottom, A4_300DPI).value == 1.0
    assert geometry_signal(at_top, A4_300DPI).value < ALARM_BELOW


def test_a_separator_is_scored_against_being_a_line():
    line = _component(ComponentType.SEPARATOR, (100, 500, 2000, 6))
    blob = _component(ComponentType.SEPARATOR, (100, 500, 200, 100))

    assert geometry_signal(line, A4_300DPI).value == 1.0
    assert geometry_signal(blob, A4_300DPI).value < ALARM_BELOW


def test_a_container_too_small_to_hold_a_cell_is_doubted():
    real = _component(ComponentType.TABLE, (150, 800, 2180, 1600))
    speck = _component(ComponentType.TABLE, (150, 800, 20, 20))

    assert geometry_signal(real, A4_300DPI).value == 1.0
    assert geometry_signal(speck, A4_300DPI).value < ALARM_BELOW


def test_a_key_value_is_expected_to_be_a_row():
    row = _component(ComponentType.KEY_VALUE, (100, 500, 900, 60))
    column = _component(ComponentType.KEY_VALUE, (100, 500, 60, 900))

    assert geometry_signal(row, A4_300DPI).value == 1.0
    assert geometry_signal(column, A4_300DPI).value < ALARM_BELOW


# ── grid parts are judged by containment, not by shape ───────────────────────

def _table(box=(100, 100, 1000, 800)) -> DetectedComponent:
    return _component(ComponentType.TABLE, box)


@pytest.mark.parametrize("kind", [ComponentType.CELL, ComponentType.ROW, ComponentType.COLUMN])
def test_a_grid_part_inside_its_table_is_where_it_should_be(kind):
    part = _component(kind, (200, 200, 150, 60))

    signal = geometry_signal(part, A4_300DPI, parent=_table())

    assert signal.value == 1.0
    assert "sits inside" in signal.reason


def test_a_cell_escaping_its_table_is_a_broken_grid():
    """The failure worth catching: a grid built from lines that are not there
    attributes every value to the wrong column."""
    escaped = _component(ComponentType.CELL, (1050, 200, 150, 60))

    signal = geometry_signal(escaped, A4_300DPI, parent=_table())

    assert signal.value is not None and signal.value < ALARM_BELOW
    assert "falls outside" in signal.reason


def test_a_cell_overhanging_slightly_is_not_condemned():
    """A few pixels past the edge is a rounding artefact, not a bad grid."""
    overhanging = _component(ComponentType.CELL, (1090, 200, 20, 60))

    signal = geometry_signal(overhanging, A4_300DPI, parent=_table())

    assert signal.value == pytest.approx(0.5)


def test_a_grid_part_with_no_parent_cannot_be_placed():
    """None, not zero — nobody said it was in the wrong place."""
    orphan = _component(ComponentType.CELL, (200, 200, 150, 60))

    signal = geometry_signal(orphan, A4_300DPI)

    assert signal.value is None
    assert "no parent recorded" in signal.reason


def test_a_cells_shape_is_never_held_against_it():
    """A cell can be any proportion the document makes it. Only containment
    is definitional, so a very wide and a very tall cell score alike."""
    wide = _component(ComponentType.CELL, (200, 200, 800, 20))
    tall = _component(ComponentType.CELL, (200, 200, 20, 600))
    table = _table()

    assert (geometry_signal(wide, A4_300DPI, parent=table).value
            == geometry_signal(tall, A4_300DPI, parent=table).value == 1.0)


def test_the_parent_reaches_the_signal_through_assess():
    escaped = _component(ComponentType.CELL, (1050, 200, 150, 60))

    with_parent = assess(escaped, A4_300DPI, parent=_table())
    without = assess(escaped, A4_300DPI)

    assert with_parent.contradictions, "the escape is visible"
    assert not without.contradictions, "with no parent there is nothing to check"


def test_a_type_with_no_definitional_shape_invents_no_evidence():
    """A paragraph can be any shape. Scoring it would be making things up."""
    signal = geometry_signal(_component(ComponentType.PARAGRAPH, (0, 0, 100, 100)), A4_300DPI)

    assert signal.value is None
    assert "no definitional shape" in signal.reason


# ── the other signals ────────────────────────────────────────────────────────

def test_the_detector_literal_becomes_one_named_input():
    component = _component(ComponentType.PARAGRAPH, (0, 0, 100, 50),
                           confidence=0.88, detector="para_text")
    signal = detector_signal(component)

    assert signal.value == pytest.approx(0.88)
    assert "para_text" in signal.reason


def test_the_baseline_is_absent_rather_than_disagreeing_when_it_did_not_run():
    signal = model_signal(_component(ComponentType.TABLE, (0, 0, 100, 100)))

    assert signal.value is None
    assert "did not run" in signal.reason


def test_the_baseline_score_is_used_when_fusion_recorded_one():
    component = _component(ComponentType.TABLE, (0, 0, 100, 100),
                           model_confidence=0.77, baseline_agreed=True)
    signal = model_signal(component)

    assert signal.value == pytest.approx(0.77)
    assert "agreed" in signal.reason


def test_an_empty_knowledge_base_says_so_rather_than_scoring_zero(tmp_path):
    """Unmeasured, not negative. Nobody has taught it anything yet, which says
    nothing about this region."""
    from piply_opdf.knowledge import LayoutKnowledgeStore

    component = _component(ComponentType.TABLE, (0, 0, 100, 100))

    assert knowledge_signal(component, A4_300DPI, None).value is None
    with LayoutKnowledgeStore(tmp_path / "kb.db") as store:
        signal = knowledge_signal(component, A4_300DPI, store)

    assert signal.value is None
    assert "nothing has been confirmed yet" in signal.reason


def test_the_knowledge_signal_reports_agreement_once_people_have_taught_it(tmp_path):
    """The signal that was dark until the LayoutPredictor existed."""
    from piply_opdf.knowledge import LayoutKnowledgeStore, Provenance, describe

    header = _component(ComponentType.HEADER, (100, 60, 2280, 140))
    features = describe(header, A4_300DPI)

    with LayoutKnowledgeStore(tmp_path / "kb.db") as store:
        store.remember(features, Provenance("first.pdf", 1, "header", "2"),
                       source="human")
        signal = knowledge_signal(header, A4_300DPI, store, features=features)

    assert signal.value is not None and signal.value > 0.9
    assert "matches a confirmed HEADER" in signal.reason


def test_the_knowledge_signal_contradicts_a_type_people_disagreed_with(tmp_path):
    """A detector calling a region something people already settled
    differently is disagreeing with them, and that is a contradiction."""
    import dataclasses

    from piply_opdf.knowledge import LayoutKnowledgeStore, Provenance, describe

    box = (100, 60, 2280, 140)
    confirmed = describe(_component(ComponentType.HEADER, box), A4_300DPI)
    claimed_wrong = dataclasses.replace(confirmed,
                                        component_type=ComponentType.PARAGRAPH)

    with LayoutKnowledgeStore(tmp_path / "kb.db") as store:
        store.remember(confirmed, Provenance("first.pdf", 1, "header", "2"),
                       source="human")
        signal = knowledge_signal(_component(ComponentType.PARAGRAPH, box),
                                  A4_300DPI, store, features=claimed_wrong)

    assert signal.value is not None and signal.value < ALARM_BELOW
    assert "not PARAGRAPH" in signal.reason


def test_a_detectors_track_record_is_read_from_the_feedback_log():
    component = _component(ComponentType.HEADER, (0, 0, 100, 50), detector="header")
    history = {"header": DetectorScore("header", confirmed=9, corrected=1)}

    signal = historical_signal(component, history)

    assert signal.value == pytest.approx(0.9)
    assert "9 of 10" in signal.reason


def test_no_review_history_means_no_signal():
    component = _component(ComponentType.HEADER, (0, 0, 100, 50), detector="header")

    assert historical_signal(component, {}).value is None
    assert historical_signal(component, None).value is None


# ── structural, from the image ───────────────────────────────────────────────

def _printed_text_crop() -> np.ndarray:
    """Real glyphs, rendered.

    An earlier version of this fixture drew rows of small solid rectangles as a
    stand-in for words. The classifier read it as ``HANDWRITING``, and it was
    right to: uniform blocks have none of the stroke-width variation or ruled
    baseline that printing has. A fixture that does not look like the thing it
    claims to be tests nothing.
    """
    crop = np.full((110, 460, 3), 255, dtype=np.uint8)
    for line, text in enumerate((
        "Patient Name and Age", "Admission Date 6/26/25", "Provider Divakaruni",
    )):
        cv2.putText(crop, text, (12, 32 + line * 34),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)
    return crop


def _printed_mark_crop() -> np.ndarray:
    """A solid two-colour mark — a logo, by rule 2."""
    crop = np.full((110, 110, 3), 255, dtype=np.uint8)
    cv2.circle(crop, (55, 55), 40, (200, 40, 30), -1)
    cv2.circle(crop, (55, 55), 20, (30, 90, 210), -1)
    return crop


def test_no_crop_means_no_structural_evidence():
    component = _component(ComponentType.PARAGRAPH, (0, 0, 400, 90))
    signal = structural_signal(component, None)

    assert signal.value is None
    assert "no crop" in signal.reason


def test_the_ink_confirms_a_claim_it_matches():
    text, mark = _printed_text_crop(), _printed_mark_crop()

    paragraph = structural_signal(_component(ComponentType.PARAGRAPH, (0, 0, 460, 110)), text)
    logo = structural_signal(_component(ComponentType.LOGO, (0, 0, 110, 110)), mark)

    assert paragraph.value == pytest.approx(0.7), "the classifier's own confidence"
    assert logo.value == pytest.approx(0.85)
    assert "which is what was claimed" in paragraph.reason


def test_the_ink_contradicts_a_claim_from_the_wrong_family():
    """This is the signal that catches a detector firing on the right place for
    the wrong reason."""
    text, mark = _printed_text_crop(), _printed_mark_crop()

    text_called_a_logo = structural_signal(
        _component(ComponentType.LOGO, (0, 0, 460, 110)), text)
    mark_called_a_paragraph = structural_signal(
        _component(ComponentType.PARAGRAPH, (0, 0, 110, 110)), mark)

    assert text_called_a_logo.value == pytest.approx(0.3)
    assert mark_called_a_paragraph.value == pytest.approx(0.15)
    assert mark_called_a_paragraph.value < ALARM_BELOW, "and that is a contradiction"


def test_the_ink_supports_without_confirming_inside_a_family():
    """The classifier has no concept of a header — it names what ink looks
    like, not the role a region plays. "This is text" therefore backs a header
    claim without settling it."""
    header = _component(ComponentType.HEADER, (0, 0, 460, 110))

    signal = structural_signal(header, _printed_text_crop())

    assert signal.value == pytest.approx(0.7 * 0.8)
    assert "supports without confirming" in signal.reason


def test_the_classifier_is_not_asked_about_crops_the_size_of_a_cell():
    """Measured on sample.pdf: 80% of cells came back HANDWRITING or SIGNATURE
    on a page with roughly one handwritten column, because baseline_scatter
    stops discriminating at that scale and stroke width cannot make the call on
    a scan. A signal wrong four times in five is worse than no signal — it
    penalises every cell and buries the ones that deserve attention."""
    crop = _printed_text_crop()

    for kind in (ComponentType.CELL, ComponentType.ROW, ComponentType.COLUMN):
        signal = structural_signal(_component(kind, (0, 0, 460, 110)), crop)
        assert signal.value is None
        assert "not reliable on crops" in signal.reason


def test_a_container_is_not_judged_by_the_ink_of_its_children():
    """A PANEL holding a signature reads as SIGNATURE. True about the ink, and
    no evidence at all about the panel."""
    signal = structural_signal(
        _component(ComponentType.PANEL, (0, 0, 110, 110)), _printed_mark_crop())

    assert signal.value is None
    assert "judged by its children" in signal.reason


def test_a_region_too_small_to_judge_yields_no_structural_signal():
    tiny = np.full((2, 2, 3), 255, dtype=np.uint8)
    signal = structural_signal(_component(ComponentType.PARAGRAPH, (0, 0, 2, 2)), tiny)

    assert signal.value is None


# ── all six together ─────────────────────────────────────────────────────────

def test_every_signal_is_reported_even_when_it_could_not_be_measured():
    """A missing row teaches an operator nothing; a row saying why teaches them
    something."""
    component = _component(ComponentType.HEADER, (100, 60, 2280, 140))
    gathered = signals_for(component, A4_300DPI)

    assert {s.kind for s in gathered} == set(SignalKind.ALL)
    assert all(s.reason for s in gathered), "every signal explains itself"


def test_assess_produces_a_ranking_not_a_probability():
    component = _component(ComponentType.HEADER, (100, 60, 2280, 140))
    result = assess(component, A4_300DPI)

    assert result.calibrated is False
    assert 0.0 <= result.score <= 1.0


# ── the queue ────────────────────────────────────────────────────────────────

def _assessed(*pairs: tuple[DetectedComponent, float]):
    return [(component, Confidence(score=value)) for component, value in pairs]


def test_the_weakest_come_first():
    strong = _component(ComponentType.HEADER, (0, 0, 100, 50))
    weak = _component(ComponentType.FOOTER, (0, 100, 100, 50))

    queued = review_queue(_assessed((strong, 0.9), (weak, 0.3)))

    assert [item.component for item in queued] == [weak, strong]


def test_a_contradicted_region_jumps_the_queue():
    """Something specific is wrong with it — better use of a person's hour than
    the next region down a smooth ranking."""
    contradicted = _component(ComponentType.HEADER, (0, 0, 100, 50))
    merely_weak = _component(ComponentType.FOOTER, (0, 100, 100, 50))

    queued = review_queue([
        (merely_weak, Confidence(score=0.2)),
        (contradicted, score([
            Signal(SignalKind.DETECTOR, 0.9, ""),
            Signal(SignalKind.GEOMETRY, 0.1, ""),
        ])),
    ])

    assert queued[0].component is contradicted
    assert queued[0].contradicted is True
    assert queued[0].score > queued[1].score, "and it scores higher, which is the point"


def test_capacity_is_the_control_an_operator_actually_has():
    parts = [_component(ComponentType.SENTENCE, (0, n * 60, 100, 50)) for n in range(10)]
    assessed = [(p, Confidence(score=n / 10)) for n, p in enumerate(parts)]

    queued = review_queue(assessed, capacity=3)

    assert len(queued) == 3
    assert [item.score for item in queued] == [0.0, 0.1, 0.2]


def test_a_threshold_can_still_be_applied_for_callers_that_want_one():
    parts = [_component(ComponentType.SENTENCE, (0, n * 60, 100, 50)) for n in range(10)]
    assessed = [(p, Confidence(score=n / 10)) for n, p in enumerate(parts)]

    assert len(review_queue(assessed, below=0.5)) == 5


def test_an_empty_page_produces_an_empty_queue():
    assert review_queue([]) == []


# ── the regression this replaces ─────────────────────────────────────────────

def test_identical_literal_scores_are_reported_as_unrankable():
    """The failure being fixed, stated as a test.

    When every component carries the same literal, sorting by confidence is
    arbitrary dressed as considered. The spread has to say so rather than let a
    caller assume the ordering means something.
    """
    literals = [Confidence(score=0.70) for _ in range(20)]

    measured = spread(literals)

    assert measured.is_useful is False
    assert "too alike" in measured.summary()


def test_evidence_derived_scores_separate_enough_to_rank():
    """The same page, scored from evidence, sorts into a usable order."""
    page = [
        _component(ComponentType.HEADER, (100, 60, 2280, 140), confidence=0.85),
        _component(ComponentType.HEADER, (100, 1700, 2280, 140), confidence=0.85),
        _component(ComponentType.TABLE, (150, 800, 2180, 1600), confidence=0.80),
        _component(ComponentType.TABLE, (150, 800, 20, 20), confidence=0.80),
        _component(ComponentType.SEPARATOR, (100, 500, 2000, 6), confidence=0.60),
        _component(ComponentType.SEPARATOR, (100, 500, 200, 100), confidence=0.60),
    ]
    assessed = [(p, assess(p, A4_300DPI)) for p in page]

    measured = spread([c for _, c in assessed])
    assert measured.is_useful is True

    # The three deliberately misplaced regions sort to the front.
    worst = {item.component.id for item in review_queue(assessed, capacity=3)}
    assert worst == {"header_100_1700", "table_150_800", "separator_100_500"}


def test_a_single_component_cannot_be_ranked_against_itself():
    assert spread([Confidence(score=0.5)]).is_useful is False


def test_measuring_the_spread_of_nothing_is_survivable():
    empty = spread([])
    assert empty.count == 0 and empty.is_useful is False
