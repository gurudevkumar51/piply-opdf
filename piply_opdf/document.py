"""
High-level Document API
========================

Provides a single ``Document`` class that orchestrates all processing phases.
Each method can be called independently or chained together.

Example (full pipeline)
-----------------------
>>> from piply_opdf import Document
>>> doc = Document("invoice.pdf")
>>> doc.assess()
>>> doc.enhance()
>>> doc.detect_layout()
>>> doc.extract_layouts()
>>> doc.ocr()

Example (assessment only)
--------------------------
>>> doc = Document("scan.pdf", config="my_config.yaml")
>>> result = doc.assess(output_path="results/assessment.json")
>>> print(result.summary())
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from piply_opdf.config import Config, load_config
from piply_opdf.models.assessment import AssessmentResult
from piply_opdf.models.grid import TableModel
from piply_opdf.phases.phase1_assess import DocumentAssessor
from piply_opdf.phases.phase2_enhance import DocumentEnhancer
from piply_opdf.utils.pdf import iter_pages

from piply_opdf.layout import (
    ColumnDetector,
    RowDetector,
    GridBuilder,
    GridValidator,
    CellExtractor,
    MetadataManager,
    DebugVisualizer
)
from piply_opdf.detectors.table import TableDetector
from piply_opdf.detectors.borderless_table import BorderlessTableDetector
from piply_opdf.detectors.header import HeaderDetector
from piply_opdf.detectors.footer import FooterDetector
from piply_opdf.detectors.key_value import KeyValueDetector
from piply_opdf.detectors.paragraph import ParagraphDetector

logger = logging.getLogger(__name__)


class Document:
    """
    High-level entry point for the piply-opdf pipeline.

    Parameters
    ----------
    source_path:
        Path to the PDF or image file to process.
    config:
        Optional path to a custom YAML configuration file, or a Config object.
        When *None*, the bundled default configuration is used.
    work_dir:
        Directory where all output artefacts (JSON, images, PDFs) are written.
        Defaults to ``<source_stem>_piply/`` alongside the source file.
    """

    def __init__(
        self,
        source_path: str | Path,
        config: str | Path | Config | None = None,
        work_dir: str | Path | None = None,
    ) -> None:
        self.source_path = Path(source_path).resolve()
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_path}")

        # Resolve config
        if isinstance(config, Config):
            self.config = config
        else:
            self.config = load_config(config)

        # Work directory
        if work_dir is None:
            work_dir = self.source_path.parent / f"{self.source_path.stem}_piply"
        self.work_dir = Path(work_dir)
        self.work_dir.mkdir(parents=True, exist_ok=True)

        # Internal state — populated as phases are run
        self._assessment: AssessmentResult | None = None
        self._enhanced_path: Path | None = None
        self.tables: list[TableModel] = []

        logger.info(
            "Document initialised: %s | work_dir: %s",
            self.source_path.name,
            self.work_dir,
        )

    # ── Phase 1: Assessment ───────────────────────────────────────────────────

    def assess(
        self,
        output_path: str | Path | None = None,
        force: bool = False,
    ) -> AssessmentResult:
        """
        Phase 1 — Assess document quality.

        Parameters
        ----------
        output_path:
            Override for the output JSON path.
        force:
            Re-run even if assessment was already performed this session.

        Returns
        -------
        AssessmentResult
        """
        if self._assessment is not None and not force:
            logger.debug("Assessment already done; returning cached result")
            return self._assessment

        out = Path(output_path) if output_path else self.work_dir / "assessment.json"
        assessor = DocumentAssessor(config=self.config)
        self._assessment = assessor.assess(self.source_path, output_path=out)
        return self._assessment

    # ── Phase 2: Enhancement ──────────────────────────────────────────────────

    def enhance(
        self,
        output_path: str | Path | None = None,
        use_assessment: bool = True,
    ) -> Path:
        """
        Phase 2 — Enhance document selectively based on assessment.

        Runs Phase 1 automatically if not yet done and *use_assessment* is True.

        Parameters
        ----------
        output_path:
            Override for the output enhanced PDF path.
        use_assessment:
            When True (default), passes assessment results to the enhancer so
            only flagged operations are applied.

        Returns
        -------
        Path
            Path to the enhanced PDF.
        """
        assessment = None
        if use_assessment:
            if self._assessment is None:
                self.assess()
            assessment = self._assessment

        out = Path(output_path) if output_path else self.work_dir / f"{self.source_path.stem}_enhanced.pdf"
        enhancer = DocumentEnhancer(config=self.config)
        self._enhanced_path = enhancer.enhance(
            self.source_path,
            assessment=assessment,
            output_path=out,
        )
        return self._enhanced_path

    # ── Phase 3: Grid Extraction Pipeline ─────────────────────────────────────

    def process_layout(self, use_enhanced: bool = True) -> list[TableModel]:
        """
        Runs the new modular table and grid extraction engine.
        Follows Priority Order: P1 (Tables), P2 (Borderless), P3 (Headers), P4 (Footers).
        """
        source = self._resolve_source(use_enhanced)
        self.tables = []
        
        # P1
        table_detector = TableDetector()
        col_detector = ColumnDetector()
        row_detector = RowDetector()
        grid_builder = GridBuilder()
        validator = GridValidator()
        cell_extractor = CellExtractor()
        metadata_manager = MetadataManager()
        visualizer = DebugVisualizer()
        
        # P2, P3, P4
        borderless_detector = BorderlessTableDetector()
        header_detector = HeaderDetector()
        footer_detector = FooterDetector()
        key_value_detector = KeyValueDetector()
        paragraph_detector = ParagraphDetector()
        
        out_dir = self.work_dir / "layouts"
        debug_dir = self.work_dir / "debug"
        
        table_idx = 1
        previous_table_cols = None
        previous_table_id = None
        
        # Also store other components for metadata saving later
        self.borderless_tables = []
        self.headers = []
        self.footers = []
        self.key_values = []
        self.paragraphs = []
        self.sentences = []
        
        for page_idx, img in iter_pages(source, dpi=300):
            page_num = page_idx + 1
            
            # --- STAGE 1: Structured Table Detection (P1) ---
            table_boxes = table_detector.detect_tables(img)
            
            for i, t_box in enumerate(table_boxes):
                # 2. Detect Columns using a temporary ID
                cols = col_detector.detect_columns(img, t_box, "temp_id")
                
                # Multi-Page Continuation Check: Only the first table on the page can be a continuation
                is_continuation = False
                if i == 0 and previous_table_cols is not None:
                    # If column counts are similar (allow variance of up to 2 due to noise), it's a continuation
                    if abs(len(cols) - len(previous_table_cols)) <= 2 and len(cols) > 0:
                        is_continuation = True
                        
                if is_continuation:
                    t_id = previous_table_id
                else:
                    t_id = f"table_{table_idx:03d}"
                    table_idx += 1
                    
                # Fix column IDs with the true table_id
                for c in cols:
                    c.parent_table = t_id
                    c.column_id = c.column_id.replace("temp_id", t_id)
                
                # 3. Detect Rows
                row_cands = row_detector.detect_row_candidates(img, cols)
                
                # 4. Build Grid
                table_model = grid_builder.build_grid(img, t_id, t_box, page_num, cols, row_cands)
                
                # 5. Validate Grid
                table_model = validator.validate(img, table_model)
                
                # 6. Extract Cells
                cell_extractor.extract(img, table_model, out_dir)
                
                # 7. Metadata
                metadata_manager.save_metadata(table_model, out_dir)
                
                # 8. Debug
                page_debug_dir = debug_dir / f"page_{page_num}"
                visualizer.visualize(img, table_model, page_debug_dir)
                
                self.tables.append(table_model)
                
                # Store the last table's columns and ID for the next page's continuation check
                if i == len(table_boxes) - 1:
                    previous_table_cols = cols
                    previous_table_id = t_id
                    
            # If no tables were found on this page, break the continuation chain
            if not table_boxes:
                previous_table_cols = None
                previous_table_id = None
                
            # --- STAGE 3: Header Detection (P3) ---
            headers = header_detector.detect_headers(str(self.source_path), page_num)
            self._save_component_crops(img, headers, out_dir, page_num, "headers")
            self.headers.extend(headers)
            
            # --- STAGE 4: Footer Detection (P4) ---
            footers = footer_detector.detect_footers(str(self.source_path), page_num)
            self._save_component_crops(img, footers, out_dir, page_num, "footers")
            self.footers.extend(footers)

            # Create tight bounding boxes from actual table cells to avoid excluding surrounding text
            table_bboxes = []
            for t in self.tables:
                if t.page == page_num:
                    if t.cells:
                        min_x = min(c.bbox.x for c in t.cells)
                        min_y = min(c.bbox.y for c in t.cells)
                        max_x = max(c.bbox.x + c.bbox.width for c in t.cells)
                        max_y = max(c.bbox.y + c.bbox.height for c in t.cells)
                        padding = 5
                        table_bboxes.append((
                            max(0, min_x - padding),
                            max(0, min_y - padding),
                            max_x - min_x + 2 * padding,
                            max_y - min_y + 2 * padding
                        ))
                    else:
                        table_bboxes.append(t.bbox.to_tuple())

            # --- STAGE 5: Key-Value Detection (P5) ---
            key_values = key_value_detector.detect_key_values(
                str(self.source_path),
                page_num,
                table_bboxes,
            )
            self._save_component_crops(img, key_values, out_dir, page_num, "key_values")
            self.key_values.extend(key_values)

            # --- STAGE 6: Paragraph Detection (P6) ---
            paragraph_exclusions = table_bboxes + [
                tuple(kv["bbox"]) for kv in key_values if kv.get("bbox")
            ] + [
                tuple(h["bbox"]) for h in headers if h.get("bbox")
            ] + [
                tuple(f["bbox"]) for f in footers if f.get("bbox")
            ]
            p_results = paragraph_detector.detect_paragraphs(
                str(self.source_path),
                page_num,
                paragraph_exclusions,
            )
            paragraphs = p_results["paragraphs"]
            sentences = p_results["sentences"]
            
            self._save_component_crops(img, paragraphs, out_dir, page_num, "paragraphs")
            for paragraph in paragraphs:
                self._save_component_crops(
                    img,
                    paragraph.get("words", []),
                    out_dir,
                    page_num,
                    "words",
                    parent_id=paragraph.get("id"),
                )
            self.paragraphs.extend(paragraphs)
            
            self._save_component_crops(img, sentences, out_dir, page_num, "sentences")
            for sentence in sentences:
                self._save_component_crops(
                    img,
                    sentence.get("words", []),
                    out_dir,
                    page_num,
                    "words",
                    parent_id=sentence.get("id"),
                )
            self.sentences.extend(sentences)
            
            # Build all exclusions for Borderless Table
            from piply_opdf.models.grid import GridBoundingBox
            all_exclusions = list(table_boxes)
            for kv in key_values:
                if kv.get("bbox"):
                    x, y, w, h = kv["bbox"]
                    all_exclusions.append(GridBoundingBox(x=x, y=y, width=w, height=h))
            for p in paragraphs:
                if p.get("bbox"):
                    x, y, w, h = p["bbox"]
                    all_exclusions.append(GridBoundingBox(x=x, y=y, width=w, height=h))
            for s in sentences:
                if s.get("bbox"):
                    x, y, w, h = s["bbox"]
                    all_exclusions.append(GridBoundingBox(x=x, y=y, width=w, height=h))

            # --- STAGE 2: Borderless Table Detection (P2) ---
            borderless = borderless_detector.detect_tables(str(self.source_path), page_num, all_exclusions)
            self.borderless_tables.extend(borderless)
            
            import cv2
            for b in borderless:
                tx, ty, tw, th = b.bbox
                ih, iw = img.shape[:2]
                ty1, ty2 = max(0, ty), min(ih, ty + th)
                tx1, tx2 = max(0, tx), min(iw, tx + tw)
                if tx2 > tx1 and ty2 > ty1:
                    b_img = img[ty1:ty2, tx1:tx2]
                    b_dir = out_dir / f"page_{page_num}" / b.id
                    b_dir.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(b_dir / "table.png"), b_img)
                    
                    import json
                    from piply_opdf.models.grid import TableManifest, ColumnManifest, RowManifest, CellManifest
                    
                    import shutil
                    col_dir = b_dir / "columns"
                    if col_dir.exists():
                        shutil.rmtree(col_dir)
                    col_dir.mkdir(parents=True, exist_ok=True)
                    
                    for i, (cx, cy, cw, ch) in enumerate(b.columns):
                        cx1, cx2 = max(0, cx), min(iw, cx + cw)
                        cy1, cy2 = max(0, cy), min(ih, cy + ch)
                        if cx2 > cx1 and cy2 > cy1:
                            col_img = img[cy1:cy2, cx1:cx2]
                            col_id = f"col_{i:03d}"
                            cv2.imwrite(str(col_dir / f"{col_id}.png"), col_img)
                            
                            c_manifest = ColumnManifest(
                                column_id=col_id,
                                parent_table=b.id,
                                bbox=(cx, cy, cw, ch),
                                confidence=b.confidence
                            )
                            with open(col_dir / f"{col_id}_manifest.json", "w") as f:
                                json.dump(c_manifest.model_dump(), f, indent=2)
                                
                    row_dir = b_dir / "rows"
                    if row_dir.exists():
                        shutil.rmtree(row_dir)
                    row_dir.mkdir(parents=True, exist_ok=True)
                    
                    for i, (rx, ry, rw, rh) in enumerate(b.rows):
                        rx1, rx2 = max(0, rx), min(iw, rx + rw)
                        ry1, ry2 = max(0, ry), min(ih, ry + rh)
                        if rx2 > rx1 and ry2 > ry1:
                            row_img = img[ry1:ry2, rx1:rx2]
                            row_id = f"row_{i:03d}"
                            cv2.imwrite(str(row_dir / f"{row_id}.png"), row_img)
                            
                            r_manifest = RowManifest(
                                row_id=row_id,
                                parent_table=b.id,
                                bbox=(rx, ry, rw, rh),
                                confidence=b.confidence
                            )
                            with open(row_dir / f"{row_id}_manifest.json", "w") as f:
                                json.dump(r_manifest.model_dump(), f, indent=2)

                    cell_dir = b_dir / "cells"
                    if cell_dir.exists():
                        shutil.rmtree(cell_dir)
                    cell_dir.mkdir(parents=True, exist_ok=True)
                    
                    b.cells = []
                    for r_idx, (rx, ry, rw, rh) in enumerate(b.rows):
                        for c_idx, (cx, cy, cw, ch) in enumerate(b.columns):
                            # Intersection
                            if hasattr(b, 'type') and b.type == "table":
                                # Shrink the bounding box slightly to avoid capturing the table grid lines!
                                # Capturing grid lines causes PaddleOCR to hallucinate '7', 'J', 'l', etc.
                                x1 = max(rx, cx) + 3
                                x2 = min(rx + rw, cx + cw) - 3
                                y1 = ry + 3
                                y2 = ry + rh - 3
                            else:
                                x1 = cx - 5
                                x2 = cx + cw + 5
                                if c_idx == 0:
                                    # Generous padding to account for PyMuPDF vs pdf2image CropBox differences
                                    x1 = min(rx, cx) - 150
                                if c_idx == len(b.columns) - 1:
                                    x2 = max(rx + rw, cx + cw) + 150
                                y1 = ry
                                y2 = ry + rh
                            
                            if x2 > x1 and y2 > y1:
                                rx1_crop, rx2_crop = max(0, x1), min(iw, x2)
                                ry1_crop, ry2_crop = max(0, y1), min(ih, y2)
                                
                                cell_img = img[ry1_crop:ry2_crop, rx1_crop:rx2_crop]
                                cell_id = f"{b.id}_r{r_idx}_c{c_idx}"
                                cv2.imwrite(str(cell_dir / f"{cell_id}.png"), cell_img)
                                
                                c_manifest = CellManifest(
                                    cell_id=cell_id,
                                    parent_table=b.id,
                                    parent_column=f"col_{c_idx:03d}",
                                    row=r_idx,
                                    column=c_idx,
                                    bbox=(x1, y1, x2 - x1, y2 - y1),
                                    confidence=b.confidence
                                )
                                with open(cell_dir / f"{cell_id}_manifest.json", "w") as f:
                                    json.dump(c_manifest.model_dump(), f, indent=2)
                                
                                b.cells.append(c_manifest)
                    
                    b_manifest = TableManifest(
                        table_id=b.id,
                        page=b.page,
                        rows=len(b.rows) if b.rows else 1,
                        columns=len(b.columns) if b.columns else 1,
                        bbox=b.bbox,
                        confidence=b.confidence
                    )
                    with open(b_dir / "manifest.json", "w") as f:
                        json.dump(b_manifest.model_dump(), f, indent=2)
                        
            
            # Optional: Save P2/P3/P4 metadata to JSON for the page
            import json
            page_meta_dir = out_dir / f"page_{page_num}"
            page_meta_dir.mkdir(parents=True, exist_ok=True)
            
            with open(page_meta_dir / "components.json", "w") as f:
                json.dump({
                    "borderless_tables": [b.model_dump() for b in borderless],
                    "headers": headers,
                    "footers": footers,
                    "key_values": key_values,
                    "paragraphs": paragraphs,
                    "sentences": sentences
                }, f, indent=2)
                
        self.generate_master_manifest()
        return self.tables

    def generate_master_manifest(self, output_path: str | Path | None = None) -> Path:
        """
        Generates a master_manifest.json representation of all detected components
        (tables, borderless tables, headers, footers).
        """
        import json
        out = Path(output_path) if output_path else self.work_dir / "master_manifest.json"
        
        manifest = {
            "document_path": str(self.source_path),
            "tables": [t.model_dump() if hasattr(t, 'model_dump') else t for t in self.tables],
            "borderless_tables": [bt.model_dump() if hasattr(bt, 'model_dump') else bt for bt in self.borderless_tables],
            "headers": [h.model_dump() if hasattr(h, 'model_dump') else h for h in self.headers],
            "footers": [f.model_dump() if hasattr(f, 'model_dump') else f for f in self.footers],
            "key_values": [kv.model_dump() if hasattr(kv, 'model_dump') else kv for kv in self.key_values],
            "paragraphs": [p.model_dump() if hasattr(p, 'model_dump') else p for p in self.paragraphs],
            "sentences": [s.model_dump() if hasattr(s, 'model_dump') else s for s in self.sentences]
        }
        
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, default=str)
            
        return out



    # ── Convenience ───────────────────────────────────────────────────────────

    def run_all(self) -> dict[str, Any]:
        """
        Run the complete Phase 1–5 pipeline in sequence.

        Returns
        -------
        dict
            Dictionary with keys: assessment, enhanced_path, layout, manifest, ocr_result
        """
        logger.info("Running full pipeline on %s", self.source_path.name)
        assessment = self.assess()
        enhanced_path = self.enhance()
        layout = self.process_layout()
        return {
            "assessment": assessment,
            "enhanced_path": enhanced_path,
            "layout": layout,
        }

    def _resolve_source(self, use_enhanced: bool) -> Path:
        """Return the enhanced path if available and requested, else original."""
        if use_enhanced and self._enhanced_path is not None and self._enhanced_path.exists():
            return self._enhanced_path
        return self.source_path

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def assessment(self) -> AssessmentResult | None:
        return self._assessment

    @property
    def enhanced_path(self) -> Path | None:
        return self._enhanced_path


    def _component_bboxes(self, *component_groups: Any) -> list[tuple[int, int, int, int]]:
        bboxes: list[tuple[int, int, int, int]] = []

        for group in component_groups:
            if not group:
                continue
            for component in group:
                bbox = None
                if hasattr(component, "bbox"):
                    bbox = component.bbox
                elif hasattr(component, "to_tuple"):
                    bbox = component.to_tuple()
                elif isinstance(component, dict):
                    bbox = component.get("bbox")

                if hasattr(bbox, "to_tuple"):
                    bbox = bbox.to_tuple()

                if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                    bboxes.append(tuple(int(v) for v in bbox))

        return bboxes

    def _save_component_crops(
        self,
        image: Any,
        components: list[dict[str, Any]],
        out_dir: Path,
        page_num: int,
        folder: str,
        parent_id: str | None = None,
    ) -> None:
        import cv2
        import json

        if not components:
            return

        page_dir = out_dir / f"page_{page_num}" / folder
        page_dir.mkdir(parents=True, exist_ok=True)
        img_h, img_w = image.shape[:2]

        for idx, component in enumerate(components, start=1):
            bbox = component.get("bbox")
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                continue

            x, y, w, h = [int(v) for v in bbox]
            pad = 2 if folder == "words" else 4
            x1 = max(0, x - pad)
            y1 = max(0, y - pad)
            x2 = min(img_w, x + w + pad)
            y2 = min(img_h, y + h + pad)

            if x2 <= x1 or y2 <= y1:
                continue

            component_id = component.get("id") or f"{folder}_{page_num:03d}_{idx:03d}"
            image_path = page_dir / f"{component_id}.png"
            manifest_path = page_dir / f"{component_id}_manifest.json"

            cv2.imwrite(str(image_path), image[y1:y2, x1:x2])
            component["image_path"] = str(image_path)
            component["manifest_path"] = str(manifest_path)
            if parent_id:
                component["parent_id"] = parent_id

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(component, f, indent=2, default=str)


    def __repr__(self) -> str:
        return f"Document(source='{self.source_path.name}', work_dir='{self.work_dir}')"
