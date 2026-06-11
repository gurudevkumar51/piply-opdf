"""Pydantic models for Phase 5/6 — OCR results and confidence analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class CharResult(BaseModel):
    """OCR result for a single character."""

    char: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: tuple[int, int, int, int] | None = None  # (x, y, x2, y2)


class WordResult(BaseModel):
    """OCR result for a single word."""

    text: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    bbox: tuple[int, int, int, int] | None = None  # (x, y, x2, y2)
    chars: list[CharResult] = Field(default_factory=list)


class RegionOCRResult(BaseModel):
    """OCR result for a single layout region (paragraph, cell, etc.)."""

    region_id: str
    region_type: str
    page_number: int

    # Raw OCR output
    raw_text: str = Field(default="", description="Full extracted text for this region")
    words: list[WordResult] = Field(default_factory=list)

    # Aggregated confidence scores
    char_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Mean character-level confidence"
    )
    word_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Mean word-level confidence"
    )
    region_confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Overall region confidence"
    )

    # Human correction (set by Phase 8)
    corrected_text: str | None = Field(
        default=None, description="Human-corrected text (overrides raw_text)"
    )
    is_corrected: bool = Field(default=False)

    @property
    def final_text(self) -> str:
        """Return corrected text if available, else raw OCR text."""
        return self.corrected_text if self.is_corrected else self.raw_text

    # Path to the source image that was OCR'd
    source_image_path: str | None = None


class OCRResult(BaseModel):
    """Full OCR result for an entire document."""

    source_path: str
    page_count: int
    engine_used: str = Field(..., description="Name of OCR engine used")
    regions: list[RegionOCRResult] = Field(default_factory=list)

    # Aggregate stats
    total_words: int = Field(default=0)
    mean_confidence: float = Field(default=0.0)
    doubtful_region_count: int = Field(default=0)

    def regions_for_page(self, page_number: int) -> list[RegionOCRResult]:
        return [r for r in self.regions if r.page_number == page_number]

    def doubtful_regions(self, threshold: float = 0.80) -> list[RegionOCRResult]:
        return [r for r in self.regions if r.region_confidence < threshold]
