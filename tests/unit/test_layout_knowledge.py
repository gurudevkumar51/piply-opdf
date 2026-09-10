"""
Layout knowledge: describing a region so it can be recognised somewhere else,
and storing it so it stays interpretable.

Three behaviours are being protected, and each has cost something to learn:

* A description must survive a change of scanner. Anything measured in pixels
  does not, so the tests scale a page and demand the same answer.
* Neighbours must be real neighbours. Ten pixels of shared span is a
  coincidence, not a relationship.
* A record whose features were built by a different extractor must not be
  matched against. Old knowledge that silently answers is worse than no
  knowledge, because nothing about the answer looks wrong.
"""

from __future__ import annotations

import pytest

from piply_opdf.core.exceptions import KnowledgeBaseError
from piply_opdf.core.types import BBox, ComponentType, DetectedComponent
from piply_opdf.knowledge import (
    FEATURE_VERSION,
    LayoutAction,
    LayoutFeedback,
    LayoutKnowledgeStore,
    Provenance,
    counts_by_action,
    describe,
    describe_page,
    page_band,
    tally,
)

A4_300DPI = (2480, 3508)


def _component(
    kind: str, box: tuple[int, int, int, int], *,
    id: str | None = None, children: list[DetectedComponent] | None = None,
) -> DetectedComponent:
    return DetectedComponent(
        id=id or f"{kind.lower()}_{box[0]}_{box[1]}",
        type=kind,
        page=1,
        bbox=BBox(*box),
        children=children or [],
    )


def _provenance(**overrides) -> Provenance:
    defaults = dict(
        source_document="sample.pdf",
        source_page=1,
        detector_name="header",
        detector_version="2",
    )
    return Provenance(**{**defaults, **overrides})


# ── geometry is scale-free ───────────────────────────────────────────────────

def test_the_same_layout_at_a_different_dpi_describes_identically():
    """The whole point of ratios. A header is near the top at any resolution."""
    small = _component(ComponentType.HEADER, (100, 60, 1140, 100))
    large = _component(ComponentType.HEADER, (200, 120, 2280, 200))

    at_150 = describe(small, (1240, 1754))
    at_300 = describe(large, (2480, 3508))

    assert at_150 == at_300


def test_position_is_recorded_as_a_fraction_of_the_page():
    component = _component(ComponentType.TABLE, (248, 1754, 1240, 350))
    features = describe(component, A4_300DPI)

    assert features.rel_x == pytest.approx(0.1)
    assert features.rel_y == pytest.approx(0.5)
    assert features.rel_w == pytest.approx(0.5)


def test_aspect_ratio_comes_from_the_box_even_with_no_image():
    features = describe(_component(ComponentType.SEPARATOR, (0, 0, 800, 4)), A4_300DPI)

    assert features.aspect_ratio == pytest.approx(200.0)
    assert features.has_appearance is False


@pytest.mark.parametrize(
    "relative_y, expected",
    [(0.02, "top"), (0.14, "top"), (0.2, "upper"), (0.5, "middle"),
     (0.7, "lower"), (0.9, "bottom"), (1.0, "bottom")],
)
def test_page_bands_split_the_page_where_headers_and_footers_live(relative_y, expected):
    assert page_band(relative_y) == expected


def test_the_band_uses_the_centre_not_the_top_edge():
    """A tall block starting at the very top is not a header."""
    banner = _component(ComponentType.PARAGRAPH, (0, 0, 2480, 2000))
    assert describe(banner, A4_300DPI).page_band == "upper"


def test_a_page_with_no_size_is_refused():
    with pytest.raises(ValueError, match="page size must be positive"):
        describe(_component(ComponentType.TITLE, (0, 0, 10, 10)), (0, 3508))


# ── relationships ────────────────────────────────────────────────────────────

