"""
Phase 2 — Document Enhancement Engine
=======================================

Applies selective enhancement based on Phase 1 assessment results.
Never enhances blindly — only applies operations that are needed.

Public API
----------
>>> from piply_opdf.phases.phase2_enhance import DocumentEnhancer
>>> enhancer = DocumentEnhancer()
>>> enhanced_pdf = enhancer.enhance("invoice.pdf", assessment=result)

CLI
---
    piply-opdf enhance invoice.pdf
"""

from __future__ import annotations

import logging
from pathlib import Path

import cv2
import numpy as np

from piply_opdf.config import Config, get_default_config
from piply_opdf.models.assessment import AssessmentResult, PageAssessment
from piply_opdf.utils.image import rotate_image, to_gray
from piply_opdf.utils.pdf import iter_pages, save_images_as_pdf

logger = logging.getLogger(__name__)


class DocumentEnhancer:
    """
    Applies selective image enhancements to a document.

    Only operations flagged as needed in the AssessmentResult are applied.
    When no AssessmentResult is provided, all auto-enabled operations run.

    Parameters
    ----------
    config:
        Optional Config object; defaults to the package default config.
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_default_config()
        cfg = self.config.section("enhancement")

        self.auto_deskew: bool = cfg.get("auto_deskew", True)
        self.auto_denoise: bool = cfg.get("auto_denoise", True)
        self.auto_sharpen: bool = cfg.get("auto_sharpen", True)
        self.clahe_clip_limit: float = cfg.get("clahe_clip_limit", 2.0)
        self.clahe_tile: tuple[int, int] = tuple(cfg.get("clahe_tile_grid_size", [8, 8]))  # type: ignore[assignment]
        self.border_kernel: int = cfg.get("border_kernel_size", 3)
        self.table_dilation_iter: int = cfg.get("table_border_dilation_iter", 2)
        self.output_quality: int = cfg.get("output_quality", 95)
        self.render_dpi: int = self.config.get("assessment.render_dpi", 300)

    # ── Main entry point ──────────────────────────────────────────────────────

    def enhance(
        self,
        source_path: str | Path,
        assessment: AssessmentResult | None = None,
        output_path: str | Path | None = None,
    ) -> Path:
        """
        Enhance all pages of a PDF and write an enhanced PDF.

        Parameters
        ----------
        source_path:
            Path to the original PDF or image.
        assessment:
            If supplied, only apply enhancements flagged as needed per-page.
            When *None*, all configured auto-enhancements are applied.
        output_path:
            Destination for the enhanced PDF.  Defaults to
            ``<source_stem>_enhanced.pdf`` in the same directory.

        Returns
        -------
        Path
            Absolute path to the written enhanced PDF.
        """
        source_path = Path(source_path)
        if output_path is None:
            output_path = source_path.parent / f"{source_path.stem}_enhanced.pdf"
        output_path = Path(output_path)

        logger.info("Enhancing document: %s", source_path.name)
        enhanced_pages: list[np.ndarray] = []

        for page_idx, img in iter_pages(source_path, dpi=self.render_dpi):
            page_assessment = None
            if assessment is not None and page_idx < len(assessment.pages):
                page_assessment = assessment.pages[page_idx]

            enhanced = self._enhance_page(img, page_assessment)
            enhanced_pages.append(enhanced)
            logger.debug("Page %d enhanced", page_idx + 1)

        result_path = save_images_as_pdf(enhanced_pages, output_path, dpi=self.render_dpi)
        logger.info("Enhanced PDF saved to %s", result_path)
        return result_path

    def enhance_image(
        self,
        image: np.ndarray,
        page_assessment: PageAssessment | None = None,
    ) -> np.ndarray:
        """
        Enhance a single OpenCV image array.

        Useful for integrating into custom pipelines.
        """
        return self._enhance_page(image, page_assessment)

    # ── Enhancement pipeline ──────────────────────────────────────────────────

    def _enhance_page(
        self,
        image: np.ndarray,
        assessment: PageAssessment | None,
    ) -> np.ndarray:
        """Apply the appropriate enhancement steps to one page image."""
        if assessment and getattr(assessment, "doc_type", "SCANNED") in ("DIGITAL", "HYBRID"):
            return image.copy()
            
        img = image.copy()

        # Determine which operations to apply
        do_deskew = self.auto_deskew and (assessment is None or assessment.needs_deskew)
        do_denoise = self.auto_denoise and (assessment is None or assessment.is_noisy)
        do_sharpen = self.auto_sharpen and (assessment is None or assessment.is_blurry)
        do_contrast = assessment is None or assessment.is_low_contrast

        # Apply in logical order: geometry → noise → contrast → sharpness
        if do_deskew:
            angle = assessment.skew_angle if assessment else 0.0
            if abs(angle) > 0.1:
                img = self.deskew(img, angle)
                logger.debug("Applied deskew: %.2f°", angle)

        if do_denoise:
            img = self.denoise(img)
            logger.debug("Applied denoise")

        if do_contrast:
            img = self.enhance_contrast(img)
            logger.debug("Applied contrast enhancement")

        if do_sharpen:
            img = self.sharpen(img)
            logger.debug("Applied sharpening")

        return img

    # ── Individual enhancement operations ─────────────────────────────────────

    @staticmethod
    def deskew(image: np.ndarray, angle: float) -> np.ndarray:
        """
        Correct rotational skew by rotating *image* by *angle* degrees.

        Uses white background fill and preserves the page frame — see
        :func:`piply_opdf.utils.image.rotate_image` for why expansion would
        break the ratio-based zones used during detection.
        """
        return rotate_image(image, angle, expand=False)

    @staticmethod
    def denoise(image: np.ndarray) -> np.ndarray:
        """
        Apply fast non-local means denoising.

        Works on colour and grayscale images.
        """
        if len(image.shape) == 2 or image.shape[2] == 1:
            return cv2.fastNlMeansDenoising(image, h=10)
        return cv2.fastNlMeansDenoisingColored(image, h=10, hColor=10)

    def enhance_contrast(self, image: np.ndarray) -> np.ndarray:
        """
        Apply CLAHE (Contrast Limited Adaptive Histogram Equalisation).

        Works in LAB colour space to avoid hue shifts.
        """
        clahe = cv2.createCLAHE(
            clipLimit=self.clahe_clip_limit,
            tileGridSize=self.clahe_tile,
        )

        if len(image.shape) == 2:
            return clahe.apply(image)

        # Convert to LAB, apply CLAHE to L channel only
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        l_channel, a_channel, b_channel = cv2.split(lab)
        l_enhanced = clahe.apply(l_channel)
        lab_enhanced = cv2.merge([l_enhanced, a_channel, b_channel])
        return cv2.cvtColor(lab_enhanced, cv2.COLOR_LAB2BGR)

    @staticmethod
    def sharpen(image: np.ndarray) -> np.ndarray:
        """
        Apply unsharp masking to improve sharpness.

        Amount/radius tuned for typical document scans.
        """
        blurred = cv2.GaussianBlur(image, (0, 0), sigmaX=3)
        # amount = 1.5 means moderate sharpening
        sharpened = cv2.addWeighted(image, 1.5, blurred, -0.5, 0)
        return sharpened

    def enhance_borders(self, image: np.ndarray) -> np.ndarray:
        """
        Strengthen faint borders using morphological close operation.

        Useful for forms and tables with light ruling.
        """
        kernel = np.ones(
            (self.border_kernel, self.border_kernel), dtype=np.uint8
        )
        gray = to_gray(image)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        closed = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)
        return cv2.bitwise_not(closed)

    def reconstruct_table_borders(self, image: np.ndarray) -> np.ndarray:
        """
        Reconstruct missing table borders using dilation + contour overlay.

        Returns the image with strengthened table lines drawn on top.
        """
        gray = to_gray(image)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Horizontal kernel
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        h_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, h_kernel)
        h_lines = cv2.dilate(h_lines, h_kernel, iterations=self.table_dilation_iter)

        # Vertical kernel
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        v_lines = cv2.morphologyEx(binary, cv2.MORPH_OPEN, v_kernel)
        v_lines = cv2.dilate(v_lines, v_kernel, iterations=self.table_dilation_iter)

        # Combine into a grid mask
        grid = cv2.add(h_lines, v_lines)

        # Overlay dark lines on original image
        result = image.copy()
        if len(result.shape) == 3:
            result[grid > 0] = (0, 0, 0)
        else:
            result[grid > 0] = 0

        return result
