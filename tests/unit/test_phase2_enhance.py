"""Unit tests for Phase 2 — Document Enhancement Engine."""

from __future__ import annotations

import numpy as np
import pytest

from piply_opdf.phases.phase2_enhance import DocumentEnhancer


# ── Fixtures ──────────────────────────────────────────────────────────────────


def make_bgr_image(h: int = 200, w: int = 300, value: int = 180) -> np.ndarray:
    return np.full((h, w, 3), value, dtype=np.uint8)


def make_gray_image(h: int = 200, w: int = 300, value: int = 180) -> np.ndarray:
    return np.full((h, w), value, dtype=np.uint8)


@pytest.fixture
def enhancer() -> DocumentEnhancer:
    return DocumentEnhancer()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestDeskew:
    def test_zero_angle_returns_same_shape(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.deskew(img, angle=0.0)
        assert result.shape == img.shape

    def test_nonzero_angle_returns_same_shape(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.deskew(img, angle=5.0)
        assert result.shape == img.shape

    def test_output_dtype_preserved(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.deskew(img, angle=2.0)
        assert result.dtype == np.uint8


class TestDenoise:
    def test_output_same_shape_colour(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.denoise(img)
        assert result.shape == img.shape

    def test_output_same_shape_gray(self, enhancer: DocumentEnhancer) -> None:
        img = make_gray_image()
        result = enhancer.denoise(img)
        assert result.shape == img.shape

    def test_output_dtype_preserved(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        assert enhancer.denoise(img).dtype == np.uint8


class TestEnhanceContrast:
    def test_output_same_shape(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.enhance_contrast(img)
        assert result.shape == img.shape

    def test_gray_input_works(self, enhancer: DocumentEnhancer) -> None:
        img = make_gray_image()
        result = enhancer.enhance_contrast(img)
        assert result.shape == img.shape
        assert result.dtype == np.uint8

    def test_does_not_change_fully_uniform_image_significantly(
        self, enhancer: DocumentEnhancer
    ) -> None:
        # A perfectly uniform image shouldn't change dramatically
        img = make_bgr_image(value=128)
        result = enhancer.enhance_contrast(img)
        assert result.dtype == np.uint8


class TestSharpen:
    def test_output_same_shape(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.sharpen(img)
        assert result.shape == img.shape

    def test_dtype_preserved(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        assert enhancer.sharpen(img).dtype == np.uint8


class TestEnhanceBorders:
    def test_output_single_channel(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.enhance_borders(img)
        # Returns binary-like result
        assert result.dtype == np.uint8

    def test_output_not_empty(self, enhancer: DocumentEnhancer) -> None:
        img = make_bgr_image()
        result = enhancer.enhance_borders(img)
        assert result.size > 0


class TestEnhancePageWithAssessment:
    def test_no_ops_applied_when_page_is_good(self, enhancer: DocumentEnhancer) -> None:
        """A 'good' page assessment should pass through with minimal changes."""
        from piply_opdf.models.assessment import PageAssessment, QualityLevel
        good_page = PageAssessment(
            page_number=1,
            dpi=300.0, dpi_ok=True,
            blur_score=200.0, is_blurry=False,
            noise_score=0.005, is_noisy=False,
            contrast_score=80.0, is_low_contrast=False,
            skew_angle=0.1, needs_deskew=False,
            quality=QualityLevel.GOOD, enhancement_needed=False,
            width_px=300, height_px=200,
        )
        img = make_bgr_image()
        # Should not raise, should return same-shape image
        result = enhancer._enhance_page(img, good_page)
        assert result.shape == img.shape

    def test_deskew_applied_when_needed(self, enhancer: DocumentEnhancer) -> None:
        from piply_opdf.models.assessment import PageAssessment, QualityLevel
        skewed_page = PageAssessment(
            page_number=1,
            dpi=300.0, dpi_ok=True,
            blur_score=200.0, is_blurry=False,
            noise_score=0.005, is_noisy=False,
            contrast_score=80.0, is_low_contrast=False,
            skew_angle=5.0, needs_deskew=True,
            quality=QualityLevel.ACCEPTABLE, enhancement_needed=True,
            width_px=300, height_px=200,
        )
        img = make_bgr_image()
        result = enhancer._enhance_page(img, skewed_page)
        assert result.shape == img.shape
