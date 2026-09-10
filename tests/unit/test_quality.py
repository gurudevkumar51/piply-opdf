"""
The two measurable quality signals.

**Coverage** answers "was anything lost?" and needs no ground truth, which
makes it the only detection quality number available without labelled data.

**Accuracy** answers "was it given the right type?" and needs someone to have
written the answer down. The harness is tested here against synthetic labels;
real labelled pages are still outstanding (backlog H1).
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from piply_opdf.core import BBox, ComponentType, DetectedComponent, PageContext
from piply_opdf.quality import (
    TARGET_COVERAGE,
    AccuracyReport,
    LabelledRegion,
    PageLabels,
    load_labels,
    measure_coverage,
    score_page,
)


def _page(image: np.ndarray, tmp_path: Path) -> PageContext:
    """A PageContext over a bare image — no PDF, so no text layer."""
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), image)
    return PageContext(page_number=1, source_path=path, image=image, dpi=300)


def _canvas(width: int = 800, height: int = 600) -> np.ndarray:
    return np.full((height, width, 3), 255, np.uint8)


def _block(image: np.ndarray, box: BBox, shade: int = 20) -> None:
    cv2.rectangle(image, (box.x, box.y), (box.x1, box.y1), (shade,) * 3, -1)


def _component(box: BBox, component_type: str = ComponentType.PARAGRAPH) -> DetectedComponent:
    return DetectedComponent(id="c", type=component_type, page=1, bbox=box)


# ── coverage ─────────────────────────────────────────────────────────────────

def test_blank_page_loses_nothing(tmp_path):
    """No ink means nothing to lose — not a division by zero."""
    report = measure_coverage(_page(_canvas(), tmp_path), [])
    assert report.accounted == 1.0
    assert report.total_ink == 0
    assert report.gaps == ()


def test_fully_covered_page_scores_one(tmp_path):
    image = _canvas()
    ink = BBox(100, 100, 300, 200)
    _block(image, ink)

    report = measure_coverage(_page(image, tmp_path), [_component(ink.padded(10))])

    assert report.accounted == pytest.approx(1.0)
    assert report.missed_ink == 0
    assert report.meets_target


def test_uncovered_ink_is_reported(tmp_path):
    """The point of the measurement: content nobody claimed shows up."""
    image = _canvas()
    claimed = BBox(80, 80, 200, 120)
    orphan = BBox(500, 380, 220, 140)
    _block(image, claimed)
    _block(image, orphan)

    report = measure_coverage(_page(image, tmp_path), [_component(claimed.padded(6))])

    assert not report.meets_target
    assert report.missed_ink > 0
    assert report.gaps, "an uncovered block should be reported as a gap"

    # the largest gap points at the orphan
    worst = report.gaps[0]
    assert worst.intersection_area(orphan) > orphan.area * 0.5


def test_nothing_detected_means_nothing_accounted(tmp_path):
    image = _canvas()
    _block(image, BBox(100, 100, 400, 300))

    report = measure_coverage(_page(image, tmp_path), [])

    assert report.accounted == pytest.approx(0.0)
    assert not report.meets_target


def test_children_count_towards_coverage(tmp_path):
    """A word inside a sentence covers its own area — depth must be walked."""
    image = _canvas()
    left = BBox(60, 60, 200, 100)
    right = BBox(400, 300, 200, 100)
    _block(image, left)
    _block(image, right)

    parent = _component(left.padded(5))
    parent.children = [_component(right.padded(5), ComponentType.WORD)]

    report = measure_coverage(_page(image, tmp_path), [parent])
    assert report.accounted == pytest.approx(1.0)


def test_boxes_outside_the_page_are_clipped(tmp_path):
    """A component running off the page must not crash the measurement."""
    image = _canvas()
    _block(image, BBox(100, 100, 200, 150))

    report = measure_coverage(
        _page(image, tmp_path), [_component(BBox(-500, -500, 5000, 5000))]
    )
    assert report.accounted == pytest.approx(1.0)


def test_specks_are_not_reported_as_gaps(tmp_path):
    """Dust is below the noise floor; gaps should point at real losses.

    Uses a real page size on purpose. The speck filter is a fraction of page
    area, so on a small canvas a two-pixel dot is proportionally a large
    region — which is not what a speck is on a 300 DPI scan.
    """
    rng = np.random.default_rng(5)
    image = _canvas(2550, 3300)
    for _ in range(40):
        x, y = int(rng.integers(40, 2500)), int(rng.integers(40, 3250))
        cv2.circle(image, (x, y), 1, (30, 30, 30), -1)

    report = measure_coverage(_page(image, tmp_path), [])
    assert report.gaps == (), f"specks listed as gaps: {report.gaps[:3]}"


def test_a_lost_paragraph_is_reported_even_on_a_noisy_page(tmp_path):
    """The filter must not hide a real loss among the dust."""
    rng = np.random.default_rng(6)
    image = _canvas(2550, 3300)
    for _ in range(40):
        x, y = int(rng.integers(40, 2500)), int(rng.integers(40, 3250))
        cv2.circle(image, (x, y), 1, (30, 30, 30), -1)

    lost = BBox(600, 1200, 900, 300)
    _block(image, lost)

    report = measure_coverage(_page(image, tmp_path), [])
    assert report.gaps, "a lost block should still be reported"
    assert report.gaps[0].intersection_area(lost) > lost.area * 0.5


def test_target_is_stated_and_strict():
    assert 0.99 <= TARGET_COVERAGE < 1.0


# ── accuracy ─────────────────────────────────────────────────────────────────

def _labels(*regions: LabelledRegion) -> PageLabels:
    return PageLabels(source="x.pdf", page=1, regions=regions)


def test_perfect_detection_scores_one():
    box = BBox(100, 100, 200, 80)
    report = score_page([_component(box)], _labels(LabelledRegion(ComponentType.PARAGRAPH, box)))

    score = report.by_type[ComponentType.PARAGRAPH]
    assert (score.precision, score.recall, score.f1) == (1.0, 1.0, 1.0)


def test_missed_region_lowers_recall_not_precision():
    found = BBox(100, 100, 200, 80)
    missed = BBox(400, 400, 200, 80)

    report = score_page(
        [_component(found)],
        _labels(LabelledRegion(ComponentType.PARAGRAPH, found),
                LabelledRegion(ComponentType.PARAGRAPH, missed)),
    )

    score = report.by_type[ComponentType.PARAGRAPH]
    assert score.precision == 1.0
    assert score.recall == pytest.approx(0.5)


def test_spurious_region_lowers_precision_not_recall():
    real = BBox(100, 100, 200, 80)
    invented = BBox(400, 400, 200, 80)

    report = score_page(
        [_component(real), _component(invented)],
        _labels(LabelledRegion(ComponentType.PARAGRAPH, real)),
    )

    score = report.by_type[ComponentType.PARAGRAPH]
    assert score.precision == pytest.approx(0.5)
    assert score.recall == 1.0


def test_wrong_type_counts_against_both_types():
    box = BBox(100, 100, 200, 80)
    report = score_page(
        [_component(box, ComponentType.TABLE)],
        _labels(LabelledRegion(ComponentType.PANEL, box)),
    )

    assert report.by_type[ComponentType.TABLE].precision == 0.0
    assert report.by_type[ComponentType.PANEL].recall == 0.0


def test_poorly_placed_box_is_not_a_match():
    """Right type, wrong place — overlap must be real to count."""
    truth = BBox(100, 100, 200, 80)
    barely = BBox(280, 160, 200, 80)

    report = score_page([_component(barely)], _labels(LabelledRegion(ComponentType.PARAGRAPH, truth)))
    assert report.by_type[ComponentType.PARAGRAPH].matched == 0


def test_two_detections_over_one_label_count_once():
    """Splitting a region in two is one hit and one false positive."""
    truth = BBox(100, 100, 400, 100)

    report = score_page(
        [_component(BBox(100, 100, 400, 96)), _component(BBox(100, 104, 400, 96))],
        _labels(LabelledRegion(ComponentType.PARAGRAPH, truth)),
    )

    score = report.by_type[ComponentType.PARAGRAPH]
    assert score.matched == 1
    assert score.detected == 2
    assert score.precision == pytest.approx(0.5)


def test_uncertain_labels_are_excluded():
    """A case a person could not decide is not evidence about the detector."""
    box = BBox(100, 100, 200, 80)
    report = score_page(
        [], _labels(LabelledRegion(ComponentType.SIGNATURE, box, uncertain=True))
    )
    assert report.by_type.get(ComponentType.SIGNATURE) is None


def test_reports_merge_across_pages():
    box = BBox(0, 0, 100, 100)
    total = AccuracyReport()
    for _ in range(3):
        total.merge(score_page([_component(box)],
                               _labels(LabelledRegion(ComponentType.PARAGRAPH, box))))

    score = total.by_type[ComponentType.PARAGRAPH]
    assert (score.matched, score.detected, score.labelled) == (3, 3, 3)


def test_labels_load_from_json(tmp_path):
    path = tmp_path / "page_001.json"
    path.write_text(
        '{"source": "invoice.pdf", "page": 2, "regions": ['
        '{"type": "table", "bbox": [10, 20, 30, 40]},'
        '{"type": "SIGNATURE", "bbox": [1, 2, 3, 4], "uncertain": true}]}',
        encoding="utf-8",
    )

    labels = load_labels(path)

    assert labels.source == "invoice.pdf"
    assert labels.page == 2
    assert labels.regions[0].type == "TABLE"        # normalised to upper case
    assert labels.regions[0].bbox.to_tuple() == (10, 20, 30, 40)
    assert labels.regions[1].uncertain is True


def test_empty_page_with_no_labels_is_not_a_failure():
    report = score_page([], _labels())
    assert report.by_type == {}
    assert report.as_table().startswith("type")
