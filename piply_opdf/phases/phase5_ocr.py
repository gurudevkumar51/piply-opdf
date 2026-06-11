"""
Phase 5 — OCR Engine
======================

Performs OCR on extracted layout regions — NOT on full pages.
Pluggable engine architecture with PaddleOCR as primary and Tesseract as fallback.

Public API
----------
>>> from piply_opdf.phases.phase5_ocr import OCRProcessor
>>> processor = OCRProcessor()
>>> result = processor.ocr_manifest(manifest, source_path="invoice.pdf")

CLI
---
    piply-opdf ocr invoice.pdf
"""

from __future__ import annotations

import abc
import json
import logging
import statistics
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from piply_opdf.config import Config, get_default_config
from piply_opdf.models.layout import LayoutManifest, LayoutRegion, RegionType
from piply_opdf.models.ocr_result import CharResult, OCRResult, RegionOCRResult, WordResult
from piply_opdf.utils.image import load_image

logger = logging.getLogger(__name__)


# ── OCR Engine ABC ────────────────────────────────────────────────────────────


class OCREngine(abc.ABC):
    """
    Abstract base class for OCR engines.

    Implement ``run(image)`` to add a new engine.
    """

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable engine name."""

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Return True when the engine is installed and ready."""

    @abc.abstractmethod
    def run(self, image: np.ndarray) -> list[WordResult]:
        """
        Run OCR on a single image array.

        Returns a list of WordResult objects with text and confidence.
        """


# ── PaddleOCR Engine ──────────────────────────────────────────────────────────


class PaddleOCREngine(OCREngine):
    """OCR engine backed by PaddleOCR (supports v2.x and v3.x APIs)."""

    def __init__(self, lang: str = "en", use_angle_cls: bool = True) -> None:
        self.lang = lang
        self.use_angle_cls = use_angle_cls
        self._ocr: Any = None

    @property
    def name(self) -> str:
        return "paddleocr"

    def is_available(self) -> bool:
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

    def _get_ocr(self) -> Any:
        if self._ocr is None:
            from paddleocr import PaddleOCR  # type: ignore[import]

            # PaddleOCR v3.x removed use_gpu; v2.x supported it.
            # Try v3.x style first (no use_gpu, CPU device implied),
            # then fall back to v2.x style.
            import inspect
            sig = inspect.signature(PaddleOCR.__init__)
            params = list(sig.parameters.keys())

            kwargs: dict[str, Any] = {
                "use_angle_cls": self.use_angle_cls,
                "lang": self.lang,
                "show_log": False,
            }
            # Only pass use_gpu when the constructor still accepts it (v2.x)
            if "use_gpu" in params:
                kwargs["use_gpu"] = False
            # v3.x uses 'device' parameter for CPU/GPU selection
            elif "device" in params:
                kwargs["device"] = "cpu"

            self._ocr = PaddleOCR(**kwargs)
        return self._ocr

    def run(self, image: np.ndarray) -> list[WordResult]:
        ocr = self._get_ocr()
        # PaddleOCR expects BGR (OpenCV default) or RGB
        results = ocr.ocr(image, cls=self.use_angle_cls)

        words: list[WordResult] = []
        if not results or results[0] is None:
            return words

        for line in results[0]:
            if line is None:
                continue
            bbox_pts, (text, conf) = line
            # Convert polygon bbox to AABB (x, y, x2, y2)
            xs = [int(p[0]) for p in bbox_pts]
            ys = [int(p[1]) for p in bbox_pts]
            bbox = (min(xs), min(ys), max(xs), max(ys))
            words.append(
                WordResult(
                    text=str(text),
                    confidence=float(conf),
                    bbox=bbox,
                )
            )
        return words


# ── Tesseract Engine ──────────────────────────────────────────────────────────


class TesseractEngine(OCREngine):
    """OCR engine backed by Tesseract via pytesseract."""

    def __init__(self, lang: str = "eng", config: str = "--oem 3 --psm 6") -> None:
        self.lang = lang
        self.tess_config = config

    @property
    def name(self) -> str:
        return "tesseract"

    def is_available(self) -> bool:
        try:
            import pytesseract  # noqa: F401
            pytesseract.get_tesseract_version()
            return True
        except Exception:
            return False

    def run(self, image: np.ndarray) -> list[WordResult]:
        import pytesseract  # type: ignore[import]
        from PIL import Image

        # Ensure grayscale or RGB for Tesseract
        if len(image.shape) == 3:
            rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
        else:
            pil_img = Image.fromarray(image)

        data = pytesseract.image_to_data(
            pil_img,
            lang=self.lang,
            config=self.tess_config,
            output_type=pytesseract.Output.DICT,
        )

        words: list[WordResult] = []
        n = len(data["text"])
        for i in range(n):
            text = str(data["text"][i]).strip()
            if not text:
                continue
            conf_raw = data["conf"][i]
            conf = max(0.0, float(conf_raw) / 100.0) if conf_raw != -1 else 0.0
            x, y, w, h = (
                int(data["left"][i]),
                int(data["top"][i]),
                int(data["width"][i]),
                int(data["height"][i]),
            )
            words.append(
                WordResult(
                    text=text,
                    confidence=conf,
                    bbox=(x, y, x + w, y + h),
                )
            )
        return words


# ── OCR Processor ─────────────────────────────────────────────────────────────


