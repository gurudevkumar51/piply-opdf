"""Unit tests for Phase 5 — OCR Engine."""

from __future__ import annotations

import numpy as np
import pytest

from piply_opdf.models.ocr_result import OCRResult, RegionOCRResult, WordResult
from piply_opdf.phases.phase5_ocr import OCRProcessor, TesseractEngine, PaddleOCREngine


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_word(text: str = "hello", conf: float = 0.95) -> WordResult:
    return WordResult(text=text, confidence=conf, bbox=(0, 0, 50, 20))


def make_bgr_image(h: int = 100, w: int = 200, value: int = 200) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestWordResult:
    def test_text_and_confidence(self) -> None:
        w = make_word("invoice", 0.92)
        assert w.text == "invoice"
        assert w.confidence == 0.92

    def test_confidence_clamps_to_range(self) -> None:
        with pytest.raises(Exception):
            WordResult(text="x", confidence=1.5)  # > 1.0 should fail validation


class TestRegionOCRResult:
    def test_final_text_uses_corrected_when_set(self) -> None:
        r = RegionOCRResult(
            region_id="p_001",
            region_type="paragraph",
            page_number=1,
            raw_text="invo1ce",
            corrected_text="invoice",
            is_corrected=True,
        )
        assert r.final_text == "invoice"

    def test_final_text_uses_raw_when_not_corrected(self) -> None:
        r = RegionOCRResult(
            region_id="p_001",
            region_type="paragraph",
            page_number=1,
            raw_text="invo1ce",
        )
        assert r.final_text == "invo1ce"

    def test_json_roundtrip(self) -> None:
        r = RegionOCRResult(
            region_id="cell_001",
            region_type="cell",
            page_number=2,
            raw_text="Total",
            words=[make_word("Total", 0.98)],
            word_confidence=0.98,
            region_confidence=0.98,
        )
        restored = RegionOCRResult.model_validate_json(r.model_dump_json())
        assert restored.region_id == r.region_id
        assert len(restored.words) == 1


class TestOCRResultModel:
    def test_doubtful_regions_below_threshold(self) -> None:
        good = RegionOCRResult(
            region_id="p_001", region_type="paragraph", page_number=1,
            region_confidence=0.95,
        )
        bad = RegionOCRResult(
            region_id="p_002", region_type="paragraph", page_number=1,
            region_confidence=0.50,
        )
        result = OCRResult(
            source_path="/fake/doc.pdf",
            page_count=1,
            engine_used="test",
            regions=[good, bad],
        )
        doubtful = result.doubtful_regions(threshold=0.80)
        assert len(doubtful) == 1
        assert doubtful[0].region_id == "p_002"

    def test_regions_for_page(self) -> None:
        r1 = RegionOCRResult(region_id="p1", region_type="paragraph", page_number=1)
        r2 = RegionOCRResult(region_id="p2", region_type="paragraph", page_number=2)
        result = OCRResult(
            source_path="/fake/doc.pdf",
            page_count=2,
            engine_used="test",
            regions=[r1, r2],
        )
        assert len(result.regions_for_page(1)) == 1
        assert len(result.regions_for_page(2)) == 1


class TestBuildRegionResult:
    def test_empty_words_returns_empty_text(self) -> None:
        result = OCRProcessor._build_region_result(
            words=[],
            region_id="p_001",
            region_type="paragraph",
            page_number=1,
        )
        assert result.raw_text == ""
        assert result.word_confidence == 0.0

    def test_words_joined_with_space(self) -> None:
        words = [make_word("Hello"), make_word("World")]
        result = OCRProcessor._build_region_result(
            words=words,
            region_id="p_001",
            region_type="paragraph",
            page_number=1,
        )
        assert result.raw_text == "Hello World"

    def test_confidence_averaged(self) -> None:
        words = [make_word("A", 0.8), make_word("B", 0.6)]
        result = OCRProcessor._build_region_result(
            words=words,
            region_id="p_001",
            region_type="paragraph",
            page_number=1,
        )
        assert abs(result.word_confidence - 0.7) < 0.01


class TestEngineAvailability:
    def test_tesseract_availability_returns_bool(self) -> None:
        engine = TesseractEngine()
        result = engine.is_available()
        assert isinstance(result, bool)

    def test_paddle_availability_returns_bool(self) -> None:
        engine = PaddleOCREngine()
        result = engine.is_available()
        assert isinstance(result, bool)

    def test_tesseract_engine_name(self) -> None:
        assert TesseractEngine().name == "tesseract"

    def test_paddle_engine_name(self) -> None:
        assert PaddleOCREngine().name == "paddleocr"
