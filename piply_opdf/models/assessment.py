"""Pydantic models for Phase 1 — Document Assessment output."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class QualityLevel(str, Enum):
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"


class PageAssessment(BaseModel):
    """Quality metrics for a single page."""

    page_number: int = Field(..., description="1-based page index")

    # DPI
    dpi: float = Field(..., description="Detected or estimated DPI")
    dpi_ok: bool = Field(..., description="True when DPI >= min_dpi threshold")

    # Blur
    blur_score: float = Field(..., description="Laplacian variance — higher = sharper")
    is_blurry: bool = Field(..., description="True when blur_score < blur_threshold")

    # Noise
    noise_score: float = Field(..., description="Normalised noise level (0–1)")
    is_noisy: bool = Field(..., description="True when noise_score > noise_threshold")

    # Contrast
    contrast_score: float = Field(..., description="RMS contrast (0–255)")
    is_low_contrast: bool = Field(..., description="True when contrast < contrast_threshold")

    # Skew
    skew_angle: float = Field(..., description="Estimated rotation angle in degrees")
    needs_deskew: bool = Field(..., description="True when |skew_angle| > skew_threshold")

    # Overall
    quality: QualityLevel = Field(..., description="Overall page quality rating")
    enhancement_needed: bool = Field(..., description="True when any issue was detected")

    # Raw metadata
    width_px: int = Field(..., description="Page width in pixels at render DPI")
    height_px: int = Field(..., description="Page height in pixels at render DPI")

    # Document Classification
    doc_type: str = Field("SCANNED", description="DIGITAL, SCANNED, or HYBRID")
    image_bboxes: list[tuple[int, int, int, int]] = Field(
        default_factory=list,
        description="Bounding boxes of embedded images in pixels at render DPI (x1, y1, x2, y2)"
    )


class AssessmentResult(BaseModel):
    """Full document assessment result."""

    source_path: str = Field(..., description="Absolute path to the source PDF/image")
    page_count: int = Field(..., description="Total number of pages assessed")
    pages: list[PageAssessment] = Field(..., description="Per-page assessment results")

    # Aggregate flags
    any_blurry: bool = Field(..., description="True if any page is blurry")
    any_noisy: bool = Field(..., description="True if any page is noisy")
    any_low_contrast: bool = Field(..., description="True if any page has low contrast")
    any_needs_deskew: bool = Field(..., description="True if any page needs deskewing")
    any_enhancement_needed: bool = Field(..., description="True if any page needs enhancement")

    # Suggested actions
    recommended_enhancements: list[str] = Field(
        default_factory=list,
        description="List of enhancement operations recommended based on assessment",
    )

    def summary(self) -> dict[str, Any]:
        """Return a human-readable summary dict."""
        return {
            "source": self.source_path,
            "pages": self.page_count,
            "issues": {
                "blurry_pages": sum(1 for p in self.pages if p.is_blurry),
                "noisy_pages": sum(1 for p in self.pages if p.is_noisy),
                "low_contrast_pages": sum(1 for p in self.pages if p.is_low_contrast),
                "skewed_pages": sum(1 for p in self.pages if p.needs_deskew),
            },
            "recommended_enhancements": self.recommended_enhancements,
        }
