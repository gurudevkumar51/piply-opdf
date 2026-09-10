"""
PP-DocLayout as the baseline layout detector.

The generic work — where is the title, the body text, the table, the figure,
the header and footer — is done better by a trained model than by rules, and
building those rules by hand is work that does not need doing. This adapter
puts the model behind the same contract as every other detector so its output
can be compared with, and combined with, Piply's own.

What it is good at, measured on the sample corpus
-------------------------------------------------

**It finds borderless tables.** On ``Sbizhub_C2219080509040.pdf`` — a seven
column bank statement with no ruled lines — the model reports two table regions
where this system's own rules report **zero**. That is the single biggest gap
in the existing detection, and the model closes it for free.

**It separates a document title from a section heading.** ``doc_title`` and
``paragraph_title`` are distinct classes, which is Rule 4's Title / Heading
distinction decided by training rather than by a font-size threshold.

What it does not do
-------------------

**It does not build cells.** A ``table`` is a region, not rows and columns. On
``sample.pdf`` the model reports one table where Piply builds 171 cells, 19 rows
and 9 columns. Assembling structure stays Piply's job, and so do key-value
pairs, nested regions and everything template-driven.

**It is an adapter, not a dependency.** Every entry point answers honestly when
PaddleOCR is absent, and the package keeps working on rules alone.

A note on oneDNN
----------------

The model is built with ``enable_mkldnn=False``. With oneDNN enabled, inference
fails outright on this platform::

    NotImplementedError: ConvertPirAttribute2RuntimeAttribute not support
    [pir::ArrayAttribute<pir::DoubleAttribute>]

This is not a tuning preference — it is the difference between running and not.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import numpy as np

from piply_opdf.baseline.labels import to_component_type
from piply_opdf.core.types import BBox, DetectedComponent, PageContext

logger = logging.getLogger(__name__)

__all__ = ["PaddleLayoutBaseline", "is_available"]

#: Regions below this score are dropped. The model reports low-confidence
#: guesses freely, and a region nobody believes is noise in the fusion step.
#: Left low on purpose: a borderless table on `Sbizhub` scores 0.55, and losing
#: that would give up the main reason for using the model at all.
DEFAULT_MIN_SCORE = 0.35

_model: Any = None
_load_failed = False


def is_available() -> bool:
    """Whether the baseline model can run. Never raises."""
    try:
        from paddleocr import LayoutDetection  # noqa: F401
    except Exception:
        return False
    return True


def _layout_model():
    """The shared model, or None when it cannot be built."""
    global _model, _load_failed
    if _model is not None or _load_failed:
        return _model
    try:
        from paddleocr import LayoutDetection

        # See the module docstring: oneDNN breaks inference on this platform.
        _model = LayoutDetection(enable_mkldnn=False)
    except Exception as exc:
        logger.warning("Baseline layout model could not be loaded: %s", exc)
        _load_failed = True
        _model = None
    return _model


class PaddleLayoutBaseline:
    """Runs PP-DocLayout over a page and returns ordinary components."""

    name = "paddle-layout"

    def __init__(self, *, min_score: float = DEFAULT_MIN_SCORE) -> None:
        self.min_score = min_score

    def is_applicable(self, page: PageContext) -> bool:
        return page.image is not None and page.image.size > 0 and is_available()

    def detect(self, page: PageContext) -> list[DetectedComponent]:
        """Regions the model found, as components.

        Returns an empty list when the model is unavailable — the caller falls
        back to Piply's own detectors, which is the whole point of the adapter.
        """
        model = _layout_model()
        if model is None or page.image is None or page.image.size == 0:
            return []

        started = time.time()
        try:
            raw = model.predict(page.image)
        except Exception as exc:
            logger.error("Baseline layout detection failed: %s", exc)
            return []
        elapsed = time.time() - started

        components: list[DetectedComponent] = []
        counters: dict[str, int] = {}

        for box in _boxes(raw):
            label = str(box.get("label", "")).strip().lower()
            score = float(box.get("score", 0.0))
            if score < self.min_score:
                continue

            bbox = _to_bbox(box.get("coordinate"), page)
            if bbox is None:
                continue

            component_type = to_component_type(label)
            index = counters.get(component_type, 0) + 1
            counters[component_type] = index

            components.append(
                DetectedComponent(
                    id=f"baseline_{component_type.lower()}_{page.page_number:03d}_{index:03d}",
                    type=component_type,
                    page=page.page_number,
                    bbox=bbox,
                    text="",
                    confidence=score,
                    index=index,
                    metadata={
                        "detector": self.name,
                        # The model's own word for it, kept so a mapping
                        # decision can be revisited without re-running.
                        "baseline_label": label,
                        "model_confidence": round(score, 4),
                        "needs_ocr": True,
                    },
                )
            )

        logger.info(
            "Baseline layout: page %d, %d regions in %.1fs",
            page.page_number, len(components), elapsed,
        )
        return components


def _boxes(raw: Any) -> list[dict]:
    """Pull the box list out of whatever the predictor returned."""
    found: list[dict] = []
    for item in raw or []:
        boxes = item.get("boxes", []) if isinstance(item, dict) else getattr(item, "boxes", [])
        found.extend(b for b in boxes if isinstance(b, dict))
    return found


def _to_bbox(coordinate: Any, page: PageContext) -> BBox | None:
    """``[x0, y0, x1, y1]`` in page pixels, clipped to the page."""
    if coordinate is None or len(coordinate) != 4:
        return None
    try:
        x0, y0, x1, y1 = (float(v) for v in coordinate)
    except (TypeError, ValueError):
        return None

    x0, x1 = sorted((max(0.0, x0), min(float(page.width), x1)))
    y0, y1 = sorted((max(0.0, y0), min(float(page.height), y1)))
    if x1 - x0 < 1 or y1 - y0 < 1:
        return None
    return BBox(int(x0), int(y0), int(x1 - x0), int(y1 - y0))
