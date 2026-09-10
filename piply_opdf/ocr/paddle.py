"""
PaddleOCR — the primary engine.

The output parsing here is the interesting part. PaddleOCR has shipped three
different result shapes across versions, and a crop can come back in any of
them depending on which call path was taken:

1. ``[('text', 0.99)]`` or ``[[('text', 0.99)]]`` — recognition only, no
   detection, which is what a pre-cropped cell uses.
2. ``[{'rec_texts': [...], 'rec_scores': [...], 'dt_polys': [...]}]`` — the
   dictionary form used from version 3.
3. ``[[[box, ('text', 0.99)], ...]]`` — the older nested list with boxes.

All three are handled, because which one appears depends on the installed
version and the call, and a pipeline that only understood one would silently
read nothing on the others.

Two behaviours worth knowing about
----------------------------------

**A white border is added before reading.** PaddleOCR's detection model clips
glyphs that touch the edge of a crop, and a table cell is by definition a tight
crop. Padding costs nothing and recovers the first and last characters.

**A crop whose ink touches its own border is penalised.** If the text runs into
the edge of the region that was cut, part of it was lost before the engine ever
saw it, so the confidence is halved. The reading is kept — it is still real
text — but it is no longer treated as reliable.

This is measured on the crop itself, **not** on the detected boxes. Measured:
PaddleOCR's boxes routinely extend 11-15 px into the padding, because the
detection model adds its own margin around text. Testing the boxes against the
border therefore fired on every crop and halved every confidence, which made the
penalty meaningless.
"""

from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

from piply_opdf.config import Config
from piply_opdf.ocr.base import OCREngine, OCRResult, register

logger = logging.getLogger(__name__)

__all__ = ["PaddleEngine"]

#: Padding added around a crop so edge glyphs are not clipped by detection.
_BORDER = 30

#: Confidence multiplier when the crop's own ink reaches its border — content
#: was cut off before the engine saw it.
_EDGE_PENALTY = 0.5

#: Below this grey level a pixel counts as ink.
_INK_LEVEL = 200

#: Loading the model is slow, so one instance is shared for the process.
_instance: Any = None
_load_failed = False


def _paddle():
    """The shared PaddleOCR instance, or None when it cannot be built."""
    global _instance, _load_failed
    if _instance is not None or _load_failed:
        return _instance
    try:
        from paddleocr import PaddleOCR

        config = Config()
        _instance = PaddleOCR(
            lang=config.get("ocr.lang", "en"),
            use_doc_orientation_classify=False,
            use_textline_orientation=False,
            enable_mkldnn=False,
        )
    except Exception as exc:
        # Missing library, missing weights, or an incompatible version. All are
        # "unavailable" rather than errors — see OCREngine.is_available.
        logger.warning("PaddleOCR could not be loaded: %s", exc)
        _load_failed = True
        _instance = None
    return _instance


@register("paddleocr")
class PaddleEngine(OCREngine):
    """Reads a crop with PaddleOCR."""

    def is_available(self) -> bool:
        try:
            import paddleocr  # noqa: F401
        except Exception:
            return False
        return True

    def read(self, image: np.ndarray | str, *, salt: bool = False) -> OCRResult:
        ocr = _paddle()
        if ocr is None:
            return OCRResult.nothing(self.name, reason="engine unavailable")

        array = _as_array(image)
        if array is None:
            return OCRResult.nothing(self.name, reason="unreadable image")

        height, width = array.shape[:2]

        # Padding helps detection keep edge glyphs. Skipped for a salted read,
        # which exists to perturb the input rather than help it.
        target: Any = array
        if not salt:
            target = cv2.copyMakeBorder(
                array, _BORDER, _BORDER, _BORDER, _BORDER,
                cv2.BORDER_CONSTANT, value=[255, 255, 255],
            )

        try:
            # Full detection, deliberately. PaddleOCR 3.x removed `det=False`,
            # and a recognition-only path via `TextRecognition` was measured
            # against this one on eight realistic crops — amounts, identifiers,
            # labels, dates. Both scored 7/8, failing on the same case
            # ("23-Oct-2025" read as "23-0ct-2025"). Equal accuracy, so the
            # simpler single path wins.
            raw = ocr.predict(target)
        except Exception as exc:
            logger.error("PaddleOCR failed: %s", exc)
            return OCRResult.nothing(self.name, reason=f"{type(exc).__name__}: {exc}")

        text, confidence, _boxes = _parse(raw)

        evidence: dict[str, Any] = {"shape": "none" if not raw else "parsed"}
        if confidence > 1.0:                        # some versions report percent
            confidence /= 100.0

        if text and _ink_touches_border(array):
            confidence *= _EDGE_PENALTY
            evidence["edge_penalty"] = "ink reaches the crop border"

        return OCRResult(text, float(confidence), self.name, evidence)


