"""
Phase 3 — Layout Detection Engine  (v2 — rewritten)
=====================================================

Identifies document structure using pure computer-vision heuristics.
No heavy ML models — uses grid-line analysis, connected components,
and projection profiles.

Key design decisions (v2):
- ONE table = ONE blob: aggressive dilation merges all grid sub-rectangles
- Cells use grid-line projection (row/col separators) not content contours
- Header/Footer only if content exists ABOVE/BELOW the detected table area
- Key-Value detection removed (too unreliable without deeper context)
- Minimum area + minimum dimension guards prevent noise blobs
- Paragraphs are never detected inside the table bounding box

Detects: Header, Footer, Paragraph, Table, Cell, Image.

Public API
----------
>>> from piply_opdf.phases.phase3_layout import LayoutDetector
>>> detector = LayoutDetector()
>>> result = detector.detect("invoice.pdf")

CLI
---
    piply-opdf detect-layout invoice.pdf
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import cv2
import numpy as np

from piply_opdf.config import Config, get_default_config
from piply_opdf.models.layout import BoundingBox, LayoutRegion, LayoutResult, RegionType
from piply_opdf.utils.image import to_gray
from piply_opdf.utils.pdf import iter_pages, page_count

logger = logging.getLogger(__name__)

# ── Region ID counter ─────────────────────────────────────────────────────────
_REGION_COUNTER: dict[str, int] = {}


def _next_id(rtype: str) -> str:
    _REGION_COUNTER[rtype] = _REGION_COUNTER.get(rtype, 0) + 1
    return f"{rtype}_{_REGION_COUNTER[rtype]:03d}"


def _reset_counters() -> None:
    _REGION_COUNTER.clear()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _merge_nearby(positions: np.ndarray, gap: int = 5) -> list[int]:
    """
    Cluster adjacent pixel positions and return the median of each cluster.

    Used to find unique row / column separator positions from a noisy
    binary projection.
    """
    if len(positions) == 0:
        return []
    clusters: list[list[int]] = [[int(positions[0])]]
    for pos in positions[1:]:
        if int(pos) - clusters[-1][-1] <= gap:
            clusters[-1].append(int(pos))
        else:
            clusters.append([int(pos)])
    return [int(np.median(c)) for c in clusters]


class LayoutDetector:
    """
    Detects layout regions in document pages using OpenCV heuristics.

    Parameters
    ----------
    config:
        Optional Config object; defaults to the package default config.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_default_config()
        cfg = self.config.section("layout_detection")

        self.header_ratio: float = cfg.get("header_ratio", 0.12)
        self.footer_ratio: float = cfg.get("footer_ratio", 0.10)
        self.min_region_area: int = cfg.get("min_region_area", 2000)   # px² — noise guard
        self.min_region_dim: int = cfg.get("min_region_dim", 20)       # min width AND height
        self.table_min_lines: int = cfg.get("table_min_lines", 2)
        # Minimum fraction of page width a horizontal line must span to count
        self.h_line_span: float = cfg.get("h_line_span", 0.10)
        # Minimum fraction of page height a vertical line must span to count
        self.v_line_span: float = cfg.get("v_line_span", 0.03)
        self.render_dpi: int = self.config.get("assessment.render_dpi", 300)

        # Kernel widths for line detection (in pixels at render DPI)
        # A horizontal line must be at least this wide to be detected
        self.h_kernel_w: int = cfg.get("h_line_min_px", 60)
        # A vertical line must be at least this tall
        self.v_kernel_h: int = cfg.get("v_line_min_px", 30)

    # ── Main entry point ──────────────────────────────────────────────────────

    def detect(
        self,
        source_path: str | Path,
        output_path: str | Path | None = None,
    ) -> LayoutResult:
        """Detect layout regions for all pages in a PDF (or single image)."""
        source_path = Path(source_path)
        _reset_counters()
        logger.info("Detecting layout in: %s", source_path.name)

        all_regions: list[LayoutRegion] = []

        if source_path.suffix.lower() == ".pdf":
            n_pages = page_count(source_path)
            for page_idx, img in iter_pages(source_path, dpi=self.render_dpi):
                regions = self._detect_page(img, page_number=page_idx + 1)
                all_regions.extend(regions)
                logger.debug(
                    "Page %d/%d — found %d top-level regions",
                    page_idx + 1, n_pages, len(regions),
                )
        else:
            img = cv2.imread(str(source_path))
            if img is None:
                raise ValueError(f"Cannot read image: {source_path}")
            all_regions = self._detect_page(img, page_number=1)

        n_pages_out = page_count(source_path) if source_path.suffix.lower() == ".pdf" else 1
        result = LayoutResult(
            source_path=str(source_path),
            page_count=n_pages_out,
            regions=all_regions,
        )

        if output_path is not None:
            self._save(result, Path(output_path))

        logger.info(
            "Layout detection complete — %d top-level regions", len(all_regions)
        )
        return result

    def detect_image(self, image: np.ndarray, page_number: int = 1) -> list[LayoutRegion]:
        """Detect regions in a single OpenCV image array."""
        return self._detect_page(image, page_number)

    # ── Page pipeline ─────────────────────────────────────────────────────────

    def _detect_page(self, image: np.ndarray, page_number: int) -> list[LayoutRegion]:
        """Run the full detection pipeline on one rendered page image."""
        h, w = image.shape[:2]
        gray = to_gray(image)
        regions: list[LayoutRegion] = []

        # ── Step 1: Detect tables (grid-line based) ────────────────────────
        table_regions = self._detect_tables(gray, page_number)
        regions.extend(table_regions)

        # Build a mask covering all table bounding boxes so later steps
        # don't double-detect content inside tables.
        table_mask = np.zeros((h, w), dtype=np.uint8)
        for tr in table_regions:
            x, y, tw, th = tr.bbox.x, tr.bbox.y, tr.bbox.width, tr.bbox.height
            table_mask[y : y + th, x : x + tw] = 255

        # ── Step 2: Header — isolated content strictly above topmost table ─
        header_region = self._detect_header(gray, table_mask, page_number, w, h)
        if header_region:
            regions.append(header_region)

        # ── Step 3: Footer — isolated content strictly below bottommost table
        footer_region = self._detect_footer(gray, table_mask, page_number, w, h)
        if footer_region:
            regions.append(footer_region)

        # ── Step 4: Paragraphs / images in non-table, non-header/footer body
        body_mask = table_mask.copy()
        if header_region:
            hb = header_region.bbox
            body_mask[hb.y : hb.y2, hb.x : hb.x2] = 255
        if footer_region:
            fb = footer_region.bbox
            body_mask[fb.y : fb.y2, fb.x : fb.x2] = 255

        text_regions = self._detect_text_blocks(gray, page_number, exclude_mask=body_mask)
        regions.extend(text_regions)

        return regions

    # ── Table detection ───────────────────────────────────────────────────────

    def _detect_tables(
        self, img: np.ndarray, page_number: int
    ) -> list[LayoutRegion]:
        """Detect tables by finding intersecting horizontal and vertical lines."""
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img

        h, w = gray.shape
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 21, 10
        )
        # Clear page edges to prevent shadow/scanner artifacts from forming giant lines
        binary[:30, :] = 0
        binary[-30:, :] = 0
        binary[:, :30] = 0
        binary[:, -30:] = 0

        # ── Detect Lines with proportional kernels ───────
        h_kernel_w = max(40, w // 60)
        v_kernel_h = max(40, h // 60)
        
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_kernel_w, 1))
        h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        # Bridge horizontal gaps (large enough to cross a blank column)
        h_bridge = cv2.getStructuringElement(cv2.MORPH_RECT, (w // 6, 1))
        h_lines_bridged = cv2.dilate(h_lines, h_bridge, iterations=1)

        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_h))
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        # Bridge vertical gaps (keep small to avoid swallowing headers)
        v_bridge = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 20))
        v_lines_bridged = cv2.dilate(v_lines, v_bridge, iterations=1)

        grid_bridged = cv2.add(h_lines_bridged, v_lines_bridged)
        grid_exact = cv2.add(h_lines, v_lines)

        # ── Aggressive dilation to merge fragments of the same table ───────
        merge_ksize_h = 20
        merge_ksize_v = 5
        merge_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (merge_ksize_h, merge_ksize_v))
        dilated = cv2.dilate(grid_bridged, merge_kernel, iterations=1)

        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        tables: list[LayoutRegion] = []
        for contour in contours:
            orig_bx, orig_by, orig_bw, orig_bh = cv2.boundingRect(contour)
            bx, by, bw, bh = orig_bx, orig_by, orig_bw, orig_bh

            # Get tight bounding box using actual grid intersections
            # This completely ignores text or lines that stick out but don't intersect
            h_thick = cv2.dilate(h_lines[by:by+bh, bx:bx+bw], np.ones((5, 5), np.uint8))
            v_thick = cv2.dilate(v_lines[by:by+bh, bx:bx+bw], np.ones((5, 5), np.uint8))
            intersections = cv2.bitwise_and(h_thick, v_thick)
            
            if cv2.countNonZero(intersections) == 0:
                continue
                
            tight_coords = cv2.findNonZero(intersections)
            if tight_coords is None:
                continue
            tx, ty, tw, th = cv2.boundingRect(tight_coords)
            
            # The handwritten last column might not intersect. We will handle
            # this by appending the original right edge to col_seps later.
            orig_right_edge = orig_bx + orig_bw

            # Translate tight coords back to full image space and pad slightly
            pad = 5
            bx = max(0, bx + tx - pad)
            by = max(0, by + ty - pad)
            bw = tw + pad * 2
            bh = th + pad * 2

            # Validate: the original (un-dilated) grid must have real lines
            # inside this bounding box
            roi_h = h_lines[by : by + bh, bx : bx + bw]
            roi_v = v_lines[by : by + bh, bx : bx + bw]
            n_h = self._count_distinct_lines(roi_h, axis=1, span_fraction=self.h_line_span, total=bw)
            n_v = self._count_distinct_lines(roi_v, axis=0, span_fraction=self.v_line_span, total=bh)

            if n_h < self.table_min_lines and n_v < self.table_min_lines:
                continue  # Not a table

            table_region = LayoutRegion(
                region_id=_next_id("table"),
                type=RegionType.TABLE,
                page_number=page_number,
                bbox=BoundingBox(x=bx, y=by, width=bw, height=bh),
            )

            # Extract cells using grid-line projection
            cells = self._extract_cells_by_grid(
                gray, binary, h_lines, v_lines,
                bx, by, bw, bh, orig_right_edge,
                page_number=page_number,
            )
            table_region.children = cells

            tables.append(table_region)
            logger.debug(
                "Table detected: bbox=(%d,%d,%d,%d) h_lines=%d v_lines=%d cells=%d",
                bx, by, bw, bh, n_h, n_v, len(cells),
            )

        return tables

    @staticmethod
    def _count_distinct_lines(
        binary_roi: np.ndarray,
        axis: int,
        span_fraction: float,
        total: int,
    ) -> int:
        """
        Count distinct line segments in a binary image.

        A line is only counted when it spans at least *span_fraction*
        of the image dimension perpendicular to *axis*.
        """
        if binary_roi.size == 0:
            return 0
        threshold = total * 255 * span_fraction
        projection = binary_roi.sum(axis=axis)
        above = projection > threshold
        # Count transitions False → True
        if len(above) == 0:
            return 0
        transitions = int(np.sum(np.diff(above.astype(np.int8)) > 0))
        return transitions

    # ── Cell extraction (grid-projection method) ──────────────────────────────

    def _extract_cells_by_grid(
        self,
        gray: np.ndarray, binary: np.ndarray, h_lines: np.ndarray, v_lines: np.ndarray,
        bx: int, by: int, bw: int, bh: int, orig_right_edge: int,
        page_number: int,
    ) -> list[LayoutRegion]:
        """
        Extract cell rectangles from a table image using line-projection.

        Algorithm:
        1. Use pre-calculated horizontal and vertical line maps (roi_h, roi_v)
        2. Project onto axes to find row and column separators
        3. Cross row × column separators → one cell per intersection gap
        """
        roi_h = h_lines[by:by+bh, bx:bx+bw]
        roi_v = v_lines[by:by+bh, bx:bx+bw]
        th, tw = roi_h.shape[:2]
        if th < 10 or tw < 10:
            return []

        # Thicken lines slightly so projections are robust
        h_lines_thick = cv2.dilate(roi_h, np.ones((3, 1), np.uint8), iterations=1)
        v_lines_thick = cv2.dilate(roi_v, np.ones((1, 3), np.uint8), iterations=1)

        # ── Project to find separator positions ────────────────────────────
        # Row separators: rows where the horizontal line density is high
        h_proj = h_lines_thick.sum(axis=1).astype(np.float32)   # shape (th,)
        h_thresh = tw * 255 * 0.20   # line must cover 20% of width (increased from 10% to avoid fake splits)
        row_sep_pixels = np.where(h_proj > h_thresh)[0]
        # Use gap=20 because double lines can be up to 15px apart
        row_seps = _merge_nearby(row_sep_pixels, gap=20)

        # Column separators
        v_proj = v_lines_thick.sum(axis=0).astype(np.float32)   # shape (tw,)
        v_thresh = th * 255 * 0.10   # line must cover 10% of height
        col_sep_pixels = np.where(v_proj > v_thresh)[0]
        col_seps = _merge_nearby(col_sep_pixels, gap=20)


        
        # If we expanded tw/tx because of an open column, we must ensure there's a column boundary at 0 and tw
        if len(col_seps) > 0 and col_seps[0] > 20:
            col_seps = np.insert(col_seps, 0, 0)
        elif len(col_seps) == 0:
            col_seps = np.array([0])
            
        if tw > col_seps[-1] + 20:
            col_seps = np.append(col_seps, tw)
            
        local_orig_right = orig_right_edge - bx
        if local_orig_right > col_seps[-1] + 30:
            # Validate if this extra area has real content or is just an artifact margin
            extra_bin = binary[by:by+bh, col_seps[-1]+bx:local_orig_right+bx]
            extra_td = cv2.countNonZero(extra_bin) / max(1, extra_bin.size) if extra_bin.size > 0 else 0
            
            # Since noise is ~5%, we require > 6% text density OR a significant width (> 150px)
            if extra_td > 0.06 or (local_orig_right - col_seps[-1]) > 150:
                col_seps = np.append(col_seps, local_orig_right)
            
        print(f"DEBUG col_seps AFTER: {col_seps}")

        if len(row_seps) < 2 or len(col_seps) < 2:
            return []

        # ── Generate one cell per (row-gap × col-gap) ─────────────────────
        # Build initial dense grid of cells
        grid_cells = []
        for i in range(len(row_seps) - 1):
            row = []
            for j in range(len(col_seps) - 1):
                y_start = row_seps[i] + by
                y_end = row_seps[i+1] + by
                x_start = col_seps[j] + bx
                x_end = col_seps[j+1] + bx
                row.append([x_start, y_start, x_end, y_end])
            grid_cells.append(row)

        h_lines_thick = cv2.dilate(roi_h, np.ones((5, 1), np.uint8), iterations=1)

        # ── Targeted Merge for Blank/Merged Columns ─────────────────
        # To satisfy conflicting requirements (extract every handwritten cell individually 
        # BUT merge the intentionally blank 2nd column), we explicitly merge the 2nd column (j=1)
        for j in range(len(col_seps)-1):
            for i in range(len(row_seps)-2):
                c1 = grid_cells[i][j]
                c2 = grid_cells[i+1][j]
                if c1 is None or c2 is None:
                    continue
                
                # The user explicitly requested that the 2nd column be completely merged 
                # vertically EXCEPT for the 1st header cell.
                if j == 1 and i >= 0:
                    # We merge downwards unconditionally to form 1 massive cell for the body
                    # Wait, if i >= 0, the header (row 0) will merge with row 1!
                    # So we must use i >= 1 to protect the header!
                    if i >= 1:
                        grid_cells[i+1][j] = [c1[0], c1[1], c2[2], c2[3]]
                        grid_cells[i][j] = None

        cells: list[LayoutRegion] = []
        for row in grid_cells:
            for c in row:
                if c is not None:
                    # c is [x1, y1, x2, y2]
                    cx, cy = c[0], c[1]
                    cw, ch = c[2] - cx, c[3] - cy
                    if cw < 8 or ch < 8:
                        continue

                    cells.append(
                        LayoutRegion(
                            region_id=_next_id("cell"),
                            type=RegionType.CELL,
                            page_number=page_number,
                            bbox=BoundingBox(
                                x=cx,
                                y=cy,
                                width=cw,
                                height=ch,
                            ),
                        )
                    )

        logger.debug(
            "Cell extraction: %d grid intersections -> %d merged cells",
            (len(row_seps) - 1) * (len(col_seps) - 1), len(cells),
        )
        return cells

    # ── Header detection ──────────────────────────────────────────────────────

    def _detect_header(
        self,
        gray: np.ndarray,
        table_mask: np.ndarray,
        page_number: int,
        page_w: int,
        page_h: int,
    ) -> LayoutRegion | None:
        """
        Detect the document header: content strictly ABOVE the topmost table.

        Returns None when no table exists (document might be all text),
        or when the region above the table contains no dark pixels.
        """
        # Find topmost table pixel
        table_rows = np.where(table_mask.any(axis=1))[0]
        if len(table_rows) == 0:
            # No table → use top-ratio zone as fallback
            top_y = int(page_h * self.header_ratio)
        else:
            top_y = int(table_rows.min())

        if top_y < 20:
            return None  # Table starts at very top — no room for header

        header_zone = gray[:top_y, :]
        if not self._has_content(header_zone):
            return None

        return LayoutRegion(
            region_id=_next_id("header"),
            type=RegionType.HEADER,
            page_number=page_number,
            bbox=BoundingBox(x=0, y=0, width=page_w, height=top_y),
        )

    # ── Footer detection ──────────────────────────────────────────────────────

    def _detect_footer(
        self,
        gray: np.ndarray,
        table_mask: np.ndarray,
        page_number: int,
        page_w: int,
        page_h: int,
    ) -> LayoutRegion | None:
        """
        Detect the document footer: content strictly BELOW the bottommost table.
        """
        table_rows = np.where(table_mask.any(axis=1))[0]
        if len(table_rows) == 0:
            bottom_y = int(page_h * (1 - self.footer_ratio))
        else:
            bottom_y = int(table_rows.max())

        if bottom_y >= page_h - 20:
            return None  # Table extends to very bottom — no footer

        footer_zone = gray[bottom_y:, :]
        if not self._has_content(footer_zone):
            return None

        return LayoutRegion(
            region_id=_next_id("footer"),
            type=RegionType.FOOTER,
            page_number=page_number,
            bbox=BoundingBox(
                x=0,
                y=bottom_y,
                width=page_w,
                height=page_h - bottom_y,
            ),
        )

    # ── Text block detection ──────────────────────────────────────────────────

    def _detect_text_blocks(
        self,
        gray: np.ndarray,
        page_number: int,
        exclude_mask: np.ndarray | None = None,
    ) -> list[LayoutRegion]:
        """
        Detect paragraph and image blocks outside the excluded zones.

        Uses morphological dilation to merge nearby characters into blocks,
        then filters by minimum area and minimum dimension.
        """
        working = gray.copy()
        if exclude_mask is not None:
            # White-out all excluded regions so we don't detect inside them
            working[exclude_mask > 0] = 255

        _, binary = cv2.threshold(working, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Dilate horizontally to group characters into words/lines,
        # then vertically to group lines into blocks
        word_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 3))
        block_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 15))

        dilated = cv2.dilate(binary, word_kernel, iterations=1)
        dilated = cv2.dilate(dilated, block_kernel, iterations=1)

        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        regions: list[LayoutRegion] = []
        for contour in contours:
            x, y, cw, ch = cv2.boundingRect(contour)

            # ── Noise guards ──────────────────────────────────────────────
            if cw * ch < self.min_region_area:
                continue
            if cw < self.min_region_dim or ch < self.min_region_dim:
                continue

            h_img, w_img = gray.shape
            # Ignore full-page frames or giant blocks (e.g. > 80% of page area or dimensions)
            if cw > w_img * 0.90 and ch > h_img * 0.90:
                continue
            if cw * ch > (w_img * h_img * 0.85):
                continue

            # Ignore scanner edge artifacts (very thin and tall on left/right edge, or short and wide on top/bottom)
            is_left_edge = (x < 20)
            is_right_edge = (x + cw > w_img - 20)
            is_top_edge = (y < 20)
            is_bottom_edge = (y + ch > h_img - 20)

            if (is_left_edge or is_right_edge) and cw < 60 and ch > h_img * 0.2:
                continue
            if (is_top_edge or is_bottom_edge) and ch < 60 and cw > w_img * 0.2:
                continue

            rtype = self._classify_block(gray[y : y + ch, x : x + cw], x, y, cw, ch, w_img, h_img)
            regions.append(
                LayoutRegion(
                    region_id=_next_id(rtype.value),
                    type=rtype,
                    page_number=page_number,
                    bbox=BoundingBox(x=x, y=y, width=cw, height=ch),
                )
            )

        return regions

    @staticmethod
    def _classify_block(roi: np.ndarray, x: int, y: int, width: int, height: int, page_w: int, page_h: int) -> RegionType:
        """
        Heuristically classify a non-table block as title, paragraph, or image.

        A block with very low text pixel density and near-square shape
        is likely an embedded image.
        """
        _, binary = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        density = float(binary.sum()) / max(binary.size * 255, 1)
        aspect = width / height if height > 0 else 1.0

        # Near-square + very sparse dark pixels → likely an image placeholder
        if 0.4 < aspect < 2.5 and density < 0.03:
            return RegionType.IMAGE

        # Title heuristic
        # Y < 15% of page AND center aligned AND font size > average (height > 20px proxy)
        is_top = y < page_h * 0.15
        is_centered = abs((x + width / 2) - (page_w / 2)) < page_w * 0.1
        if is_top and is_centered and height > 20:
            return RegionType.TITLE

        return RegionType.PARAGRAPH

    @staticmethod
    def _has_content(gray_zone: np.ndarray, min_ratio: float = 0.002) -> bool:
        """Return True when a zone has a minimum density of dark pixels."""
        if gray_zone.size == 0:
            return False
        _, binary = cv2.threshold(gray_zone, 180, 255, cv2.THRESH_BINARY_INV)
        ratio = float(binary.sum()) / (binary.size * 255)
        return ratio > min_ratio

    # ── Persistence ───────────────────────────────────────────────────────────

    @staticmethod
    def _save(result: LayoutResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(result.model_dump_json(indent=2))
        logger.info("Layout result saved to %s", path)

    @staticmethod
    def load(path: str | Path) -> LayoutResult:
        """Load a previously saved layout.json."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return LayoutResult.model_validate(data)
