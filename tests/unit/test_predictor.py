"""
Reading the layout knowledge base back.

Two properties matter more than any number here.

**It must recognise the same kind of region on a document it has not seen.**
That is the whole return on people spending time reviewing — if a confirmed
header teaches nothing about the next invoice's header, the store is a log
rather than knowledge.

**It must not announce a match that is wrong.** Missing a match costs a little
confidence. A confident wrong match stops anybody looking again, which is the
failure the whole project is arranged against.
"""

from __future__ import annotations

import dataclasses

import pytest

from piply_opdf.core.types import BBox, ComponentType, DetectedComponent
from piply_opdf.intelligence import LayoutPredictor, Match, similarity
from piply_opdf.knowledge import (
    LayoutKnowledgeStore, Provenance, describe, describe_page,
)

A4_300DPI = (2480, 3508)


def _page(prefix: str = "a") -> list[DetectedComponent]:
    """An invoice-shaped page: logo top-left, header beside it, table, footer."""
    return [
        DetectedComponent(id=f"{prefix}_logo", type=ComponentType.LOGO,
                          page=1, bbox=BBox(120, 70, 300, 120)),
        DetectedComponent(id=f"{prefix}_head", type=ComponentType.HEADER,
                          page=1, bbox=BBox(500, 60, 1880, 140)),
        DetectedComponent(id=f"{prefix}_tab", type=ComponentType.TABLE,
                          page=1, bbox=BBox(150, 800, 2180, 1600)),
        DetectedComponent(id=f"{prefix}_foot", type=ComponentType.FOOTER,
                          page=1, bbox=BBox(150, 3300, 2180, 120)),
    ]


def _described(components) -> dict[str, object]:
    return {c.type: f for c, f in describe_page(components, A4_300DPI)}


@pytest.fixture
def taught(tmp_path):
    """A store holding one invoice's worth of confirmed regions."""
    store = LayoutKnowledgeStore(tmp_path / "kb.db")
    for kind, features in _described(_page("a")).items():
        store.remember(features, Provenance("invoice_one.pdf", 1, kind.lower(), "2"),
                       source="human")
    yield store
    store.close()


# ── it recognises the same kind of region elsewhere ──────────────────────────

def test_a_second_document_of_the_same_shape_is_recognised(taught):
    """The return on review: what one invoice taught, the next one uses."""
    second = _page("b")
    second[1].bbox = BBox(520, 75, 1850, 135)        # header nudged a little

    predictor = LayoutPredictor(taught)

    for component, features in describe_page(second, A4_300DPI):
        value, reason = predictor.verdict(features)
        assert value is not None and value > 0.9, f"{component.type}: {reason}"
        assert component.type in reason


def test_a_mislabelled_region_is_contradicted_by_what_people_confirmed(taught):
    """The case worth having. People already settled what regions here are;
    a detector calling one something else is disagreeing with them."""
    from piply_opdf.confidence import ALARM_BELOW

    header = _described(_page("a"))[ComponentType.HEADER]
    claimed_wrong = dataclasses.replace(header, component_type=ComponentType.PARAGRAPH)

    value, reason = LayoutPredictor(taught).verdict(claimed_wrong)

    assert value is not None and value < ALARM_BELOW, "this must register as a contradiction"
    assert "confirmed regions like this as HEADER" in reason
    assert "not PARAGRAPH" in reason


def test_regions_in_different_places_are_not_confused(taught):
    """A header and a footer have the same shape and opposite positions."""
    described = _described(_page("a"))

    alike = similarity(described[ComponentType.HEADER], described[ComponentType.FOOTER])

    assert alike < 0.7, f"header and footer scored {alike:.2f} alike"


def test_a_region_is_identical_to_itself():
    described = _described(_page("a"))
    assert similarity(described[ComponentType.TABLE], described[ComponentType.TABLE]) == 1.0


# ── it refuses to guess ──────────────────────────────────────────────────────

def test_an_empty_store_says_nothing_rather_than_zero(tmp_path):
    """Unmeasured, not negative. Nobody has taught it anything yet."""
    with LayoutKnowledgeStore(tmp_path / "empty.db") as store:
        features = describe(_page("a")[1], A4_300DPI)
        value, reason = LayoutPredictor(store).verdict(features)

    assert value is None
    assert "nothing has been confirmed yet" in reason