def _as_array(image: np.ndarray | str) -> np.ndarray | None:
    if isinstance(image, np.ndarray):
        return image if image.size else None
    loaded = cv2.imread(str(image))
    return loaded if loaded is not None and loaded.size else None


def _ink_touches_border(crop: np.ndarray) -> bool:
    """True when the crop has ink in its outermost rows or columns.

    A direct sign that the region was cut through its content: whatever ran off
    the edge never reached the engine, so the reading is incomplete however
    confident the engine sounds.
    """
    if crop is None or crop.size == 0:
        return False

    grey = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    ink = grey < _INK_LEVEL
    if ink.shape[0] < 3 or ink.shape[1] < 3:
        return False

    return bool(
        ink[0, :].any() or ink[-1, :].any() or ink[:, 0].any() or ink[:, -1].any()
    )


def _parse(raw: Any) -> tuple[str, float, list]:
    """Pull text, mean confidence and boxes out of any PaddleOCR result shape."""
    if not raw:
        return "", 0.0, []

    first = raw[0]

    # 1) recognition only: [('text', 0.99)] or [[('text', 0.99)]]
    if isinstance(first, tuple) or (
        isinstance(first, list) and first and isinstance(first[0], tuple)
    ):
        items = first if isinstance(first, list) else raw
        texts = [str(i[0]) for i in items if isinstance(i, tuple) and len(i) == 2]
        confs = [float(i[1]) for i in items if isinstance(i, tuple) and len(i) == 2]
        return " ".join(texts), _mean(confs), []

    # 2) dictionary form, PaddleOCR v3 and later
    if isinstance(first, dict) and "rec_texts" in first:
        texts = list(first.get("rec_texts", []))
        confs = list(first.get("rec_scores", []))
        boxes = list(first.get("dt_polys", []))
        if boxes and len(boxes) == len(texts):
            texts, confs = _in_reading_order(boxes, texts, confs)
        return " ".join(str(t) for t in texts), _mean(confs), boxes

    # 3) older nested list: [[box, ('text', 0.99)], ...]
    if isinstance(first, list):
        lines = sorted(first, key=_line_position)
        texts, confs, boxes = [], [], []
        for line in lines:
            if isinstance(line, list) and len(line) >= 2 and isinstance(line[1], tuple):
                boxes.append(line[0])
                texts.append(str(line[1][0]))
                confs.append(float(line[1][1]))
        return " ".join(texts), _mean(confs), boxes

    return "", 0.0, []


def _in_reading_order(boxes, texts, confs):
    """Top to bottom, then left to right.

    Rows are bucketed at 30 px so words on one line stay together instead of
    being ordered by a few pixels of vertical jitter.
    """
    combined = sorted(
        zip(boxes, texts, confs), key=lambda item: (round(item[0][0][1] / 30.0), item[0][0][0])
    )
    return [c[1] for c in combined], [c[2] for c in combined]


def _line_position(line) -> tuple[float, float]:
    if isinstance(line, list) and line and isinstance(line[0], list) and line[0]:
        return round(line[0][0][1] / 30.0), line[0][0][0]
    return 0.0, 0.0


def _mean(values) -> float:
    return float(sum(values) / len(values)) if values else 0.0
