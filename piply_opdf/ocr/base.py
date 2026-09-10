"""
The OCR contract, and the registry that makes engines swappable.

One engine is primary — PaddleOCR — and others exist behind the same interface
so a future switch is a configuration change rather than a code change. The
shape mirrors the detector and segmenter registries already in the package, so
there is one pattern to learn rather than three.

Adding an engine is a file and a decorator:

.. code-block:: python

    @register("myengine")
    class MyEngine(OCREngine):
        name = "myengine"

        def is_available(self) -> bool: ...
        def read(self, image, *, salt=False) -> OCRResult: ...

Nothing else changes. ``ocr.engine: myengine`` in the configuration selects it.

Availability is a **question, not a crash**
-------------------------------------------

An engine whose library is missing answers ``is_available() -> False`` rather
than raising on import or silently returning an empty string. That distinction
matters: "this page has no text" and "no OCR engine is installed" are different
facts, and a pipeline that confuses them produces empty documents that look
successful.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np

__all__ = [
    "OCRResult",
    "OCREngine",
    "register",
    "available_engines",
    "registered_engines",
    "create_engine",
]


@dataclass(frozen=True, slots=True)
class OCRResult:
    """What an engine read, and how much to believe it.

    ``engine`` and ``evidence`` are carried deliberately: a component records
    *who* read it and *why* it is trusted, never just a number. See the
    governing principle in ``docs/plan-templates.md``.
    """

    text: str
    confidence: float
    #: Which engine produced this. Never empty — "none" when nothing could run.
    engine: str = "none"
    #: Per-engine detail: word confidences, penalties applied, why it failed.
    evidence: dict[str, Any] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        return not self.text.strip()

    @classmethod
    def nothing(cls, engine: str = "none", **evidence: Any) -> "OCRResult":
        """No text, and a confidence of zero rather than a guess."""
        return cls("", 0.0, engine, dict(evidence))


class OCREngine(ABC):
    """Reads text from one image region."""

    #: Registry key. Also what appears in ``OCRResult.engine``.
    name: str = "unnamed"

    @abstractmethod
    def is_available(self) -> bool:
        """Whether this engine can actually run.

        Must be cheap and must not raise: a missing library is a ``False``,
        not an exception.
        """

    @abstractmethod
    def read(self, image: np.ndarray | str, *, salt: bool = False) -> OCRResult:
        """Read *image*, which may be an array or a path to one.

        *salt* asks for a slightly perturbed second reading, used to see whether
        a result is stable. An engine that cannot do this may ignore it.
        """

    def __repr__(self) -> str:                      # pragma: no cover - debug aid
        return f"<{type(self).__name__} name={self.name!r}>"


_ENGINES: dict[str, Callable[[], OCREngine]] = {}


def register(name: str) -> Callable[[type[OCREngine]], type[OCREngine]]:
    """Register an engine class under *name*."""

    def decorator(cls: type[OCREngine]) -> type[OCREngine]:
        _ENGINES[name] = cls
        cls.name = name
        return cls

    return decorator


def registered_engines() -> list[str]:
    """Every engine name known, whether or not its library is installed."""
    return sorted(_ENGINES)


def available_engines() -> list[str]:
    """Only the engines that could actually run right now."""
    ready = []
    for name in sorted(_ENGINES):
        try:
            if _ENGINES[name]().is_available():
                ready.append(name)
        except Exception:                           # a broken engine is not available
            continue
    return ready


def create_engine(name: str) -> OCREngine:
    """Build the engine registered under *name*.

    Raises :class:`KeyError` with the known names listed, because a typo in
    configuration should say what was expected rather than fail obscurely.
    """
    try:
        factory = _ENGINES[name]
    except KeyError:
        raise KeyError(
            f"No OCR engine named {name!r}. Known engines: {', '.join(registered_engines()) or 'none'}"
        ) from None
    return factory()
