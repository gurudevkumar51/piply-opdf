"""Unit tests for Phase 1 — Document Assessment Engine."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from piply_opdf.models.assessment import AssessmentResult, QualityLevel
from piply_opdf.phases.phase1_assess import DocumentAssessor


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_gray_image(h: int = 200, w: int = 300, value: int = 200) -> np.ndarray:
    """Create a plain grayscale image."""
    return np.full((h, w), value, dtype=np.uint8)


def make_textured_image(h: int = 200, w: int = 300) -> np.ndarray:
    """Create a noisy grayscale image with visible structure."""
    rng = np.random.default_rng(42)
    img = rng.integers(50, 200, (h, w), dtype=np.uint8)
    # Draw some black rectangles to simulate text
    img[20:30, 10:100] = 10
    img[50:60, 10:150] = 10
    img[80:90, 10:80] = 10
    return img


@pytest.fixture
def assessor() -> DocumentAssessor:
    return DocumentAssessor()


# ── Unit tests ────────────────────────────────────────────────────────────────


class TestDocumentAssessorInit:
    def test_default_thresholds(self, assessor: DocumentAssessor) -> None:
        assert assessor.blur_threshold == 100.0
        assert assessor.noise_threshold == 0.02
        assert assessor.contrast_threshold == 50.0
        # Tracks config/default.yaml. Flagging is deliberately sensitive; the
        # decision to actually resample is gated separately by
        # preprocessing.deskew.DEFAULT_MIN_CORRECTION.
        assert assessor.skew_threshold == 0.1

    def test_custom_config(self) -> None:
        from piply_opdf.config import Config
        cfg = Config.__new__(Config)
        cfg._data = {
            "assessment": {
                "blur_threshold": 50.0,
                "noise_threshold": 0.01,
                "contrast_threshold": 30.0,
                "skew_threshold": 1.0,
                "min_dpi": 200,
                "render_dpi": 150,
            }
        }
        a = DocumentAssessor(config=cfg)
        assert a.blur_threshold == 50.0
        assert a.skew_threshold == 1.0


class TestAssessImage:
    def test_sharp_image_not_blurry(self, assessor: DocumentAssessor) -> None:
        import cv2
        # A strong edge image should have high Laplacian variance
        img = np.zeros((100, 100), dtype=np.uint8)
        img[40:60, 40:60] = 255
        page = assessor._assess_image(img, page_number=1)
        # Strong edges → high blur score
        assert page.blur_score > 0

    def test_flat_image_is_blurry(self, assessor: DocumentAssessor) -> None:
        img = make_gray_image(value=180)
        page = assessor._assess_image(img, page_number=1)
        assert page.is_blurry is True

    def test_flat_image_low_contrast(self, assessor: DocumentAssessor) -> None:
        img = make_gray_image(value=200)
        page = assessor._assess_image(img, page_number=1)
        assert page.is_low_contrast is True

    def test_page_number_preserved(self, assessor: DocumentAssessor) -> None:
        img = make_gray_image()
        page = assessor._assess_image(img, page_number=3)
        assert page.page_number == 3

    def test_width_height_recorded(self, assessor: DocumentAssessor) -> None:
        img = make_gray_image(h=100, w=200)
        page = assessor._assess_image(img, page_number=1)
        assert page.width_px == 200
        assert page.height_px == 100

    def test_quality_poor_for_flat_image(self, assessor: DocumentAssessor) -> None:
        img = make_gray_image(value=180)
        page = assessor._assess_image(img, page_number=1)
        # Flat image triggers blur + contrast issues → POOR
        assert page.quality in (QualityLevel.ACCEPTABLE, QualityLevel.POOR)


class TestBuildResult:
    def test_no_enhancement_needed(self, assessor: DocumentAssessor) -> None:
        from piply_opdf.models.assessment import PageAssessment
        page = PageAssessment(
            page_number=1,
            dpi=300.0,
            dpi_ok=True,
            blur_score=200.0,
            is_blurry=False,
            noise_score=0.01,
            is_noisy=False,
            contrast_score=80.0,
            is_low_contrast=False,
            skew_angle=0.5,
            needs_deskew=False,
            quality=QualityLevel.GOOD,
            enhancement_needed=False,
            width_px=800,
            height_px=1100,
        )
        result = assessor._build_result("/fake/path.pdf", [page])
        assert result.any_enhancement_needed is False
        assert result.recommended_enhancements == []

    def test_recommended_enhancements_populated(self, assessor: DocumentAssessor) -> None:
        from piply_opdf.models.assessment import PageAssessment
        page = PageAssessment(
            page_number=1,
            dpi=300.0,
            dpi_ok=True,
            blur_score=20.0,
            is_blurry=True,
            noise_score=0.05,
            is_noisy=True,
            contrast_score=30.0,
            is_low_contrast=True,
            skew_angle=3.5,
            needs_deskew=True,
            quality=QualityLevel.POOR,
            enhancement_needed=True,
            width_px=800,
            height_px=1100,
        )
        result = assessor._build_result("/fake/path.pdf", [page])
        assert "deskew" in result.recommended_enhancements
        assert "sharpen" in result.recommended_enhancements
        assert "denoise" in result.recommended_enhancements
        assert "contrast_enhancement" in result.recommended_enhancements


class TestAssessResultModel:
    def test_summary_returns_dict(self) -> None:
        from piply_opdf.models.assessment import PageAssessment
        page = PageAssessment(
            page_number=1,
            dpi=300.0, dpi_ok=True,
            blur_score=200.0, is_blurry=False,
            noise_score=0.01, is_noisy=False,
            contrast_score=80.0, is_low_contrast=False,
            skew_angle=0.5, needs_deskew=False,
            quality=QualityLevel.GOOD, enhancement_needed=False,
            width_px=800, height_px=1100,
        )
        result = AssessmentResult(
            source_path="/fake/doc.pdf",
            page_count=1,
            pages=[page],
            any_blurry=False,
            any_noisy=False,
            any_low_contrast=False,
            any_needs_deskew=False,
            any_enhancement_needed=False,
        )
        s = result.summary()
        assert s["pages"] == 1
        assert "issues" in s

    def test_json_serialisation_roundtrip(self) -> None:
        from piply_opdf.models.assessment import PageAssessment
        page = PageAssessment(
            page_number=1,
            dpi=300.0, dpi_ok=True,
            blur_score=150.0, is_blurry=False,
            noise_score=0.01, is_noisy=False,
            contrast_score=70.0, is_low_contrast=False,
            skew_angle=1.0, needs_deskew=False,
            quality=QualityLevel.GOOD, enhancement_needed=False,
            width_px=800, height_px=1100,
        )
        result = AssessmentResult(
            source_path="/fake/doc.pdf",
            page_count=1,
            pages=[page],
            any_blurry=False,
            any_noisy=False,
            any_low_contrast=False,
            any_needs_deskew=False,
            any_enhancement_needed=False,
        )
        json_str = result.model_dump_json()
        restored = AssessmentResult.model_validate_json(json_str)
        assert restored.source_path == result.source_path
        assert restored.pages[0].blur_score == result.pages[0].blur_score
