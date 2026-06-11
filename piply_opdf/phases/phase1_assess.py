"""
Phase 1 — Document Assessment Engine
=====================================

Determines whether a document needs enhancement before OCR.
Never enhances blindly — always assess first.

Public API
----------
>>> from piply_opdf.phases.phase1_assess import DocumentAssessor
>>> assessor = DocumentAssessor()
>>> result = assessor.assess("invoice.pdf")
>>> result.any_enhancement_needed
True

CLI
---
    piply-opdf assess invoice.pdf
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

from piply_opdf.config import Config, get_default_config
from piply_opdf.models.assessment import AssessmentResult, PageAssessment, QualityLevel
from piply_opdf.utils.image import (
    compute_histogram,
    estimate_noise,
    estimate_skew_angle,
    laplacian_variance,
    rms_contrast,
    to_gray,
)
from piply_opdf.utils.pdf import get_page_metadata, iter_pages, page_count

logger = logging.getLogger(__name__)


class DocumentAssessor:
    """
    Assesses document quality and recommends enhancements.

    Parameters
    ----------
    config:
        Optional Config object; defaults to the package default config.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_default_config()
        cfg = self.config.section("assessment")

        self.blur_threshold: float = cfg.get("blur_threshold", 100.0)
        self.noise_threshold: float = cfg.get("noise_threshold", 0.02)
        self.contrast_threshold: float = cfg.get("contrast_threshold", 50.0)
        self.skew_threshold: float = cfg.get("skew_threshold", 2.0)
        self.min_dpi: int = cfg.get("min_dpi", 150)
        self.render_dpi: int = cfg.get("render_dpi", 300)

    # ── Main entry point ──────────────────────────────────────────────────────

    def assess(
        self,
        source_path: str | Path,
        output_path: str | Path | None = None,
    ) -> AssessmentResult:
        """
        Assess all pages of a PDF (or a single image file).

        Parameters
        ----------
        source_path:
            Path to a PDF or image file.
        output_path:
            If given, write the JSON result to this path.

        Returns
        -------
        AssessmentResult
            Per-page metrics and aggregate flags.
        """
        source_path = Path(source_path)
        logger.info("Assessing document: %s", source_path.name)

        pages: list[PageAssessment] = []

        if source_path.suffix.lower() == ".pdf":
            n_pages = page_count(source_path)
            for page_idx, img in iter_pages(source_path, dpi=self.render_dpi):
                meta = get_page_metadata(source_path, page_idx)
                assessment = self._assess_image(img, page_number=page_idx + 1)
                pages.append(assessment)
                logger.debug("Page %d/%d assessed", page_idx + 1, n_pages)
        else:
            # Single image file
            import cv2
            img = cv2.imread(str(source_path))
            if img is None:
                raise ValueError(f"Cannot read image: {source_path}")
            pages.append(self._assess_image(img, page_number=1))

        result = self._build_result(str(source_path), pages)

        if output_path is not None:
            self._save(result, Path(output_path))

        logger.info(
            "Assessment complete — enhancement needed: %s",
            result.any_enhancement_needed,
        )
        return result

    # ── Per-page assessment ───────────────────────────────────────────────────

    def _assess_image(self, image: np.ndarray, page_number: int) -> PageAssessment:
        """Compute quality metrics for a single page image."""
        gray = to_gray(image)
        h, w = gray.shape

        blur_score = laplacian_variance(gray)
        noise_score = estimate_noise(gray)
        contrast_score = rms_contrast(gray)
        skew_angle = estimate_skew_angle(gray)

        is_blurry = blur_score < self.blur_threshold
        is_noisy = noise_score > self.noise_threshold
        is_low_contrast = contrast_score < self.contrast_threshold
        needs_deskew = abs(skew_angle) > self.skew_threshold

        enhancement_needed = is_blurry or is_noisy or is_low_contrast or needs_deskew

        # Overall quality rating
        issues = sum([is_blurry, is_noisy, is_low_contrast, needs_deskew])
        if issues == 0:
            quality = QualityLevel.GOOD
        elif issues <= 2:
            quality = QualityLevel.ACCEPTABLE
        else:
            quality = QualityLevel.POOR

        return PageAssessment(
            page_number=page_number,
            dpi=float(self.render_dpi),
            dpi_ok=True,  # We rendered at self.render_dpi, so DPI is known
            blur_score=round(blur_score, 4),
            is_blurry=is_blurry,
            noise_score=round(noise_score, 6),
            is_noisy=is_noisy,
            contrast_score=round(contrast_score, 4),
            is_low_contrast=is_low_contrast,
            skew_angle=round(skew_angle, 4),
            needs_deskew=needs_deskew,
            quality=quality,
            enhancement_needed=enhancement_needed,
            width_px=w,
            height_px=h,
        )

    # ── Result aggregation ────────────────────────────────────────────────────

    def _build_result(self, source_path: str, pages: list[PageAssessment]) -> AssessmentResult:
        """Aggregate per-page results into a document-level AssessmentResult."""
        any_blurry = any(p.is_blurry for p in pages)
        any_noisy = any(p.is_noisy for p in pages)
        any_low_contrast = any(p.is_low_contrast for p in pages)
        any_needs_deskew = any(p.needs_deskew for p in pages)
        any_enhancement_needed = any(p.enhancement_needed for p in pages)

        recommended: list[str] = []
        if any_needs_deskew:
            recommended.append("deskew")
        if any_blurry:
            recommended.append("sharpen")
        if any_noisy:
            recommended.append("denoise")
        if any_low_contrast:
            recommended.append("contrast_enhancement")

        return AssessmentResult(
            source_path=source_path,
            page_count=len(pages),
            pages=pages,
            any_blurry=any_blurry,
            any_noisy=any_noisy,
            any_low_contrast=any_low_contrast,
            any_needs_deskew=any_needs_deskew,
            any_enhancement_needed=any_enhancement_needed,
            recommended_enhancements=recommended,
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    @staticmethod
    def _save(result: AssessmentResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(result.model_dump_json(indent=2))
        logger.info("Assessment saved to %s", path)

    @staticmethod
    def load(path: str | Path) -> AssessmentResult:
        """Load a previously saved assessment.json."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return AssessmentResult.model_validate(data)
