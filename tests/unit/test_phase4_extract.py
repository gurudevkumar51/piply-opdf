"""Unit tests for Phase 4 — Layout Extraction Engine."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from piply_opdf.models.layout import BoundingBox, LayoutManifest, LayoutRegion, RegionType
from piply_opdf.phases.phase4_extract import LayoutExtractor


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def extractor() -> LayoutExtractor:
    return LayoutExtractor()


def make_bgr_image(h: int = 200, w: int = 300) -> np.ndarray:
    # Use tile-based pattern instead of numpy.random (avoids DLL policy blocks)
    tile = np.arange(h * w * 3, dtype=np.uint8).reshape(h, w, 3) % 150 + 50
    return tile


def make_region(
    region_id: str = "paragraph_001",
    rtype: RegionType = RegionType.PARAGRAPH,
    x: int = 10, y: int = 10, w: int = 100, h: int = 50,
    page_number: int = 1,
) -> LayoutRegion:
    return LayoutRegion(
        region_id=region_id,
        type=rtype,
        page_number=page_number,
        bbox=BoundingBox(x=x, y=y, width=w, height=h),
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestLayoutExtractorInit:
    def test_default_padding(self, extractor: LayoutExtractor) -> None:
        assert extractor.region_padding == 4

    def test_default_output_dir_name(self, extractor: LayoutExtractor) -> None:
        assert extractor.output_dir_name == "layouts"


class TestExtractRegion:
    def test_sets_image_path(self, extractor: LayoutExtractor, tmp_path: Path) -> None:
        image = make_bgr_image()
        region = make_region()
        page_images = {1: image}
        updated = extractor._extract_region(region, page_images, tmp_path)
        assert updated.image_path is not None
        assert Path(updated.image_path).exists()

    def test_missing_page_image_returns_original(
        self, extractor: LayoutExtractor, tmp_path: Path
    ) -> None:
        region = make_region(page_number=99)
        page_images = {1: make_bgr_image()}
        updated = extractor._extract_region(region, page_images, tmp_path)
        # Should return region unchanged (no image_path set)
        assert updated.image_path is None

    def test_cropped_file_is_png(self, extractor: LayoutExtractor, tmp_path: Path) -> None:
        image = make_bgr_image()
        region = make_region()
        page_images = {1: image}
        updated = extractor._extract_region(region, page_images, tmp_path)
        assert updated.image_path is not None
        assert updated.image_path.endswith(".png")

    def test_children_are_extracted(self, extractor: LayoutExtractor, tmp_path: Path) -> None:
        image = make_bgr_image(h=300, w=400)
        child = make_region(region_id="cell_001", rtype=RegionType.CELL, x=20, y=20, w=50, h=30)
        parent = make_region(
            region_id="table_001",
            rtype=RegionType.TABLE,
            x=10, y=10, w=200, h=150,
        )
        parent = parent.model_copy(update={"children": [child]})
        page_images = {1: image}
        updated = extractor._extract_region(parent, page_images, tmp_path)
        assert len(updated.children) == 1
        assert updated.children[0].image_path is not None


class TestExtractFromImage:
    def test_returns_updated_regions(self, extractor: LayoutExtractor, tmp_path: Path) -> None:
        image = make_bgr_image()
        regions = [
            make_region("paragraph_001", x=5, y=5, w=80, h=40),
            make_region("paragraph_002", x=5, y=60, w=80, h=40),
        ]
        updated = extractor.extract_from_image(image, regions, tmp_path)
        assert len(updated) == 2
        for r in updated:
            assert r.image_path is not None

    def test_output_dir_created(self, extractor: LayoutExtractor, tmp_path: Path) -> None:
        new_dir = tmp_path / "extracted_layouts"
        image = make_bgr_image()
        extractor.extract_from_image(image, [make_region()], new_dir)
        assert new_dir.exists()


class TestLayoutManifestModel:
    def test_json_roundtrip(self) -> None:
        region = make_region()
        manifest = LayoutManifest(
            source_path="/fake/doc.pdf",
            output_dir="/fake/layouts",
            regions=[region],
        )
        json_str = manifest.model_dump_json()
        restored = LayoutManifest.model_validate_json(json_str)
        assert restored.source_path == manifest.source_path
        assert len(restored.regions) == 1
        assert restored.regions[0].region_id == "paragraph_001"
