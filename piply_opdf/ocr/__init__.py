"""
OCR, configurable.

PaddleOCR is the primary engine. Others sit behind the same interface so a
future switch is a configuration change, not a code change:

.. code-block:: yaml

    ocr:
      engine: paddleocr          # primary
      fallback_engine: tesseract # used only when the primary cannot run

.. code-block:: python

    from piply_opdf.ocr import read_text

    result = read_text(cell_image)
    result.text, result.confidence, result.engine

Fallback is for *unavailability*, not for disagreement
------------------------------------------------------

The fallback engine runs when the primary **cannot run at all** — its library is
missing, or its model will not load. It does **not** run because the primary
returned a poor result.

That distinction is deliberate. Trying a second engine whenever the first is
unsure doubles the slowest stage in the pipeline for the pages that need it
most, and quietly turns "two independent readings agreed" into "we kept asking
until we liked the answer". Cross-checking two engines to *earn* confidence is a
separate, deliberate call — :func:`read_with_agreement` — used only where it
pays.
"""

from __future__ import annotations

import logging

import numpy as np

from piply_opdf.config import Config
from piply_opdf.ocr.base import (
    OCREngine,
    OCRResult,
    available_engines,
    create_engine,
    register,
    registered_engines,
)

# Importing these registers them. Order does not matter; configuration decides.
from piply_opdf.ocr import paddle as _paddle  # noqa: F401
from piply_opdf.ocr import tesseract as _tesseract  # noqa: F401

logger = logging.getLogger(__name__)

__all__ = [
    "OCRResult",
    "OCREngine",
    "register",
    "registered_engines",
    "available_engines",
    "create_engine",
    "resolve_engine",
    "read_text",
    "read_with_agreement",
    "DEFAULT_ENGINE",
]

#: What is used when configuration says nothing.
DEFAULT_ENGINE = "paddleocr"


def resolve_engine(name: str | None = None) -> OCREngine | None:
    """The engine to use, honouring configuration and falling back if needed.

    Returns ``None`` when nothing can run, so a caller can tell "no text on this
    page" from "no OCR installed" — see the note in
    :mod:`piply_opdf.ocr.base`.
    """
    config = Config()
    wanted = name or config.get("ocr.engine", DEFAULT_ENGINE)

    engine = _try(wanted)
    if engine is not None:
        return engine

    fallback = config.get("ocr.fallback_engine", None)
    if fallback and fallback != wanted:
        engine = _try(fallback)
        if engine is not None:
            logger.warning(
                "OCR engine %r is unavailable; using fallback %r", wanted, fallback
            )
            return engine

    logger.error(
        "No OCR engine available. Wanted %r, fallback %r. Registered: %s",
        wanted, fallback, ", ".join(registered_engines()),
    )
    return None


def _try(name: str) -> OCREngine | None:
    try:
        engine = create_engine(name)
    except KeyError as exc:
        logger.error("%s", exc)
        return None
    return engine if engine.is_available() else None


def read_text(
    image: np.ndarray | str,
    *,
    engine: str | None = None,
    salt: bool = False,
) -> OCRResult:
    """Read *image* with the configured engine.

    Never raises for a missing engine: an unavailable one gives an empty result
    carrying the reason, so the caller can record *why* nothing was read.
    """
    selected = resolve_engine(engine)
    if selected is None:
        return OCRResult.nothing(reason="no OCR engine available")
    return selected.read(image, salt=salt)


def read_with_agreement(
    image: np.ndarray | str,
    *,
    primary: str | None = None,
    secondary: str | None = None,
) -> tuple[OCRResult, OCRResult | None, bool]:
    """Read with two engines and report whether they agree.

    Returns ``(primary_result, secondary_result, agreed)``. The second engine is
    skipped — and ``None`` returned for it — when it is unavailable or is the
    same engine.

    **Use this sparingly.** Two independent readings agreeing is strong evidence
    and is worth having where it matters: a value that failed a field
    constraint, or a high-stakes field such as an amount or an identifier.
    Running it on every region doubles the slowest stage of the pipeline for
    content that was never in doubt.
    """
    first = read_text(image, engine=primary)

    config = Config()
    other = secondary or config.get("ocr.fallback_engine", None)
    if not other or other == first.engine:
        return first, None, False

    engine = _try(other)
    if engine is None:
        return first, None, False

    second = engine.read(image)
    agreed = _normalise(first.text) == _normalise(second.text) and not first.is_empty
    return first, second, agreed


def _normalise(text: str) -> str:
    """Compare readings without punishing spacing differences."""
    return " ".join(text.split()).casefold()