def test_neighbours_are_recorded_in_all_four_directions():
    target = _component(ComponentType.TABLE, (500, 1000, 1000, 500))
    page = [
        target,
        _component(ComponentType.TITLE, (500, 700, 1000, 100)),      # above
        _component(ComponentType.FOOTER, (500, 1700, 1000, 100)),    # below
        _component(ComponentType.LOGO, (100, 1100, 200, 200)),       # left
        _component(ComponentType.STAMP, (1700, 1100, 200, 200)),     # right
    ]

    features = describe(target, A4_300DPI, siblings=page)

    assert features.above_type == ComponentType.TITLE
    assert features.below_type == ComponentType.FOOTER
    assert features.left_type == ComponentType.LOGO
    assert features.right_type == ComponentType.STAMP


def test_the_nearer_of_two_neighbours_wins():
    target = _component(ComponentType.TABLE, (500, 1000, 1000, 500))
    page = [
        target,
        _component(ComponentType.TITLE, (500, 200, 1000, 100)),    # far above
        _component(ComponentType.HEADING, (500, 900, 1000, 60)),   # near above
    ]

    assert describe(target, A4_300DPI, siblings=page).above_type == ComponentType.HEADING


def test_a_region_that_barely_shares_a_span_is_not_a_neighbour():
    """A page number in the right margin is not "above" a full-width table.

    Without the overlap floor, ten shared pixels make a relationship, and every
    stored record fills with coincidences that mean nothing on the next page.
    """
    table = _component(ComponentType.TABLE, (100, 1000, 2000, 500))
    page_number = _component(ComponentType.FOOTER, (2050, 900, 60, 40))

    features = describe(table, A4_300DPI, siblings=[table, page_number])

    assert features.above_type is None


def test_alignment_counts_the_siblings_sharing_an_edge():
    """A header row is text above rows sharing its column edges."""
    header = _component(ComponentType.HEADER, (300, 500, 1800, 60))
    rows = [_component(ComponentType.PARAGRAPH, (300, 600 + n * 80, 1800, 60),
                       id=f"row_{n}") for n in range(3)]

    features = describe(header, A4_300DPI, siblings=[header, *rows])

    assert features.aligns_left_with == 3
    assert features.aligns_right_with == 3


def test_a_small_drift_still_counts_as_aligned():
    """Scanners drift. 0.5% of the page width absorbs it."""
    first = _component(ComponentType.PARAGRAPH, (300, 500, 1000, 60))
    second = _component(ComponentType.PARAGRAPH, (306, 600, 1000, 60))

    assert describe(first, A4_300DPI, siblings=[first, second]).aligns_left_with == 1


def test_a_clearly_different_edge_does_not_count_as_aligned():
    first = _component(ComponentType.PARAGRAPH, (300, 500, 1000, 60))
    second = _component(ComponentType.PARAGRAPH, (700, 600, 1000, 60))

    assert describe(first, A4_300DPI, siblings=[first, second]).aligns_left_with == 0


# ── nesting ──────────────────────────────────────────────────────────────────

def test_children_are_described_against_their_siblings_not_the_page():
    """Cells in a table are positioned against each other, not against a logo.

    The logo sits directly above the first cell on the page. Scoped to
    siblings, the cell's neighbour above is the other cell — or nothing — but
    never something outside the container it lives in.
    """
    cell_a = _component(ComponentType.KEY_VALUE, (400, 1100, 400, 80), id="cell_a")
    cell_b = _component(ComponentType.KEY_VALUE, (400, 1200, 400, 80), id="cell_b")
    table = _component(ComponentType.TABLE, (300, 1000, 1800, 600),
                       id="table", children=[cell_a, cell_b])
    logo = _component(ComponentType.LOGO, (400, 200, 300, 300), id="logo")

    described = describe_page([table, logo], A4_300DPI)
    assert len(described) == 4, "table, two cells and the logo"

    top_cell, bottom_cell = (
        f for _, f in described if f.parent_type == ComponentType.TABLE
    )

    assert top_cell.above_type is None, "the logo is outside the table"
    assert top_cell.below_type == ComponentType.KEY_VALUE
    assert bottom_cell.above_type == ComponentType.KEY_VALUE
    assert described[0][1].parent_type is None, "the table itself is top level"
    assert described[0][0] is table, "each record is paired with its component"


