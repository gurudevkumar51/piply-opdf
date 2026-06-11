"""Unit tests for Phase 3 — Layout Detection Engine."""

from __future__ import annotations

import numpy as np
import pytest

from piply_opdf.models.layout import RegionType
from piply_opdf.phases.phase3_layout import LayoutDetector, _reset_counters


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_white_page(h: int = 800, w: int = 600) -> np.ndarray:
    """Create a blank white page image (BGR)."""
    return np.full((h, w, 3), 255, dtype=np.uint8)


def draw_text_lines(img: np.ndarray, y_starts: list[int], color: int = 30) -> np.ndarray:
    """Draw horizontal dark bands simulating text lines."""
    result = img.copy()
    for y in y_starts:
        result[y : y + 8, 30:-30] = color
    return result


def draw_grid(
    img: np.ndarray,
    x: int, y: int, w: int, h: int,
    rows: int, cols: int,
) -> np.ndarray:
    """Draw a grid of lines simulating a table."""
    result = img.copy()
    col_w = w // cols
    row_h = h // rows
    # Horizontal lines
    for r in range(rows + 1):
        yy = y + r * row_h
        result[yy : yy + 2, x : x + w] = 0
    # Vertical lines
    for c in range(cols + 1):
        xx = x + c * col_w
        result[y : y + h, xx : xx + 2] = 0
    return result


@pytest.fixture(autouse=True)
def reset_counters() -> None:
    """Reset the global region ID counter before each test."""
    _reset_counters()


@pytest.fixture
def detector() -> LayoutDetector:
    return LayoutDetector()


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestLayoutDetectorInit:
    def test_default_ratios(self, detector: LayoutDetector) -> None:
        assert detector.header_ratio == 0.12
        assert detector.footer_ratio == 0.10

    def test_min_region_area(self, detector: LayoutDetector) -> None:
        assert detector.min_region_area == 2000


class TestHasContent:
    def test_white_image_has_no_content(self, detector: LayoutDetector) -> None:
        img = np.full((100, 100), 255, dtype=np.uint8)
        assert detector._has_content(img) is False

    def test_black_image_has_content(self, detector: LayoutDetector) -> None:
        img = np.zeros((100, 100), dtype=np.uint8)
        assert detector._has_content(img) is True


class TestClassifyBlock:
    def test_sparse_square_is_image(self, detector: LayoutDetector) -> None:
        # A near-square ROI with very few dark pixels → IMAGE
        roi = np.full((100, 120), 240, dtype=np.uint8)  # nearly white
        result = LayoutDetector._classify_block(roi, 120, 100)
        assert result == RegionType.IMAGE

    def test_text_dense_block_is_paragraph(self, detector: LayoutDetector) -> None:
        # A block with significant dark content → PARAGRAPH
        roi = np.full((100, 300), 200, dtype=np.uint8)
        roi[10:20, 10:250] = 20   # dark text-like stripes
        roi[40:50, 10:200] = 20
        roi[70:80, 10:150] = 20
        result = LayoutDetector._classify_block(roi, 300, 100)
        assert result == RegionType.PARAGRAPH


class TestDetectPage:
    def test_blank_page_has_no_regions(self, detector: LayoutDetector) -> None:
        img = make_white_page()
        regions = detector._detect_page(img, page_number=1)
        # A completely blank page should produce no regions
        assert len(regions) == 0

    def test_page_with_text_finds_some_regions(self, detector: LayoutDetector) -> None:
        img = make_white_page(h=800, w=600)
        img = draw_text_lines(img, y_starts=[100, 120, 140, 160, 180])
        regions = detector._detect_page(img, page_number=1)
        assert len(regions) >= 1

    def test_all_regions_have_correct_page_number(self, detector: LayoutDetector) -> None:
        img = make_white_page()
        img = draw_text_lines(img, y_starts=[100, 130, 160])
        regions = detector._detect_page(img, page_number=5)
        for r in regions:
            assert r.page_number == 5

    def test_region_ids_are_unique(self, detector: LayoutDetector) -> None:
        img = make_white_page()
        img = draw_text_lines(img, y_starts=[100, 130, 160, 190, 220])
        regions = detector._detect_page(img, page_number=1)
        ids = [r.region_id for r in regions]
        assert len(ids) == len(set(ids))

    def test_bbox_within_image_bounds(self, detector: LayoutDetector) -> None:
        img = make_white_page(h=800, w=600)
        img = draw_text_lines(img, y_starts=[100, 130])
        regions = detector._detect_page(img, page_number=1)
        for r in regions:
            assert r.bbox.x >= 0
            assert r.bbox.y >= 0
            assert r.bbox.x + r.bbox.width <= 600
            assert r.bbox.y + r.bbox.height <= 800


class TestBoundingBox:
    def test_area(self) -> None:
        from piply_opdf.models.layout import BoundingBox
        bb = BoundingBox(x=0, y=0, width=100, height=50)
        assert bb.area == 5000

    def test_aspect_ratio(self) -> None:
        from piply_opdf.models.layout import BoundingBox
        bb = BoundingBox(x=0, y=0, width=200, height=100)
        assert bb.aspect_ratio == 2.0

    def test_x2_y2(self) -> None:
        from piply_opdf.models.layout import BoundingBox
        bb = BoundingBox(x=10, y=20, width=100, height=50)
        assert bb.x2 == 110
        assert bb.y2 == 70


class TestLayoutResult:
    def test_regions_for_page(self) -> None:
        from piply_opdf.models.layout import BoundingBox, LayoutRegion, LayoutResult
        r1 = LayoutRegion(
            region_id="paragraph_001",
            type=RegionType.PARAGRAPH,
            page_number=1,
            bbox=BoundingBox(x=0, y=0, width=100, height=50),
        )
        r2 = LayoutRegion(
            region_id="paragraph_002",
            type=RegionType.PARAGRAPH,
            page_number=2,
            bbox=BoundingBox(x=0, y=0, width=100, height=50),
        )
        result = LayoutResult(source_path="/fake/doc.pdf", page_count=2, regions=[r1, r2])
        assert len(result.regions_for_page(1)) == 1
        assert len(result.regions_for_page(2)) == 1
        assert len(result.regions_for_page(3)) == 0

    def test_count_by_type(self) -> None:
        from piply_opdf.models.layout import BoundingBox, LayoutRegion, LayoutResult
        regions = [
            LayoutRegion(
                region_id=f"paragraph_00{i}",
                type=RegionType.PARAGRAPH,
                page_number=1,
                bbox=BoundingBox(x=0, y=i * 60, width=100, height=50),
            )
            for i in range(3)
        ]
        result = LayoutResult(source_path="/fake/doc.pdf", page_count=1, regions=regions)
        counts = result.count_by_type()
        assert counts["paragraph"] == 3
