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
from piply_opdf.models.layout import LayoutManifest, LayoutResult
from piply_opdf.models.ocr_result import OCRResult
from piply_opdf.phases.phase1_assess import DocumentAssessor
from piply_opdf.phases.phase2_enhance import DocumentEnhancer
from piply_opdf.phases.phase3_layout import LayoutDetector
from piply_opdf.phases.phase4_extract import LayoutExtractor
from piply_opdf.phases.phase5_ocr import OCRProcessor

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
        self._layout_result: LayoutResult | None = None
        self._layout_manifest: LayoutManifest | None = None
        self._ocr_result: OCRResult | None = None

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

    # ── Phase 3: Layout Detection ─────────────────────────────────────────────

    def detect_layout(
        self,
        output_path: str | Path | None = None,
        use_enhanced: bool = True,
    ) -> LayoutResult:
        """
        Phase 3 — Detect document layout structure.

        Parameters
        ----------
        output_path:
            Override for the output layout.json path.
        use_enhanced:
            When True, uses the enhanced PDF if it exists; falls back to original.

        Returns
        -------
        LayoutResult
        """
        source = self._resolve_source(use_enhanced)
        out = Path(output_path) if output_path else self.work_dir / "layout.json"

        detector = LayoutDetector(config=self.config)
        self._layout_result = detector.detect(source, output_path=out)
        return self._layout_result

    # ── Phase 4: Layout Extraction ────────────────────────────────────────────

    def extract_layouts(
        self,
        output_dir: str | Path | None = None,
        use_enhanced: bool = True,
    ) -> LayoutManifest:
        """
        Phase 4 — Extract layout regions as individual image files.

        Runs Phase 3 automatically if not yet done.

        Parameters
        ----------
        output_dir:
            Override for the output directory for cropped images.
        use_enhanced:
            When True, crops from the enhanced PDF if it exists.

        Returns
        -------
        LayoutManifest
        """
        if self._layout_result is None:
            self.detect_layout(use_enhanced=use_enhanced)

        source = self._resolve_source(use_enhanced)
        out_dir = Path(output_dir) if output_dir else self.work_dir / "layouts"

        extractor = LayoutExtractor(config=self.config)
        self._layout_manifest = extractor.extract(
            source,
            self._layout_result,  # type: ignore[arg-type]
            output_dir=out_dir,
        )
        return self._layout_manifest

    # ── Phase 5: OCR ─────────────────────────────────────────────────────────

    def ocr(
        self,
        output_path: str | Path | None = None,
    ) -> OCRResult:
        """
        Phase 5 — Run OCR on extracted layout regions.

        Runs Phases 3 & 4 automatically if not yet done.

        Parameters
        ----------
        output_path:
            Override for the output ocr_result.json path.

        Returns
        -------
        OCRResult
        """
        if self._layout_manifest is None:
            self.extract_layouts()

        out = Path(output_path) if output_path else self.work_dir / "ocr_result.json"

        processor = OCRProcessor(config=self.config)
        self._ocr_result = processor.ocr_manifest(
            self._layout_manifest,  # type: ignore[arg-type]
            output_path=out,
        )
        # Patch engine name
        self._ocr_result.engine_used = processor.engine.name
        return self._ocr_result

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
        layout = self.detect_layout()
        manifest = self.extract_layouts()
        ocr_result = self.ocr()
        return {
            "assessment": assessment,
            "enhanced_path": enhanced_path,
            "layout": layout,
            "manifest": manifest,
            "ocr_result": ocr_result,
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

    @property
    def layout_result(self) -> LayoutResult | None:
        return self._layout_result

    @property
    def layout_manifest(self) -> LayoutManifest | None:
        return self._layout_manifest

    @property
    def ocr_result(self) -> OCRResult | None:
        return self._ocr_result

    def __repr__(self) -> str:
        return f"Document(source='{self.source_path.name}', work_dir='{self.work_dir}')"