def test_a_child_knows_what_contains_it():
    child = _component(ComponentType.SENTENCE, (400, 1100, 400, 80), id="child")
    panel = _component(ComponentType.PANEL, (300, 1000, 1800, 600),
                       id="panel", children=[child])

    described = describe_page([panel], A4_300DPI)

    assert described[0][1].parent_type is None
    assert described[1][1].parent_type == ComponentType.PANEL
    assert described[1][0] is child


def test_geometry_stays_relative_to_the_page_even_inside_a_container():
    """So a cell's position is comparable across documents, not just within one."""
    child = _component(ComponentType.SENTENCE, (248, 1754, 248, 350), id="child")
    panel = _component(ComponentType.PANEL, (0, 1700, 2480, 600),
                       id="panel", children=[child])

    described = describe_page([panel], A4_300DPI)

    assert described[1][1].rel_x == pytest.approx(0.1)
    assert described[1][1].rel_y == pytest.approx(0.5)


# ── appearance ───────────────────────────────────────────────────────────────

def test_a_crop_is_measured_by_the_same_function_the_classifier_uses():
    """One extractor. If these drifted apart the store would describe regions
    in numbers the classifier no longer recognises."""
    import numpy as np

    from piply_opdf.classification import measure

    crop = np.full((80, 300, 3), 255, dtype=np.uint8)
    crop[20:30, 40:260] = 0                       # a bar of ink
    crop[50:60, 40:260] = 0

    features = describe(
        _component(ComponentType.PARAGRAPH, (100, 500, 300, 80)), A4_300DPI, crop=crop
    )
    direct = measure(crop)

    assert features.has_appearance is True
    assert features.ink_ratio == pytest.approx(direct.ink_ratio, abs=1e-6)
    assert features.stroke_width_cv == pytest.approx(direct.stroke_width_cv, abs=1e-6)
    assert features.colour_clusters == direct.colour_clusters


def test_a_region_too_small_to_measure_records_absence_not_zero():
    """Nobody measured it and it has no ink are different facts."""
    import numpy as np

    tiny = np.full((2, 2, 3), 255, dtype=np.uint8)

    features = describe(
        _component(ComponentType.SEPARATOR, (0, 0, 2, 2)), A4_300DPI, crop=tiny
    )

    assert features.ink_ratio is None
    assert features.has_appearance is False


# ── provenance ───────────────────────────────────────────────────────────────

def test_a_record_built_now_is_current():
    assert _provenance().is_current is True


def test_a_record_from_an_older_extractor_is_not_current():
    assert _provenance(feature_version="0").is_current is False


def test_the_versioning_block_carries_every_field_the_plan_requires():
    row = _provenance(model_version="pp-structure-v3").as_row()

    assert set(row) == {
        "feature_version", "detector_name", "detector_version", "model_version",
        "source_document", "source_page", "created_at",
    }


# ── human actions ────────────────────────────────────────────────────────────

def test_an_unknown_action_is_refused():
    with pytest.raises(ValueError, match="unknown action"):
        LayoutFeedback(action="maybe", document_id="d", page_no=1,
                       provenance=_provenance())


def _feedback(action: str, detector: str = "header") -> LayoutFeedback:
    return LayoutFeedback(action=action, document_id="d", page_no=1,
                          provenance=_provenance(detector_name=detector))


def test_the_five_actions_answer_two_separate_questions():
    """Finding a region and naming it are different skills with different fixes."""
    rows = [
        _feedback(LayoutAction.CONFIRMED),
        _feedback(LayoutAction.CONFIRMED),
        _feedback(LayoutAction.CORRECTED),   # found it, named it wrong
        _feedback(LayoutAction.DELETED),     # invented it
        _feedback(LayoutAction.ADDED),       # missed it
    ]

    score = tally(rows)["header"]

    assert score.type_accuracy == pytest.approx(2 / 3)          # 2 of 3 named right
    assert score.detection_precision == pytest.approx(3 / 4)    # 3 of 4 were real
    assert score.detection_recall == pytest.approx(3 / 4)       # found 3 of 4


