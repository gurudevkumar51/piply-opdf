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
from piply_opdf.core import BBox, ComponentType, PageContext
from piply_opdf.quality.images import PageImages, build_page_images
from piply_opdf.core.segmenter import segment_tree
from piply_opdf.preprocessing import deskew
from piply_opdf.models.assessment import AssessmentResult
# Importing the package registers every segmenter in the registry.
import piply_opdf.segmentation  # noqa: F401
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
from piply_opdf.detectors.table.key_value_shape import looks_like_key_value_grid
from piply_opdf.detectors.borderless_table import BorderlessTableDetector
from piply_opdf.detectors.header import HeaderDetector
from piply_opdf.detectors.footer import FooterDetector
from piply_opdf.detectors.key_value import KeyValueDetector
from piply_opdf.detectors.paragraph import ParagraphDetector
from piply_opdf.detectors.list_item import ListItemDetector
from piply_opdf.detectors.title import TitleDetector
from piply_opdf.detectors.graphic import GraphicDetector
from piply_opdf.detectors.panel import PanelDetector

logger = logging.getLogger(__name__)

#: A borderless table must have at least this many rows and columns. Below the
#: column threshold a block of aligned text is a list of label/value pairs, not
#: a table — see the note where these are applied.
MIN_BORDERLESS_ROWS = 2
MIN_BORDERLESS_COLUMNS = 3


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
        layout_store: Any | None = None,
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
        #: The three images each page was carried through, keyed by page
        #: number. Detection reads ``structural``; OCR should read ``working``.
        self.page_images: dict[int, PageImages] = {}
        #: Regions the baseline model found that the rules did not. Kept apart
        #: from the rule-based collections so which detector found what stays
        #: answerable.
        self.baseline_regions: list[dict] = []
        #: One fusion summary per page, for diagnosis.
        self.fusion_reports: dict[int, str] = {}
        #: An open :class:`~piply_opdf.knowledge.LayoutKnowledgeStore`, or None.
        #: Optional because the package must work without one — a knowledge
        #: base that has to exist before anything runs is a knowledge base
        #: nobody can start using.
        self.layout_store = layout_store
        #: How well each page's confidence scores separated, keyed by page.
        #: Worth watching: if they bunch, the review queue is arbitrary however
        #: it is sorted, which is the failure the evidence score replaces.
        self.confidence_reports: dict[int, Any] = {}
        #: Each detector's track record, read once from the layout store's
        #: feedback log. Empty until people have reviewed something.
        self._history: dict[str, Any] = {}

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

    def process_layout(
        self,
        use_enhanced: bool = True,
        use_baseline: bool = False,
    ) -> list[TableModel]:
        """
        Runs the new modular table and grid extraction engine.
        Follows Priority Order: P1 (Tables), P2 (Borderless), P3 (Headers), P4 (Footers).

        Parameters
        ----------
        use_enhanced:
            Kept for existing callers and ignored — layout always reads the
            structural image. See :meth:`_resolve_source`.
        use_baseline:
            Run the trained layout model alongside the rules and fuse the two.
            **Off by default**: it adds several seconds per page, and switching
            it on changes what is detected, so it should be a deliberate choice
            that can be measured before and after.
        """
        source = self._resolve_source(use_enhanced)
        self.tables = []
        self.page_images = {}
        self._history = self._read_history()
        self.baseline_regions = []
        self.fusion_reports = {}
        #: Boxed regions — closed frames with no internal division.
        self.panels = []
        
        # P1
        table_detector = TableDetector()
        panel_detector = PanelDetector()
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
        list_item_detector = ListItemDetector()
        paragraph_detector = ParagraphDetector()
        title_detector = TitleDetector()
        graphic_detector = GraphicDetector()
        
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
        self.list_items = []
        self.titles = []
        #: Regions no text detector claimed: signatures, handwriting, logos,
        #: photographs, and anything the classifier could not type.
        self.graphics = []
        
        for page_idx, original in iter_pages(source, dpi=300):
            page_num = page_idx + 1

            # A page is carried as three images. Detection reads the
            # **structural** one — orientation and deskew only. The enhanced
            # image exists for OCR and is deliberately not used here: measured
            # on sample.pdf, enhancing cost a 171-cell table at 0.05 degrees of
            # rotation, where the unenhanced page survived 2 degrees. Sharpening
            # for legibility thins the hairline rules tables are found by.
            #
            # Pages with a text layer are not deskewed: PyMuPDF reports
            # coordinates in the original page frame, so rotating the raster
            # would put the image and the text layer in different coordinate
            # systems. Such pages are digital and not skewed in the first place.
            probe = PageContext(
                page_number=page_num,
                source_path=self.source_path,
                image=original,
                dpi=300,
            )
            images = build_page_images(
                original,
                enhance=self._page_enhancer(page_num),
                has_text_layer=probe.has_text_layer,
            )
            self.page_images[page_num] = images

            if images.skew_corrected:
                logger.info(
                    "Page %d: corrected skew by %.2f degrees",
                    page_num, images.skew_corrected,
                )
            if images.needs_orientation_review:
                # Not turned: which quarter turn is needed cannot be decided
                # from ink alone, so a person chooses. See quality/orientation.
                logger.warning(
                    "Page %d: orientation %s — needs review",
                    page_num, images.orientation.verdict,
                )

            img = images.structural
            page_ctx = PageContext(
                page_number=page_num,
                source_path=self.source_path,
                image=img,
                dpi=300,
                skew_correction=images.skew_corrected,
            )

            # --- STAGE 0.5: Panel Detection ---
            # Before tables: a frame must be checked for internal division
            # before anything claims it as a table. One cell is a panel; two or
            # more is left for the table detector. See docs/components.md Rule 1.
            # Segmented immediately: a container's children come from running
            # the ordinary detectors inside it, so the box is opened up here
            # rather than left as an empty region.
            panel_comps = [
                segment_tree(c, page_ctx) for c in panel_detector.detect(page_ctx)
            ]
            panels = [c.to_dict() for c in panel_comps]
            self._save_component_crops(img, panels, out_dir, page_num, "panels")
            for panel in panels:
                self._save_component_crops(
                    img, panel.get("children", []), out_dir, page_num, "panel_contents",
                    parent_id=panel.get("id"),
                )
            self.panels.extend(panels)

            # Not passed to the text detectors yet: until containers are
            # decomposed (backlog F2) their contents must still be found at
            # page level, otherwise everything inside a box is lost. Only the
            # residual sweep excludes them, so frame lines are not reported as
            # unknown regions.
            panel_exclusions = [
                b for b in (BBox.from_any(p["bbox"]) for p in panels) if b
            ]

            # --- STAGE 1: Structured Table Detection (P1) ---
            #: Grids that turned out to be key-value lists. Held separately so
            #: the later detectors treat them as claimed, exactly as a table
            #: would be.
            kv_claimed: list[BBox] = []
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
                
                # A form often rules a box around what is really a list of
                # labelled fields. The grid detector sees the rules and calls
                # it a table, but its columns are not carrying different kinds
                # of data — they are label, separator and value, with empty
                # spacers between. Reported as a table, the value of `PAN` ends
                # up in "row 3, column 4" instead of under its own name.
                if looks_like_key_value_grid(img, table_model):
                    rows_as_pairs = self._grid_rows_as_key_values(
                        img, table_model, page_num, out_dir
                    )
                    self.key_values.extend(rows_as_pairs)
                    kv_claimed.extend(
                        b for b in (BBox.from_any(kv["bbox"]) for kv in rows_as_pairs) if b
                    )
                    continue

                self.tables.append(table_model)
                
                # Store the last table's columns and ID for the next page's continuation check
                if i == len(table_boxes) - 1:
                    previous_table_cols = cols
                    previous_table_id = t_id
                    
            # If no tables were found on this page, break the continuation chain
            if not table_boxes:
                previous_table_cols = None
                previous_table_id = None

            # Create tight bounding boxes from actual table cells to avoid excluding surrounding text.
            # Computed before header/footer detection so those detectors can treat
            # table area as claimed — without it, a header sitting directly above a
            # table merges into one region with the table's first rows on scans.
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

            table_exclusions = [BBox.from_any(b) for b in table_bboxes]
            table_exclusions = [b for b in table_exclusions if b is not None]

            # --- STAGE 1.5: Borderless Table Detection (P2) ---
            # Runs immediately after bordered tables, and *before* the text
            # detectors. A borderless table's rows look exactly like key-values
            # or paragraphs, so whichever runs first claims them. Running this
            # last — as it used to — meant a page that is entirely a borderless
            # table produced key-values and no table at all.
            from piply_opdf.models.grid import GridBoundingBox

            borderless_input = list(table_boxes) + [
                GridBoundingBox(x=p_.x, y=p_.y, width=p_.width, height=p_.height)
                for p_ in panel_exclusions
            ]
            borderless = borderless_detector.detect_tables(
                str(self.source_path), page_num, borderless_input
            )

            # A borderless table needs at least two rows and three columns.
            #
            # Two columns of aligned text is not distinguishable from a list of
            # label/value pairs, and the key-value detector reads those far
            # better — it finds the separator and splits key from value. On real
            # documents every two-column "table" was a form block, and claiming
            # it here wiped out every key-value on the page.
            #
            # Three or more columns is unambiguously tabular.
            borderless = [
                bt for bt in borderless
                if len(getattr(bt, "rows", [])) >= MIN_BORDERLESS_ROWS
                and len(getattr(bt, "columns", [])) >= MIN_BORDERLESS_COLUMNS
            ]
            self.borderless_tables.extend(borderless)

            borderless_exclusions = [
                b for b in (BBox.from_any(tuple(bt.bbox)) for bt in borderless) if b
            ]

            # --- STAGE 2.5: Title Detection ---
            # Ahead of the header: a prominent heading sits in the top band, so
            # whichever runs first claims it. A large, short, typographically
            # distinct line is a title; the running header is what remains.
            title_comps = title_detector.detect(page_ctx, table_exclusions)
            titles = [segment_tree(c, page_ctx).to_dict() for c in title_comps]
            self._save_component_crops(img, titles, out_dir, page_num, "titles")
            for t in titles:
                self._save_component_crops(
                    img, t.get("children", []), out_dir, page_num, "words",
                    parent_id=t.get("id"),
                )
            self.titles.extend(titles)

            title_exclusions = table_exclusions + borderless_exclusions + [
                b for b in (BBox.from_any(t["bbox"]) for t in titles) if b
            ]

            # --- STAGE 3: Header Detection (P3) ---
            # Text layer when present, CV fallback on scans — see detectors.header.
            header_comps = header_detector.detect(page_ctx, title_exclusions)
            headers = [segment_tree(c, page_ctx).to_dict() for c in header_comps]
            self._save_component_crops(img, headers, out_dir, page_num, "headers")
            for h in headers:
                self._save_component_crops(
                    img, h.get("children", []), out_dir, page_num, "words",
                    parent_id=h.get("id"),
                )
            self.headers.extend(headers)

            # --- STAGE 4: Footer Detection (P4) ---
            footer_comps = footer_detector.detect(page_ctx, title_exclusions)
            footers = [segment_tree(c, page_ctx).to_dict() for c in footer_comps]
            self._save_component_crops(img, footers, out_dir, page_num, "footers")
            for f in footers:
                self._save_component_crops(
                    img, f.get("children", []), out_dir, page_num, "words",
                    parent_id=f.get("id"),
                )
            self.footers.extend(footers)

            # Exclusions accumulate as each stage claims page area, so later
            # detectors never re-report a region an earlier one already owns.
            claimed = list(title_exclusions)
            claimed += kv_claimed
            claimed += [b for b in (BBox.from_any(h["bbox"]) for h in headers) if b]
            claimed += [b for b in (BBox.from_any(f["bbox"]) for f in footers) if b]

            # --- STAGE 5: Key-Value Detection (P5) ---
            # Segmented into KEY / SEPARATOR / VALUE so a recurring key is
            # verified once and reused, independently of its varying value.
            kv_comps = key_value_detector.detect(page_ctx, claimed)
            key_values = [segment_tree(c, page_ctx).to_dict() for c in kv_comps]
            self._save_component_crops(img, key_values, out_dir, page_num, "key_values")
            for kv in key_values:
                self._save_component_crops(
                    img, kv.get("children", []), out_dir, page_num, "words",
                    parent_id=kv.get("id"),
                )
            self.key_values.extend(key_values)
            claimed += [b for b in (BBox.from_any(kv["bbox"]) for kv in key_values) if b]

            # --- STAGE 5.5: List Item Detection ---
            list_items = [
                c.to_dict() for c in list_item_detector.detect(page_ctx, claimed)
            ]
            self._save_component_crops(img, list_items, out_dir, page_num, "list_items")
            for li in list_items:
                self._save_component_crops(
                    img, li.get("children", []), out_dir, page_num, "words",
                    parent_id=li.get("id"),
                )
            self.list_items.extend(list_items)
            claimed += [b for b in (BBox.from_any(li["bbox"]) for li in list_items) if b]

            # --- STAGE 6: Paragraph Detection (P6) ---
            # The detector emits SENTENCE for single-line runs and PARAGRAPH for
            # multi-line runs in one list; split them for downstream consumers.
            prose = [c.to_dict() for c in paragraph_detector.detect(page_ctx, claimed)]
            paragraphs = [c for c in prose if c["type"] == "PARAGRAPH"]
            sentences = [c for c in prose if c["type"] == "SENTENCE"]

            self._save_component_crops(img, paragraphs, out_dir, page_num, "paragraphs")
            for paragraph in paragraphs:
                self._save_component_crops(
                    img,
                    paragraph.get("children", []),
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
                    sentence.get("children", []),
                    out_dir,
                    page_num,
                    "words",
                    parent_id=sentence.get("id"),
                )
            self.sentences.extend(sentences)
            


            # --- STAGE 7: Residual / Graphic Sweep ---
            # Runs last, with everything claimed so far as exclusions. Whatever
            # ink is left is content no text detector recognised: logos,
            # signatures, handwriting, photographs. Typed by the content
            # classifier, or kept as UNKNOWN so a page never silently loses
            # content and the decision can be deferred.
            residual_claimed = list(claimed) + panel_exclusions
            residual_claimed += [
                b for b in (BBox.from_any(p["bbox"]) for p in paragraphs) if b
            ]
            residual_claimed += [
                b for b in (BBox.from_any(s["bbox"]) for s in sentences) if b
            ]
            residual_claimed += borderless_exclusions

            graphics = [
                c.to_dict() for c in graphic_detector.detect(page_ctx, residual_claimed)
            ]
            self._save_component_crops(img, graphics, out_dir, page_num, "graphics")
            self.graphics.extend(graphics)

            # --- STAGE 8: Baseline layout model, fused with the rules ---
            # Off unless asked for. The two are complementary rather than
            # competing — measured on the corpus, the model finds headings and
            # borderless tables the rules miss, while the rules find key-values,
            # panels and marks the model has no concept of. Where both claim a
            # region and name it differently, the component is flagged rather
            # than resolved silently.
            if use_baseline:
                self._fuse_baseline(page_ctx, page_num)

            # --- STAGE 9: Confidence, from evidence rather than literals ---
            # Last, because it reads what every earlier stage produced: the
            # rule that fired, the shape it produced, the ink inside it, and
            # the baseline's opinion where there was one. Running it before
            # fusion would score components the model had not yet weighed in
            # on.
            self._score_page(page_num)

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
                        
            
            # --- STAGE 10: Confidence for the grid ---
            # After the cells exist, which is why it is not part of stage 9.
            # A cell's shape proves nothing, so this asks the one thing that
            # can be wrong — does it sit inside its table — and reads its ink.
            self._score_grid(page_num)

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
        """Where the page rasters are read from.

        **Always the original.** Layout detection needs geometry, and the
        enhanced PDF is built for legibility — measured on ``sample.pdf``, it
        lost a 171-cell table at 0.05 degrees of rotation where the original
        survived 2 degrees.

        Enhancement has not gone away: it is applied per page, in memory, by
        :func:`~piply_opdf.quality.images.build_page_images`, and kept on
        ``PageImages.working`` for OCR to read. That is also where it is checked
        for having destroyed structure.

        *use_enhanced* is kept so existing callers do not break, and is ignored.
        """
        if use_enhanced and self._enhanced_path is not None:
            logger.debug(
                "Layout reads the original raster; the enhanced PDF is for OCR."
            )
        return self.source_path

    def _page_enhancer(self, page_num: int):
        """An enhancement function for one page, or None to skip enhancement.

        Returns None when the assessment says the page does not need cleaning,
        which is what makes ``working is structural`` for a clean page — no
        copy, no processing, no risk.
        """
        assessment = self._assessment
        if assessment is None:
            return None

        page = None
        for candidate in getattr(assessment, "pages", []) or []:
            if getattr(candidate, "page_number", None) == page_num:
                page = candidate
                break

        if page is not None and not getattr(page, "enhancement_needed", True):
            return None

        enhancer = DocumentEnhancer(config=self.config)
        return lambda image: enhancer.enhance_image(image, page)

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

    def _fuse_baseline(self, page_ctx: PageContext, page_num: int) -> None:
        """Run the baseline layout model and fuse it with what the rules found.

        Regions only the model found are appended to :attr:`baseline_regions`
        rather than merged into the rule-based collections. That keeps the two
        distinguishable: an operator, and the evaluation harness, can both see
        which detector is responsible for what.
        """
        from piply_opdf.baseline import baseline_detector, is_available
        from piply_opdf.fusion import fuse

        if not is_available():
            logger.info("Baseline layout model unavailable; rules only")
            return

        regions = baseline_detector().detect(page_ctx)
        if not regions:
            return

        existing = self._components_on_page(page_num)
        outcome = fuse(existing, regions)

        self.baseline_regions.extend(
            component.to_dict() for component in outcome.components
            if component.metadata.get("fusion") == "baseline only"
        )
        self.fusion_reports[page_num] = outcome.summary()

        logger.info("Page %d fusion: %s", page_num, outcome.summary())

    def _components_on_page(self, page_num: int) -> list:
        """Every rule-detected component on a page, as DetectedComponent."""
        return [component for _source, component, _sibs, _parent
                in self._page_components(page_num)]

    def _page_components(self, page_num: int) -> list[tuple[Any, Any, Any, Any]]:
        """``(source, component, siblings, parent)`` for everything on a page.

        ``source`` is the object the component was built from — a raw dict for
        most collections, a table model for tables. Handed back alongside so a
        result worked out here (a confidence, say) can be written where the
        rest of the pipeline will actually read it, rather than onto a copy
        that is thrown away.

        ``siblings`` and ``parent`` come along because a region's *relationships*
        are what make a description transferable to another document, and they
        can only be worked out here, while the tree is still standing.
        """
        from piply_opdf.core.types import DetectedComponent

        found: list[tuple[Any, DetectedComponent, list, Any]] = []

        def build(raw: dict) -> DetectedComponent | None:
            box = BBox.from_any(raw.get("bbox"))
            if box is None:
                return None
            return DetectedComponent(
                id=raw.get("id", ""),
                type=raw.get("type", "UNKNOWN"),
                page=page_num,
                bbox=box,
                confidence=raw.get("confidence", 0.5),
                metadata=raw.get("metadata", {}) or {},
            )

        def collect(level: list[dict], parent: DetectedComponent | None) -> None:
            """One level of the tree, then each child level in turn.

            Children are included deliberately. Most of what a person actually
            reviews is cells and segmented units, not the container that holds
            them — on `sample.pdf` the top level is 4 regions and the tree
            below it is nearly 200. Scoring only the top level would leave the
            review queue describing the handful of things nobody was worried
            about.

            Relationships are scoped to a level: the children of a table are
            positioned against each other, not against a logo elsewhere on the
            page.
            """
            built = [(raw, build(raw)) for raw in level]
            siblings = [c for _raw, c in built if c is not None]

            for raw, component in built:
                if component is None:
                    continue
                found.append((raw, component, siblings, parent))
                children = [c for c in (raw.get("children") or []) if isinstance(c, dict)]
                if children:
                    collect(children, component)

        for name in ("panels", "headers", "footers", "titles", "key_values",
                     "paragraphs", "sentences", "list_items", "graphics"):
            collect([raw for raw in (getattr(self, name, []) or [])
                     if raw.get("page", 1) == page_num], None)

        for table in list(self.tables) + list(self.borderless_tables):
            if getattr(table, "page", 1) != page_num:
                continue
            tb = getattr(table, "bbox", None)
            if tb is None:
                continue
            found.append((
                table,
                DetectedComponent(
                    id=str(getattr(table, "table_id", "")),
                    type=ComponentType.TABLE,
                    page=page_num,
                    bbox=BBox(int(tb.x), int(tb.y), int(tb.width), int(tb.height)),
                    confidence=getattr(table, "confidence", 0.8),
                ),
                [], None,
            ))
        return found

    def _score_page(self, page_num: int) -> None:
        """Replace each component's literal confidence with an evidence score.

        The literal is not discarded — it becomes ``detector_evidence``, one of
        six signals, because "this rule fired at 0.85" is genuine evidence about
        the region. What changes is that it stops being the *whole* answer.

        The itemised evidence is written to ``metadata['confidence']`` so it
        travels with the component into the manifest and the database. A score
        whose reasoning was thrown away cannot be argued with, and an operator
        who cannot argue with it will either trust it blindly or ignore it.

        Scores are a **ranking, not a probability**, until the weights are
        fitted against a labelled corpus. :attr:`confidence_reports` records
        whether they separated enough to be worth sorting at all.
        """
        from piply_opdf.confidence import assess, spread
        from piply_opdf.knowledge import describe

        images = self.page_images.get(page_num)
        if images is None:
            return
        height, width = images.structural.shape[:2]

        scored = []
        for source, component, siblings, parent in self._page_components(page_num):
            crop = self._crop(images.structural, component.bbox)
            # Described first, then handed to the scorer. Relationships need
            # the tree, and the tree only exists now; by the time a person
            # confirms the region its siblings are rows in a database, and
            # putting them back together would be guesswork. The knowledge
            # signal needs the same description, so it is computed once.
            features = describe(
                component, (width, height),
                siblings=siblings, parent=parent, crop=crop,
            )
            confidence = assess(
                component, (width, height), crop=crop, store=self.layout_store,
                history=self._history, parent=parent, features=features,
            )
            scored.append(confidence)

            if isinstance(source, dict):
                source["confidence"] = round(confidence.score, 4)
                extra = source.setdefault("metadata", {})
                extra["confidence"] = confidence.as_metadata()
                extra["layout_features"] = features.as_row()
            else:
                source.confidence = round(confidence.score, 4)
                if hasattr(source, "metadata"):
                    source.metadata = {**(source.metadata or {}),
                                       "confidence": confidence.as_metadata(),
                                       "layout_features": features.as_row()}

        if scored:
            self.confidence_reports[page_num] = spread(scored)
            logger.info("Page %d confidence: %s",
                        page_num, self.confidence_reports[page_num].summary())

    def _read_history(self) -> dict[str, Any]:
        """Each detector's track record, from the layout feedback log.

        Read once per run rather than per component: it is the same answer for
        every region, and it changes only when a person reviews something.

        Empty when no store is attached or nobody has reviewed anything, which
        makes ``historical_reliability`` unmeasured rather than zero — an
        untested detector must not read as a failing one.
        """
        if self.layout_store is None:
            return {}
        try:
            from piply_opdf.knowledge import tally

            return tally(self.layout_store.feedback())
        except Exception as error:                  # a bad store is not fatal
            logger.warning("Could not read review history: %s", error)
            return {}

    def _score_grid(self, page_num: int) -> None:
        """Score the parts of every table: columns, rows and cells.

        Separate from :meth:`_score_page` because the grid is built after the
        detectors have finished, and because grid parts answer a different
        question. A cell's shape says nothing — it is whatever the document
        makes it — so ``geometry_evidence`` asks the one thing that *can* be
        wrong: does it sit inside the table it claims to belong to? A cell that
        escapes its table means the grid was built from lines that are not
        there, and every value in it is then attributed to the wrong column.

        ``structural_evidence`` is the other half, and on real documents it is
        the useful one: it reads the cell's own ink, so a column of signatures
        in a table of typed values stops looking like ordinary text.
        """
        from piply_opdf.confidence import assess
        from piply_opdf.core.types import DetectedComponent
        from piply_opdf.knowledge import describe

        images = self.page_images.get(page_num)
        if images is None:
            return
        height, width = images.structural.shape[:2]
        scored = 0

        for table in list(self.tables) + list(self.borderless_tables):
            if getattr(table, "page", 1) != page_num:
                continue
            parent_box = _grid_bbox(getattr(table, "bbox", None))
            if parent_box is None:
                continue
            parent = DetectedComponent(
                id=str(getattr(table, "table_id", getattr(table, "id", ""))),
                type=ComponentType.TABLE, page=page_num, bbox=parent_box,
            )

            for kind, parts in (
                (ComponentType.COLUMN, getattr(table, "columns", None)),
                (ComponentType.ROW, getattr(table, "rows", None)),
                (ComponentType.CELL, getattr(table, "cells", None)),
            ):
                # Borderless tables keep rows and columns as bare tuples, which
                # have nowhere to record evidence. Skipped rather than silently
                # scored into a value nobody reads.
                usable = [p for p in (parts or []) if hasattr(p, "metadata")
                          and _grid_bbox(getattr(p, "bbox", None)) is not None]

                # A cell's neighbours are the other cells of the same table —
                # which is what makes "a header row is text above rows sharing
                # its column edges" expressible at all.
                siblings = [
                    DetectedComponent(
                        id="", type=kind, page=page_num,
                        bbox=_grid_bbox(part.bbox),
                    )
                    for part in usable
                ]

                for part, component in zip(usable, siblings):
                    box = component.bbox
                    component.id = str(getattr(part, "cell_id", getattr(
                        part, "row_id", getattr(part, "column_id", ""))))
                    component.confidence = getattr(part, "confidence", 1.0)
                    component.metadata = {"detector": "grid-builder"}

                    part_crop = self._crop(images.structural, box)
                    features = describe(
                        component, (width, height), siblings=siblings,
                        parent=parent, crop=part_crop,
                    )
                    confidence = assess(
                        component, (width, height),
                        crop=part_crop,
                        store=self.layout_store,
                        history=self._history,
                        parent=parent,
                        features=features,
                    )
                    part.confidence = round(confidence.score, 4)
                    part.metadata = {**(part.metadata or {}),
                                     "confidence": confidence.as_metadata(),
                                     "layout_features": features.as_row()}
                    scored += 1

        if scored:
            logger.info("Page %d: scored %d grid parts from evidence", page_num, scored)

    @staticmethod
    def _crop(image, box: BBox):
        """The region's own pixels, or None when the box falls outside them."""
        height, width = image.shape[:2]
        x1, y1 = max(0, box.x), max(0, box.y)
        x2, y2 = min(width, box.x1), min(height, box.y1)
        if x2 <= x1 or y2 <= y1:
            return None
        return image[y1:y2, x1:x2]

    def _grid_rows_as_key_values(
        self,
        image,
        table,
        page_num: int,
        out_dir,
    ) -> list[dict]:
        """Turn a grid that is really a labelled-field list into KEY_VALUE rows.

        One pair per row: the leftmost column carrying writing is the label, the
        rightmost is the value, and anything between them is the separator. The
        row's own box is used for the pair, so an operator sees the whole line
        as it appears on the page.
        """
        from piply_opdf.detectors.table.key_value_shape import column_glyph_counts

        counts = column_glyph_counts(image, table)
        floor = len(table.rows) * 0.5
        carrying = [
            col for col, n in zip(table.columns, counts) if n >= floor
        ]
        if len(carrying) < 2:
            return []

        key_col, value_col = carrying[0], carrying[-1]

        pairs: list[dict] = []
        for index, row in enumerate(sorted(table.rows, key=lambda r: r.bbox.y), start=1):
            rb = row.bbox
            pair = {
                "id": f"{table.table_id}_kv_{index:03d}",
                "type": ComponentType.KEY_VALUE,
                "page": page_num,
                "bbox": [rb.x, rb.y, rb.width, rb.height],
                "text": "",
                "confidence": 0.75,
                "index": index,
                "candidates": [],
                "children": [],
                "metadata": {
                    "strategy": "grid-key-value",
                    "needs_ocr": True,
                    "key": "",
                    "value": "",
                    # Kept so the label and the value can be cropped and read
                    # separately once OCR runs.
                    "key_bbox": [key_col.bbox.x, rb.y, key_col.bbox.width, rb.height],
                    "value_bbox": [value_col.bbox.x, rb.y, value_col.bbox.width, rb.height],
                    "from_table": table.table_id,
                },
            }
            pairs.append(pair)

        self._save_component_crops(image, pairs, out_dir, page_num, "key_values")
        return pairs

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


def _grid_bbox(value) -> BBox | None:
    """A BBox from any of the shapes the grid models use.

    ``GridBoundingBox`` for the table models, a bare ``(x, y, w, h)`` tuple for
    the manifests. Returns None rather than guessing when it is neither.
    """
    if value is None:
        return None
    if hasattr(value, "to_tuple"):
        return BBox(*value.to_tuple())
    return BBox.from_any(value)
