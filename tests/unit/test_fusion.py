"""
Combining the baseline model with Piply's rules.

The behaviour being protected: neither detector is allowed to silently win.
Agreement is evidence, a lone finding is kept, and a disagreement goes to a
person carrying both opinions.

None of this needs a model — fusion works on components, so it is tested on
components.
"""

from __future__ import annotations

import pytest

from piply_opdf.core.types import BBox, ComponentType, DetectedComponent
from piply_opdf.fusion import fuse, specificity


def _component(kind: str, box: tuple[int, int, int, int], *,
               confidence: float = 0.7, source: str = "rules") -> DetectedComponent:
    return DetectedComponent(
        id=f"{kind.lower()}_{box[0]}_{box[1]}",
        type=kind,
        page=1,
        bbox=BBox(*box),
        confidence=confidence,
        metadata={"detector": source},
    )


# ── agreement ────────────────────────────────────────────────────────────────

def test_agreement_raises_confidence():
    """Two independent detectors reaching the same answer is real evidence."""
    mine = _component(ComponentType.TABLE, (100, 100, 400, 300), confidence=0.7)
    theirs = _component(ComponentType.TABLE, (105, 98, 395, 305), source="baseline")

    result = fuse([mine], [theirs])

    assert result.agreed == 1
    assert result.components[0].confidence > 0.7
    assert result.components[0].metadata["baseline_agreed"] is True


def test_confidence_never_exceeds_one():
    mine = _component(ComponentType.TABLE, (0, 0, 100, 100), confidence=0.98)
    theirs = _component(ComponentType.TABLE, (0, 0, 100, 100), source="baseline")

    result = fuse([mine], [theirs])
    assert result.components[0].confidence <= 1.0


# ── each keeps what it is good at ────────────────────────────────────────────

def test_a_region_only_the_baseline_found_is_kept():
    """The borderless table on `Sbizhub`: the rules find nothing there."""
    theirs = _component(ComponentType.TABLE, (140, 290, 2080, 920),
                        confidence=0.55, source="baseline")

    result = fuse([], [theirs])

    assert result.baseline_only == 1
    assert result.components[0].type == ComponentType.TABLE
    assert result.components[0].metadata["fusion"] == "baseline only"


def test_a_region_only_the_rules_found_is_kept():
    """A key-value pair: the model has no such concept."""
    mine = _component(ComponentType.KEY_VALUE, (60, 400, 900, 40))

    result = fuse([mine], [])

    assert result.piply_only == 1
    assert result.components[0].type == ComponentType.KEY_VALUE
    assert result.components[0].metadata["fusion"] == "rules only"


def test_nothing_is_lost_from_either_side():
    mine = [_component(ComponentType.KEY_VALUE, (0, 0, 100, 30)),
            _component(ComponentType.PANEL, (0, 200, 500, 400))]
    theirs = [_component(ComponentType.HEADING, (0, 700, 400, 50), source="baseline"),
              _component(ComponentType.IMAGE, (600, 700, 200, 200), source="baseline")]

    result = fuse(mine, theirs)
    assert len(result.components) == 4


# ── disagreement ─────────────────────────────────────────────────────────────

def test_a_disagreement_is_flagged_not_resolved_silently():
    """The failure this system exists to avoid: confidently wrong, unreviewed."""
    mine = _component(ComponentType.PARAGRAPH, (100, 100, 800, 400), confidence=0.9)
    theirs = _component(ComponentType.TABLE, (100, 100, 800, 400), source="baseline")

    result = fuse([mine], [theirs])
    component = result.components[0]

    assert result.disagreed == 1
    assert component.metadata["fusion_review"] is True
    assert component in result.needs_review
    assert component.confidence < 0.9, "a disputed region must not stay confident"


def test_a_disagreement_keeps_both_opinions():
    mine = _component(ComponentType.PARAGRAPH, (100, 100, 800, 400))
    theirs = _component(ComponentType.TABLE, (100, 100, 800, 400), source="baseline")

    component = fuse([mine], [theirs]).components[0]
    offered = {c["type"] for c in component.candidates}

    assert offered == {ComponentType.PARAGRAPH, ComponentType.TABLE}


def test_the_more_specific_type_wins():
    """"Key-value pair" tells an operator more than "text"."""
    mine = _component(ComponentType.KEY_VALUE, (100, 100, 800, 40))
    theirs = _component(ComponentType.PARAGRAPH, (100, 100, 800, 40), source="baseline")

    component = fuse([mine], [theirs]).components[0]

    assert component.type == ComponentType.KEY_VALUE
    assert component.metadata["fusion_winner"] == "rules"