def test_collapsing_the_actions_would_hide_the_difference():
    """Two detectors, same 'disagreement' count, opposite problems."""
    sloppy_names = tally([_feedback(LayoutAction.CORRECTED, "a") for _ in range(4)])["a"]
    misses_things = tally([_feedback(LayoutAction.ADDED, "b") for _ in range(4)])["b"]

    assert sloppy_names.type_accuracy == 0.0
    assert misses_things.type_accuracy is None, "it never named anything wrong"
    assert misses_things.detection_recall == 0.0


def test_a_detector_nobody_reviewed_scores_none_not_zero():
    """Unmeasured must not read as failed."""
    score = tally([])
    assert score == {}

    empty = tally([_feedback(LayoutAction.REJECTED)])
    assert empty == {}, "a rejected template says nothing about a detector"


def test_rejected_is_still_counted_somewhere():
    counts = counts_by_action([
        _feedback(LayoutAction.REJECTED),
        _feedback(LayoutAction.CONFIRMED),
    ])

    assert counts[LayoutAction.REJECTED] == 1
    assert counts[LayoutAction.CONFIRMED] == 1
    assert set(counts) == set(LayoutAction.ALL)


# ── the store ────────────────────────────────────────────────────────────────

@pytest.fixture
def store(tmp_path):
    with LayoutKnowledgeStore(tmp_path / "nested" / "layout.db") as opened:
        yield opened


def test_a_record_survives_the_round_trip(store):
    features = describe(_component(ComponentType.HEADER, (100, 60, 2280, 140)), A4_300DPI)

    store.remember(features, _provenance(), source="human")
    back = store.candidates()

    assert len(back) == 1
    assert back[0].features == features
    assert back[0].provenance.detector_name == "header"
    assert back[0].source == "human"


def test_a_detector_cannot_teach_itself(store):
    """The rule the whole store exists to enforce."""
    features = describe(_component(ComponentType.TABLE, (0, 0, 100, 100)), A4_300DPI)

    with pytest.raises(KnowledgeBaseError, match="only human-verified"):
        store.remember(features, _provenance(), source="detector")

    assert store.candidates() == []


def test_knowledge_from_an_older_extractor_is_not_offered_for_matching(store):
    """Stale features are not comparable, so they must not quietly answer."""
    features = describe(_component(ComponentType.TABLE, (0, 0, 100, 100)), A4_300DPI)

    store.remember(features, _provenance(feature_version="0"), source="human")

    assert store.candidates() == []
    assert len(store.candidates(include_stale=True)) == 1


def test_the_store_says_how_much_of_itself_is_unusable(store):
    features = describe(_component(ComponentType.TABLE, (0, 0, 100, 100)), A4_300DPI)
    store.remember(features, _provenance(), source="human")
    store.remember(features, _provenance(feature_version="0"), source="human")

    stats = store.stats()

    assert stats["total"] == 2
    assert stats["usable"] == 1
    assert stats["stale"] == 1
    assert stats["current_feature_version"] == FEATURE_VERSION


def test_candidates_can_be_narrowed_by_type_and_band(store):
    header = describe(_component(ComponentType.HEADER, (100, 60, 2280, 140)), A4_300DPI)
    footer = describe(_component(ComponentType.FOOTER, (100, 3300, 2280, 140)), A4_300DPI)
    store.remember(header, _provenance(), source="human")
    store.remember(footer, _provenance(), source="human")

    assert len(store.candidates(ComponentType.HEADER)) == 1
    assert len(store.candidates(page_band="bottom")) == 1
    assert len(store.candidates()) == 2


def test_feedback_survives_the_round_trip_with_its_boxes(store):
    store.record(LayoutFeedback(
        action=LayoutAction.CORRECTED,
        document_id="sample.pdf",
        page_no=2,
        provenance=_provenance(),
        detected_type=ComponentType.PARAGRAPH,
        human_type=ComponentType.HEADING,
        bbox_before=BBox(10, 20, 30, 40),
        bbox_after=BBox(11, 21, 31, 41),
        user_id="gurudev",
    ))

    row = store.feedback(document_id="sample.pdf")[0]

    assert row.action == LayoutAction.CORRECTED
    assert row.detected_type == ComponentType.PARAGRAPH
    assert row.human_type == ComponentType.HEADING
    assert row.bbox_before == BBox(10, 20, 30, 40)
    assert row.bbox_after == BBox(11, 21, 31, 41)
    assert row.user_id == "gurudev"