def test_matching_nothing_in_a_sparse_store_is_not_evidence_against(taught):
    """With a handful of records, a non-match says the store is thin — not
    that the region is odd. Claiming otherwise would invent a measurement."""
    stranger = describe(
        DetectedComponent(id="s", type=ComponentType.SIGNATURE, page=1,
                          bbox=BBox(1900, 1500, 300, 200)),
        A4_300DPI,
    )

    value, reason = LayoutPredictor(taught).verdict(stranger)

    assert value is None
    assert "too few to read as disagreement" in reason


def test_weak_resemblances_are_not_offered_as_matches(taught):
    """Missing a match costs a little confidence; announcing a wrong one stops
    anybody looking again."""
    stranger = describe(
        DetectedComponent(id="s", type=ComponentType.SIGNATURE, page=1,
                          bbox=BBox(1900, 1500, 300, 200)),
        A4_300DPI,
    )

    assert LayoutPredictor(taught).match(stranger) == []
    assert LayoutPredictor(taught, min_similarity=0.0).match(stranger) != []


def test_records_from_an_older_extractor_are_never_matched_against(tmp_path):
    """The store filters them; the predictor must not work around it."""
    with LayoutKnowledgeStore(tmp_path / "kb.db") as store:
        features = describe(_page("a")[1], A4_300DPI)
        store.remember(features, Provenance("old.pdf", 1, "header", "1",
                                            feature_version="1"), source="human")

        value, reason = LayoutPredictor(store).verdict(features)

    assert value is None
    assert "nothing has been confirmed yet" in reason


# ── it can be argued with ────────────────────────────────────────────────────

def test_a_match_reports_which_groups_agreed(taught):
    """A score nobody can take apart is one an operator will either believe
    blindly or ignore."""
    header = _described(_page("a"))[ComponentType.HEADER]

    best = LayoutPredictor(taught).match(header)[0]

    assert set(best.groups) >= {"geometry", "relationships"}
    assert "geometry" in best.why()
    assert "HEADER" in best.why()
    assert "invoice_one.pdf" in best.why()


def test_matches_come_back_best_first(taught):
    header = _described(_page("a"))[ComponentType.HEADER]

    found = LayoutPredictor(taught, min_similarity=0.0).match(header, limit=4)

    assert [m.score for m in found] == sorted((m.score for m in found), reverse=True)
    assert found[0].component_type == ComponentType.HEADER


def test_it_searches_every_type_not_just_the_claimed_one(taught):
    """The useful case is exactly the one where the claim is wrong — filtering
    by the claimed type would hide it."""
    header = _described(_page("a"))[ComponentType.HEADER]
    claimed_wrong = dataclasses.replace(header, component_type=ComponentType.STAMP)

    found = LayoutPredictor(taught).match(claimed_wrong)

    assert found and found[0].component_type == ComponentType.HEADER


# ── missing is not zero, here too ────────────────────────────────────────────

def test_a_group_neither_record_has_is_skipped_not_scored_zero(tmp_path):
    """A record described from geometry alone is not *unlike* one with
    appearance measured. It is quieter."""
    geometry_only = describe(_page("a")[1], A4_300DPI)

    assert "appearance" not in _groups(geometry_only, geometry_only)
    assert "shape" not in _groups(geometry_only, geometry_only)
    assert similarity(geometry_only, geometry_only) == 1.0


def _groups(a, b) -> dict:
    from piply_opdf.intelligence.predictor import _score_against

    return _score_against(a, b)[1]


def test_appearance_is_compared_when_both_records_have_it():
    import cv2
    import numpy as np

    crop = np.full((90, 400, 3), 255, dtype=np.uint8)
    for line in range(3):
        cv2.putText(crop, "Patient Name", (10, 28 + line * 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20, 20, 20), 2)

    measured = describe(_page("a")[1], A4_300DPI, crop=crop)

    groups = _groups(measured, measured)
    assert "appearance" in groups and "shape" in groups