class OCRProcessor:
    """
    Applies OCR to extracted layout regions using a pluggable engine.

    Selects the engine based on config (paddleocr → tesseract fallback).
    """

    def __init__(self, config: Config | None = None) -> None:
        self.config = config or get_default_config()
        self.engine = self._build_engine()

    def _build_engine(self) -> OCREngine:
        """Instantiate the primary engine; fall back to secondary if unavailable."""
        cfg = self.config.section("ocr")
        primary_name = cfg.get("engine", "paddleocr")
        fallback_name = cfg.get("fallback_engine", "tesseract")
        lang = cfg.get("lang", "en")

        paddle_cfg = cfg.get("paddleocr") or {}
        tess_cfg = cfg.get("tesseract") or {}

        def _build(name: str) -> OCREngine | None:
            if name == "paddleocr":
                e: OCREngine = PaddleOCREngine(
                    lang=lang,
                    use_angle_cls=paddle_cfg.get("use_angle_cls", True),
                )
            elif name == "tesseract":
                e = TesseractEngine(
                    lang=tess_cfg.get("lang", "eng"),
                    config=tess_cfg.get("config", "--oem 3 --psm 6"),
                )
            else:
                logger.warning("Unknown engine name '%s'", name)
                return None
            return e if e.is_available() else None

        engine = _build(primary_name)
        if engine is None:
            logger.warning(
                "Primary OCR engine '%s' not available — trying fallback '%s'",
                primary_name,
                fallback_name,
            )
            engine = _build(fallback_name)

        if engine is None:
            raise RuntimeError(
                "No OCR engine available. Install paddleocr or pytesseract."
            )

        logger.info("OCR engine: %s", engine.name)
        return engine

    # ── Main entry point ──────────────────────────────────────────────────────

    def ocr_manifest(
        self,
        manifest: LayoutManifest,
        output_path: str | Path | None = None,
    ) -> OCRResult:
        """
        Run OCR on all regions described in a LayoutManifest.

        Parameters
        ----------
        manifest:
            Output from Phase 4 (LayoutExtractor.extract).
        output_path:
            If given, write ocr_result.json to this path.

        Returns
        -------
        OCRResult
        """
        logger.info(
            "Running OCR on %d regions using %s",
            len(manifest.regions),
            self.engine.name,
        )

        region_results: list[RegionOCRResult] = []
        for region in manifest.regions:
            region_result = self._ocr_region(region)
            region_results.append(region_result)
            # Also OCR children (cells)
            for child in region.children:
                child_result = self._ocr_region(child)
                region_results.append(child_result)

        result = self._build_result(manifest.source_path, region_results)

        if output_path is not None:
            self._save(result, Path(output_path))

        logger.info(
            "OCR complete — %d regions, mean confidence: %.3f",
            len(region_results),
            result.mean_confidence,
        )
        return result

    def ocr_image(
        self,
        image: np.ndarray,
        region_id: str = "region_001",
        region_type: str = "unknown",
        page_number: int = 1,
    ) -> RegionOCRResult:
        """OCR a single in-memory image and return a RegionOCRResult."""
        words = self.engine.run(image)
        return self._build_region_result(
            words=words,
            region_id=region_id,
            region_type=region_type,
            page_number=page_number,
        )

    # ── Per-region processing ─────────────────────────────────────────────────

    def _ocr_region(self, region: LayoutRegion) -> RegionOCRResult:
        """Load the region image and run OCR."""
        if region.image_path is None or not Path(region.image_path).exists():
            logger.warning("No image for region %s — returning empty result", region.region_id)
            return RegionOCRResult(
                region_id=region.region_id,
                region_type=region.type.value,
                page_number=region.page_number,
            )

        try:
            image = load_image(region.image_path)
            words = self.engine.run(image)
        except Exception as exc:
            logger.error("OCR failed for region %s: %s", region.region_id, exc)
            words = []

        result = self._build_region_result(
            words=words,
            region_id=region.region_id,
            region_type=region.type.value,
            page_number=region.page_number,
            source_image_path=region.image_path,
        )
        return result

    @staticmethod
    def _build_region_result(
        words: list[WordResult],
        region_id: str,
        region_type: str,
        page_number: int,
        source_image_path: str | None = None,
    ) -> RegionOCRResult:
        """Assemble a RegionOCRResult from a list of WordResult objects."""
        if not words:
            return RegionOCRResult(
                region_id=region_id,
                region_type=region_type,
                page_number=page_number,
                raw_text="",
                source_image_path=source_image_path,
            )

        raw_text = " ".join(w.text for w in words)
        confs = [w.confidence for w in words]
        word_conf = statistics.mean(confs) if confs else 0.0
        region_conf = word_conf  # Could be refined with spatial weighting

        return RegionOCRResult(
            region_id=region_id,
            region_type=region_type,
            page_number=page_number,
            raw_text=raw_text,
            words=words,
            word_confidence=round(word_conf, 4),
            region_confidence=round(region_conf, 4),
            source_image_path=source_image_path,
        )

    @staticmethod
    def _build_result(source_path: str, regions: list[RegionOCRResult]) -> OCRResult:
        """Aggregate region results into a document-level OCRResult."""
        total_words = sum(len(r.words) for r in regions)
        confs = [r.region_confidence for r in regions if r.words]
        mean_conf = statistics.mean(confs) if confs else 0.0
        return OCRResult(
            source_path=source_path,
            page_count=max((r.page_number for r in regions), default=0),
            engine_used="unknown",  # will be overridden by OCRProcessor
            regions=regions,
            total_words=total_words,
            mean_confidence=round(mean_conf, 4),
        )

    # ── Persistence ───────────────────────────────────────────────────────────

    @staticmethod
    def _save(result: OCRResult, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(result.model_dump_json(indent=2))
        logger.info("OCR result saved to %s", path)

    @staticmethod
    def load(path: str | Path) -> OCRResult:
        """Load a previously saved ocr_result.json."""
        path = Path(path)
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return OCRResult.model_validate(data)
