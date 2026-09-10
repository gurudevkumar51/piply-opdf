"""
The baseline layout detector, and its adapter.

Most of these need no model: the label mapping, the availability contract and
the degradation behaviour are all testable without loading PP-DocLayout, which
keeps the suite fast and keeps it green on a machine with nothing installed.

The few that genuinely need the model skip themselves — the same distinction
the adapter itself draws between "no regions here" and "no model installed".
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from piply_opdf.baseline import (
    LABEL_MAP,
    PRECISE_LABELS,
    PaddleLayoutBaseline,
    baseline_detector,
    is_available,
    to_component_type,
)
from piply_opdf.core.types import ComponentType, PageContext

needs_model = pytest.mark.skipif(not is_available(), reason="PP-DocLayout not installed")


def _page(tmp_path, image: np.ndarray) -> PageContext:
    path = tmp_path / "page.png"
    cv2.imwrite(str(path), image)
    return PageContext(page_number=1, source_path=path, image=image, dpi=300)


def _document_page(width: int = 1240, height: int = 1754) -> np.ndarray:
    """A title, a heading and body text — the shape the model is trained on."""
    page = np.full((height, width, 3), 255, np.uint8)
    cv2.putText(page, "ANNUAL REPORT", (260, 150), cv2.FONT_HERSHEY_SIMPLEX,
                1.8, (20, 20, 20), 4, cv2.LINE_AA)
    cv2.putText(page, "1. Introduction", (120, 320), cv2.FONT_HERSHEY_SIMPLEX,
                1.0, (20, 20, 20), 3, cv2.LINE_AA)
    body = "the quick brown fox jumps over the lazy dog and keeps running "
    for row in range(18):
        cv2.putText(page, (body * 3)[:64], (120, 400 + row * 42),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (35, 35, 35), 2, cv2.LINE_AA)
    return page


# ── the label vocabulary ─────────────────────────────────────────────────────

def test_the_model_distinguishes_a_title_from_a_heading():
    """Rule 4's first boundary, decided by training rather than a font size."""
    assert to_component_type("doc_title") == ComponentType.TITLE
    assert to_component_type("paragraph_title") == ComponentType.HEADING


def test_subheading_is_never_produced_by_the_baseline():
    """The model has no third heading level, so it must not invent one.

    Heading versus subheading is left to the rules, and to a person where the
    rules cannot decide.
    """
    assert ComponentType.SUBHEADING not in LABEL_MAP.values()


def test_the_core_labels_map_where_expected():
    for label, expected in (
        ("text", ComponentType.PARAGRAPH),
        ("table", ComponentType.TABLE),
        ("header", ComponentType.HEADER),
        ("footer", ComponentType.FOOTER),
        ("image", ComponentType.IMAGE),
        ("seal", ComponentType.STAMP),
    ):
        assert to_component_type(label) == expected, label


def test_an_unknown_label_is_kept_as_unknown_not_guessed():
    """A region the model named and we cannot interpret is still a region."""
    assert to_component_type("some_future_class") == ComponentType.UNKNOWN
    assert to_component_type("") == ComponentType.UNKNOWN


def test_every_mapped_type_is_in_the_vocabulary():
    for component_type in LABEL_MAP.values():
        assert component_type in ComponentType.ALL, component_type


def test_precise_labels_are_all_mapped():
    for label in PRECISE_LABELS:
        assert label in LABEL_MAP, label


# ── the adapter contract ─────────────────────────────────────────────────────

def test_availability_is_answered_not_raised():
    assert isinstance(is_available(), bool)


def test_a_blank_page_context_yields_nothing(tmp_path):
    page = PageContext(page_number=1, source_path=tmp_path / "x.png",
                       image=np.zeros((0, 0, 3), np.uint8), dpi=300)
    assert baseline_detector().detect(page) == []


def test_the_package_runs_without_the_model(tmp_path, monkeypatch):
    """The point of an adapter: no model means no regions, never a crash."""
    monkeypatch.setattr("piply_opdf.baseline.paddle_layout._layout_model", lambda: None)

    page = _page(tmp_path, _document_page())
    assert PaddleLayoutBaseline().detect(page) == []


def test_a_failing_model_does_not_stop_the_page(tmp_path, monkeypatch):
    class Broken:
        def predict(self, _image):
            raise RuntimeError("model exploded")

    monkeypatch.setattr("piply_opdf.baseline.paddle_layout._layout_model", lambda: Broken())
    assert PaddleLayoutBaseline().detect(_page(tmp_path, _document_page())) == []


def test_low_scoring_regions_are_dropped(tmp_path, monkeypatch):
    class Noisy:
        def predict(self, _image):
            return [{"boxes": [
                {"label": "text", "score": 0.90, "coordinate": [10, 10, 200, 60]},
                {"label": "text", "score": 0.05, "coordinate": [10, 80, 200, 130]},
            ]}]

    monkeypatch.setattr("piply_opdf.baseline.paddle_layout._layout_model", lambda: Noisy())
    found = PaddleLayoutBaseline(min_score=0.35).detect(_page(tmp_path, _document_page()))

    assert len(found) == 1
    assert found[0].confidence == pytest.approx(0.90)


def test_boxes_are_clipped_to_the_page(tmp_path, monkeypatch):
    class Overflowing:
        def predict(self, _image):
            return [{"boxes": [
                {"label": "text", "score": 0.9, "coordinate": [-50, -50, 99999, 99999]},
            ]}]

    monkeypatch.setattr("piply_opdf.baseline.paddle_layout._layout_model", lambda: Overflowing())
    page = _page(tmp_path, _document_page())
    found = PaddleLayoutBaseline().detect(page)

    assert len(found) == 1
    box = found[0].bbox
    assert box.x >= 0 and box.y >= 0
    assert box.x1 <= page.width and box.y1 <= page.height


def test_a_degenerate_box_is_skipped(tmp_path, monkeypatch):
    class Degenerate:
        def predict(self, _image):
            return [{"boxes": [
                {"label": "text", "score": 0.9, "coordinate": [10, 10, 10, 10]},
                {"label": "text", "score": 0.9, "coordinate": None},
            ]}]

    monkeypatch.setattr("piply_opdf.baseline.paddle_layout._layout_model", lambda: Degenerate())
    assert PaddleLayoutBaseline().detect(_page(tmp_path, _document_page())) == []


def test_a_component_records_where_it_came_from(tmp_path, monkeypatch):
    """Per the governing principle: never just a type and a number."""
    class One:
        def predict(self, _image):
            return [{"boxes": [
                {"label": "paragraph_title", "score": 0.77, "coordinate": [10, 10, 300, 70]},
            ]}]

    monkeypatch.setattr("piply_opdf.baseline.paddle_layout._layout_model", lambda: One())
    found = PaddleLayoutBaseline().detect(_page(tmp_path, _document_page()))

    assert found[0].type == ComponentType.HEADING
    assert found[0].metadata["detector"] == "paddle-layout"
    assert found[0].metadata["baseline_label"] == "paragraph_title"
    assert found[0].metadata["model_confidence"] == pytest.approx(0.77)


# ── with the real model ──────────────────────────────────────────────────────

@needs_model
def test_the_model_finds_regions_on_a_document_page(tmp_path):
    found = baseline_detector().detect(_page(tmp_path, _document_page()))
    assert found, "no regions found on a page of title, heading and body text"
    assert all(c.bbox.area > 0 for c in found)
    assert all(0.0 <= c.confidence <= 1.0 for c in found)