def test_the_baseline_wins_when_it_is_the_specific_one():
    """The model knows a heading; the rules only saw text."""
    mine = _component(ComponentType.PARAGRAPH, (100, 100, 600, 50))
    theirs = _component(ComponentType.HEADING, (100, 100, 600, 50), source="baseline")

    component = fuse([mine], [theirs]).components[0]

    assert component.type == ComponentType.HEADING
    assert component.metadata["fusion_winner"] == "baseline"


# ── matching ─────────────────────────────────────────────────────────────────

def test_regions_that_do_not_overlap_are_not_matched():
    mine = _component(ComponentType.PARAGRAPH, (0, 0, 100, 100))
    theirs = _component(ComponentType.TABLE, (900, 900, 100, 100), source="baseline")

    result = fuse([mine], [theirs])

    assert result.agreed == 0 and result.disagreed == 0
    assert result.piply_only == 1 and result.baseline_only == 1


def test_a_loosely_drawn_region_still_matches():
    """A model wraps a paragraph loosely; the rules hug the ink.

    Overlap is measured against the *smaller* box for exactly this reason —
    intersection-over-union would call this pair a disagreement.
    """
    tight = _component(ComponentType.PARAGRAPH, (110, 110, 380, 180))
    loose = _component(ComponentType.PARAGRAPH, (100, 100, 400, 200), source="baseline")

    assert fuse([tight], [loose]).agreed == 1


def test_one_baseline_region_is_claimed_only_once():
    first = _component(ComponentType.PARAGRAPH, (100, 100, 200, 100))
    second = _component(ComponentType.PARAGRAPH, (100, 100, 200, 100))
    theirs = _component(ComponentType.PARAGRAPH, (100, 100, 200, 100), source="baseline")

    result = fuse([first, second], [theirs])

    assert result.agreed == 1
    assert result.piply_only == 1


# ── specificity ──────────────────────────────────────────────────────────────

def test_specificity_orders_useful_types_above_vague_ones():
    assert specificity(ComponentType.KEY_VALUE) > specificity(ComponentType.PARAGRAPH)
    assert specificity(ComponentType.TABLE) > specificity(ComponentType.SENTENCE)
    assert specificity(ComponentType.PARAGRAPH) > specificity(ComponentType.UNKNOWN)


def test_an_unlisted_type_is_least_specific():
    assert specificity("SOMETHING_NEW") == 0


# ── reporting ────────────────────────────────────────────────────────────────

def test_the_outcome_reports_what_happened():
    result = fuse(
        [_component(ComponentType.KEY_VALUE, (0, 0, 100, 30))],
        [_component(ComponentType.TABLE, (500, 500, 300, 300), source="baseline")],
    )
    assert "1 baseline only" in result.summary()
    assert "1 rules only" in result.summary()


def test_fusing_nothing_is_survivable():
    result = fuse([], [])
    assert result.components == []
    assert result.summary().startswith("0 components")


# ── containment is not identity ──────────────────────────────────────────────

def test_a_small_component_inside_a_large_region_does_not_claim_it():
    """Found by running it on `Sbizhub_C2219080509040.pdf`.

    The model's two table regions — the borderless bank statement the rules
    miss entirely — were each swallowed by a single sentence sitting inside
    them, because a small box inside a large one overlaps it completely. The
    one finding worth having was reported as "already known".

    Two boxes describe the same region only when they are also comparable in
    size. Otherwise one contains the other, which is nesting.
    """
    sentence = _component(ComponentType.SENTENCE, (200, 400, 180, 40))
    table = _component(ComponentType.TABLE, (140, 290, 2080, 920), source="baseline")

    result = fuse([sentence], [table])

    assert result.baseline_only == 1, "the table was swallowed by a sentence inside it"
    assert result.piply_only == 1
    assert result.agreed == 0 and result.disagreed == 0

    kinds = {c.type for c in result.components}
    assert kinds == {ComponentType.SENTENCE, ComponentType.TABLE}


def test_comparable_boxes_still_match():
    """The guard must not stop genuine matches."""
    mine = _component(ComponentType.TABLE, (100, 100, 800, 600))
    theirs = _component(ComponentType.TABLE, (110, 105, 780, 590), source="baseline")

    assert fuse([mine], [theirs]).agreed == 1


def test_the_size_guard_is_adjustable():
    small = _component(ComponentType.SENTENCE, (100, 100, 100, 50))
    large = _component(ComponentType.TABLE, (100, 100, 400, 200), source="baseline")

    strict = fuse([small], [large], min_size_ratio=0.9)
    loose = fuse([small], [large], min_size_ratio=0.05)

    assert strict.baseline_only == 1
    assert loose.disagreed == 1
