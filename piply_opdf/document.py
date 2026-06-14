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
from piply_opdf.detectors.table_detector import TableDetector
from piply_opdf.detectors.borderless_table_detector import BorderlessTableDetector
from piply_opdf.detectors.header_detector import HeaderDetector
from piply_opdf.detectors.footer_detector import FooterDetector

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
        
        out_dir = self.work_dir / "layouts"
        debug_dir = self.work_dir / "debug"
        
        table_idx = 1
        previous_table_cols = None
        previous_table_id = None
        
        # Also store other components for metadata saving later
        self.borderless_tables = []
        self.headers = []
        self.footers = []
        
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
                table_model = grid_builder.build_grid(t_id, t_box, page_num, cols, row_cands)
                
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
                
            # --- STAGE 2: Borderless Table Detection (P2) ---
            borderless = borderless_detector.detect_tables(str(self.source_path), page_num, table_boxes)
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
                    from piply_opdf.models.grid import TableManifest, ColumnManifest
                    
                    col_dir = b_dir / "columns"
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
                    
                    b_manifest = TableManifest(
                        table_id=b.id,
                        page=b.page,
                        rows=1,
                        columns=len(b.columns) if b.columns else 1,
                        bbox=b.bbox,
                        confidence=b.confidence
                    )
                    with open(b_dir / "manifest.json", "w") as f:
                        json.dump(b_manifest.model_dump(), f, indent=2)
                        
            # --- STAGE 3: Header Detection (P3) ---
            headers = header_detector.detect_headers(str(self.source_path), page_num)
            self.headers.extend(headers)
            
            # --- STAGE 4: Footer Detection (P4) ---
            footers = footer_detector.detect_footers(str(self.source_path), page_num)
            self.footers.extend(footers)
            
            # Optional: Save P2/P3/P4 metadata to JSON for the page
            import json
            page_meta_dir = out_dir / f"page_{page_num}"
            page_meta_dir.mkdir(parents=True, exist_ok=True)
            
            with open(page_meta_dir / "components.json", "w") as f:
                json.dump({
                    "borderless_tables": [b.model_dump() for b in borderless],
                    "headers": headers,
                    "footers": footers
                }, f, indent=2)
                
        return self.tables



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



    def __repr__(self) -> str:
        return f"Document(source='{self.source_path.name}', work_dir='{self.work_dir}')"
