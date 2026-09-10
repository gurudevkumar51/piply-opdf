"""
Tesseract — the alternative engine.

Kept behind the same interface as PaddleOCR so switching is a configuration
change. Two things are needed for it to run: the ``pytesseract`` wrapper *and*
the ``tesseract`` binary. Having only the wrapper is the common case and reads
as unavailable, because the wrapper alone cannot recognise anything.

**Confidence comes from Tesseract, not from a constant.** An earlier version of
this code returned a flat 0.85 whenever any text came back, which is a fabricated
number: it said "fairly confident" about a smudged word and a crisp one alike.
Tesseract reports a per-word confidence and that is what is used, so a poor
reading now looks poor.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from piply_opdf.config import Config
from piply_opdf.ocr.base import OCREngine, OCRResult, register

logger = logging.getLogger(__name__)

__all__ = ["TesseractEngine"]

#: Tesseract reports -1 for words it did not score. Those are dropped rather
#: than averaged in as zero, which would drag every result down.
_UNSCORED = -1


@register("tesseract")
class TesseractEngine(OCREngine):
    """Reads a crop with Tesseract."""

    def is_available(self) -> bool:
        try:
            import pytesseract

            # The wrapper importing proves nothing — the binary has to exist.
            pytesseract.get_tesseract_version()
        except Exception:
            return False
        return True

    def read(self, image: np.ndarray | str, *, salt: bool = False) -> OCRResult:
        if not self.is_available():
            return OCRResult.nothing(self.name, reason="tesseract binary not found")

        array = _as_array(image)
        if array is None:
            return OCRResult.nothing(self.name, reason="unreadable image")

        if salt:
            rng = np.random.default_rng()
            noise = rng.integers(0, 5, array.shape, dtype=np.uint8)
            array = np.clip(array.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        config = Config()
        options = config.get("ocr.tesseract.config", "--oem 3 --psm 6")
        language = config.get("ocr.tesseract.lang", "eng")

        try:
            import pytesseract

            data = pytesseract.image_to_data(
                array, lang=language, config=options,
                output_type=pytesseract.Output.DICT,
            )
        except Exception as exc:
            logger.error("Tesseract failed: %s", exc)
            return OCRResult.nothing(self.name, reason=f"{type(exc).__name__}: {exc}")

        words, confidences = [], []
        for word, raw_conf in zip(data.get("text", []), data.get("conf", [])):
            word = (word or "").strip()
            if not word:
                continue
            try:
                score = float(raw_conf)
            except (TypeError, ValueError):
                continue
            if score <= _UNSCORED:
                continue
            words.append(word)
            confidences.append(score / 100.0)

        if not words:
            return OCRResult.nothing(self.name, reason="no text found")

        return OCRResult(
            " ".join(words),
            float(sum(confidences) / len(confidences)),
            self.name,
            {"words": len(words), "config": options, "lang": language},
        )


def _as_array(image: np.ndarray | str) -> np.ndarray | None:
    if isinstance(image, np.ndarray):
        return image if image.size else None
    loaded = cv2.imread(str(image))
    return loaded if loaded is not None and loaded.size else None
