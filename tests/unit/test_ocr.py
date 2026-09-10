"""
The configurable OCR layer.

Most of these need no OCR engine at all: the registry, the configuration, the
fallback rules and the contract are all testable without loading a model, which
keeps the suite fast and keeps it passing on a machine where nothing is
installed.

The few that genuinely need PaddleOCR skip themselves when it is absent — the
same distinction the layer itself draws between *"no text here"* and *"no engine
installed"*.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from piply_opdf.ocr import (
    DEFAULT_ENGINE,
    OCREngine,
    OCRResult,
    available_engines,
    create_engine,
    read_text,
    register,
    registered_engines,
    resolve_engine,
)


def _crop(text: str, scale: float = 0.9, pad: int = 14) -> np.ndarray:
    (w, h), base = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
    image = np.full((h + base + pad * 2, w + pad * 2, 3), 255, np.uint8)
    cv2.putText(image, text, (pad, h + pad), cv2.FONT_HERSHEY_SIMPLEX,
                scale, (20, 20, 20), 2, cv2.LINE_AA)
    return image


def _paddle_ready() -> bool:
    return "paddleocr" in available_engines()


needs_paddle = pytest.mark.skipif(not _paddle_ready(), reason="PaddleOCR not installed")


# ── the registry ─────────────────────────────────────────────────────────────

def test_paddleocr_is_the_primary_engine():
    assert DEFAULT_ENGINE == "paddleocr"


def test_both_engines_are_registered():
    names = registered_engines()
    assert "paddleocr" in names
    assert "tesseract" in names


def test_an_engine_can_be_added_without_touching_callers():
    """The point of the registry: a future engine is a file and a decorator."""

    @register("pretend")
    class Pretend(OCREngine):
        def is_available(self) -> bool:
            return True

        def read(self, image, *, salt=False):
            return OCRResult("from pretend", 0.9, self.name)

    try:
        assert "pretend" in registered_engines()
        assert read_text(_crop("x"), engine="pretend").text == "from pretend"
    finally:
        from piply_opdf.ocr import base
        base._ENGINES.pop("pretend", None)


def test_an_unknown_engine_says_what_it_expected():
    with pytest.raises(KeyError, match="paddleocr"):
        create_engine("does-not-exist")


# ── availability is a question, not a crash ──────────────────────────────────

def test_availability_is_reported_not_raised():
    """A missing library must answer False, never blow up."""
    for name in registered_engines():
        assert isinstance(create_engine(name).is_available(), bool)


def test_reading_without_any_engine_returns_a_reason(monkeypatch):
    monkeypatch.setattr("piply_opdf.ocr.resolve_engine", lambda *a, **k: None)
    result = read_text(_crop("43438"))

    assert result.is_empty
    assert result.confidence == 0.0
    assert result.engine == "none"
    assert "no OCR engine" in result.evidence["reason"]


def test_an_unavailable_engine_does_not_fabricate_text():
    """The distinction that matters: no text found, versus nothing to find it."""
    result = read_text(_crop("43438"), engine="tesseract")
    if "tesseract" in available_engines():
        pytest.skip("tesseract is installed here")
    assert result.is_empty
    assert result.confidence == 0.0
    assert "reason" in result.evidence


# ── the result carries its reasoning ─────────────────────────────────────────

def test_a_result_records_which_engine_read_it():
    """Per the governing principle: never just a number."""
    assert OCRResult("x", 0.9, "paddleocr").engine == "paddleocr"
    assert OCRResult.nothing().engine == "none"


def test_nothing_is_empty_and_unconfident():
    result = OCRResult.nothing("paddleocr", reason="unreadable image")
    assert result.is_empty
    assert result.confidence == 0.0
    assert result.evidence["reason"] == "unreadable image"


# ── reading, where an engine exists ──────────────────────────────────────────

@needs_paddle
def test_the_configured_engine_is_used():
    engine = resolve_engine()
    assert engine is not None
    assert engine.name == "paddleocr"


@needs_paddle
@pytest.mark.parametrize("value", ["43438", "AOKPN4722Q", "57,550.00"])
def test_a_clean_crop_is_read_correctly(value):
    result = read_text(_crop(value))
    assert result.text.strip() == value
    assert result.confidence > 0.8
    assert result.engine == "paddleocr"


@needs_paddle
def test_a_crop_cut_through_its_own_text_is_marked_down():
    """A tight crop that sliced a glyph gives a confident, wrong reading.

    Measured: `43438` sliced through the leading 4 reads as `13438` at
    confidence 1.0 — the engine has no way to know part of the digit is
    missing. Ink reaching the crop border is the evidence that it is, so the
    confidence is halved and the reading is flagged rather than trusted.
    """
    whole = _crop("43438")
    sliced = whole[:, 34:].copy()

    clean = read_text(whole)
    cut = read_text(sliced)

    assert "edge_penalty" not in clean.evidence
    assert "edge_penalty" in cut.evidence, "a sliced crop was not marked down"
    assert cut.confidence < clean.confidence


@needs_paddle
def test_an_unreadable_image_is_survivable():
    assert read_text(np.zeros((0, 0, 3), np.uint8)).is_empty
    assert read_text("no/such/file.png").is_empty
