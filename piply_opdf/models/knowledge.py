"""Pydantic models for Phase 9 — Knowledge Engine."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeEntry(BaseModel):
    """A single learned OCR entry stored in the knowledge base."""

    entry_id: str = Field(..., description="Unique identifier (UUID or hash-based)")

    # Visual signatures
    phash: str = Field(..., description="Perceptual hash (hex string) of the region image")
    dhash: str = Field(..., description="Difference hash (hex string)")
    histogram_signature: list[float] = Field(
        ..., description="Normalised intensity histogram (256 bins)"
    )

    # SSIM feature vector (when available)
    ssim_features: list[float] = Field(
        default_factory=list, description="SSIM-derived feature vector"
    )

    # Ground-truth label
    ocr_value: str = Field(..., description="Correct OCR text for this visual pattern")

    # Provenance
    region_type: str = Field(default="unknown", description="Layout region type")
    source_document: str = Field(default="", description="Original source document path")

    # Learning statistics
    validation_count: int = Field(
        default=1, description="Number of times this entry has been confirmed"
    )
    last_validated: datetime = Field(
        default_factory=datetime.utcnow, description="Timestamp of last human validation"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Confidence in this entry
    learned_confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score for this knowledge entry",
    )


class KnowledgePack(BaseModel):
    """Portable knowledge pack for export/import/merge operations."""

    version: str = Field(default="1.0", description="Pack schema version")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source_description: str = Field(default="", description="Human-readable provenance description")
    entry_count: int = Field(default=0)
    entries: list[KnowledgeEntry] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.entries)