def test_feedback_can_be_read_back_and_scored(store):
    for action in (LayoutAction.CONFIRMED, LayoutAction.CONFIRMED, LayoutAction.CORRECTED):
        store.record(LayoutFeedback(action=action, document_id="d", page_no=1,
                                    provenance=_provenance()))

    score = tally(store.feedback())["header"]

    assert score.confirmed == 2
    assert score.type_accuracy == pytest.approx(2 / 3)


def test_filtering_feedback_by_an_unknown_action_is_refused(store):
    with pytest.raises(ValueError, match="unknown action"):
        store.feedback(action="probably")


# ── moving a store ───────────────────────────────────────────────────────────

def test_export_and_import_preserve_the_features_exactly(store, tmp_path):
    features = describe(_component(ComponentType.HEADER, (100, 60, 2280, 140)), A4_300DPI)
    store.remember(features, _provenance(), source="human")

    written = store.export_to(tmp_path / "out" / "kb.json")
    assert written == {"knowledge": 1, "feedback": 0}

    with LayoutKnowledgeStore(tmp_path / "second.db") as other:
        read = other.import_from(tmp_path / "out" / "kb.json")
        arrived = other.candidates()

    assert read["knowledge"] == 1
    assert arrived[0].features == features
    assert arrived[0].source == "manual_import", "it came in through a person, not a detector"


def test_the_action_log_travels_with_the_knowledge(store, tmp_path):
    """Separated, the counts that make a detector measurable are lost."""
    store.record(LayoutFeedback(action=LayoutAction.CORRECTED, document_id="d",
                                page_no=1, provenance=_provenance(),
                                detected_type=ComponentType.PARAGRAPH,
                                human_type=ComponentType.HEADING,
                                bbox_before=BBox(1, 2, 3, 4)))
    store.export_to(tmp_path / "kb.json")

    with LayoutKnowledgeStore(tmp_path / "second.db") as other:
        other.import_from(tmp_path / "kb.json")
        row = other.feedback()[0]

    assert row.action == LayoutAction.CORRECTED
    assert row.human_type == ComponentType.HEADING
    assert row.bbox_before == BBox(1, 2, 3, 4)


def test_stale_records_are_carried_across_and_counted(store, tmp_path):
    """An export is a copy, not a filtered view — but the other end is told."""
    features = describe(_component(ComponentType.TABLE, (0, 0, 100, 100)), A4_300DPI)
    store.remember(features, _provenance(), source="human")
    store.remember(features, _provenance(feature_version="0"), source="human")
    store.export_to(tmp_path / "kb.json")

    with LayoutKnowledgeStore(tmp_path / "second.db") as other:
        read = other.import_from(tmp_path / "kb.json")

        assert read["knowledge"] == 2
        assert read["stale"] == 1
        assert len(other.candidates()) == 1, "the stale one is kept but not offered"


def test_an_unreadable_export_format_is_refused_not_guessed_at(store, tmp_path):
    path = tmp_path / "kb.json"
    path.write_text('{"format_version": 99, "knowledge": []}', encoding="utf-8")

    with pytest.raises(KnowledgeBaseError, match="export format"):
        store.import_from(path)


def test_reopening_the_file_keeps_what_was_written(tmp_path):
    """It is a file other applications can read, so it has to be a real file."""
    path = tmp_path / "layout.db"
    features = describe(_component(ComponentType.TITLE, (0, 0, 100, 50)), A4_300DPI)

    with LayoutKnowledgeStore(path) as first:
        first.remember(features, _provenance(), source="human")

    with LayoutKnowledgeStore(path) as second:
        assert len(second.candidates()) == 1
