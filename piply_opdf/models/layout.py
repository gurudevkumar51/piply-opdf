"""Pydantic models for Phase 3/4 — Layout Detection & Extraction."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RegionType(str, Enum):
    HEADER = "header"
    FOOTER = "footer"
    TITLE = "title"
    PARAGRAPH = "paragraph"
    SENTENCE = "sentence"
    TABLE = "table"
    ROW = "row"
    COLUMN = "column"
    CELL = "cell"
    KEY_VALUE = "key_value"
    SIGNATURE = "signature"
    IMAGE = "image"
    UNKNOWN = "unknown"

class ContentType(str, Enum):
    PRINTED_TEXT = "printed_text"
    TEXT_REGION = "text_region"
    MIXED_CONTENT = "mixed_content"
    SIGNATURE = "signature"
    STAMP = "stamp"
    IMAGE = "image"
    EMPTY_REGION = "empty_region"
    UNKNOWN = "unknown"


class BoundingBox(BaseModel):
    """Pixel-space bounding box (top-left origin)."""

    x: int = Field(..., description="Left edge (pixels)")
    y: int = Field(..., description="Top edge (pixels)")
    width: int = Field(..., description="Region width (pixels)")
    height: int = Field(..., description="Region height (pixels)")

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    @property
    def area(self) -> int:
        return self.width * self.height

    @property
    def aspect_ratio(self) -> float:
        return self.width / self.height if self.height > 0 else 0.0

    def to_tuple(self) -> tuple[int, int, int, int]:
        """Return (x, y, x2, y2)."""
        return (self.x, self.y, self.x2, self.y2)

    def to_xywh(self) -> tuple[int, int, int, int]:
        """Return (x, y, width, height)."""
        return (self.x, self.y, self.width, self.height)


class LayoutRegion(BaseModel):
    """A single detected layout region."""

    region_id: str = Field(..., description="Unique region identifier, e.g. 'paragraph_001'")
    type: RegionType = Field(..., description="Semantic type of the region")
    page_number: int = Field(..., description="1-based page index this region belongs to")
    bbox: BoundingBox = Field(..., description="Bounding box in page pixel coordinates")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Detection confidence (0–1)"
    )

    # Optional: child regions (e.g. rows inside a table)
    children: list["LayoutRegion"] = Field(
        default_factory=list,
        description="Child regions (e.g. rows of a table, cells of a row)",
    )

    # Set after Phase 4 extraction
    image_path: str | None = Field(
        default=None, description="Relative path to the cropped region image"
    )

    content_type: ContentType = Field(
        default=ContentType.UNKNOWN, description="Content classification of the region"
    )
    cluster_id: str | None = Field(
        default=None, description="ID of the similarity cluster this region belongs to"
    )
    ml_features: dict[str, float] | None = Field(
        default=None, description="Mathematical features extracted for V2 ML training"
    )

class LayoutResult(BaseModel):
    """Full layout detection result for a document."""

    source_path: str
    page_count: int
    regions: list[LayoutRegion] = Field(default_factory=list)

    def regions_for_page(self, page_number: int) -> list[LayoutRegion]:
        return [r for r in self.regions if r.page_number == page_number]

    def regions_of_type(self, rtype: RegionType) -> list[LayoutRegion]:
        return [r for r in self.regions if r.type == rtype]

    def count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.regions:
            counts[r.type.value] = counts.get(r.type.value, 0) + 1
        return counts


class ClusterGroup(BaseModel):
    """A group of visually similar layout regions."""
    
    cluster_id: str = Field(..., description="Unique cluster identifier")
    representative: str = Field(..., description="Path to the representative image for OCR")
    members: list[str] = Field(..., description="List of all image paths in this cluster")
    layout_type: str = Field(..., description="The RegionType of the members")
    content_type: str = Field(..., description="The ContentType of the members")
    total_members: int = Field(..., description="Number of members in the cluster")


class ClusterManifest(BaseModel):
    """Manifest of all clusters generated for a document."""
    
    source_path: str
    output_dir: str
    clusters: list[ClusterGroup] = Field(default_factory=list)


class LayoutManifest(BaseModel):
    """Manifest produced by Phase 4 — one entry per extracted image file."""

    source_path: str
    output_dir: str
    regions: list[LayoutRegion] = Field(default_factory=list)
