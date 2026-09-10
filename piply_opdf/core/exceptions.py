"""Typed exceptions for the piply_opdf package.

Every error raised deliberately by the package derives from :class:`PiplyError`,
so callers can catch the whole family without also swallowing bugs.
"""

from __future__ import annotations

__all__ = [
    "PiplyError",
    "ConfigurationError",
    "UnsupportedFormatError",
    "SourceNotFoundError",
    "DetectionError",
    "OCREngineError",
    "OCREngineUnavailableError",
    "KnowledgeBaseError",
]


class PiplyError(Exception):
    """Base class for all errors raised by piply_opdf."""


class ConfigurationError(PiplyError):
    """Configuration is missing, malformed, or has an out-of-range value."""


class UnsupportedFormatError(PiplyError):
    """The input file type is not supported by the pipeline."""


class SourceNotFoundError(PiplyError, FileNotFoundError):
    """The requested source document does not exist on disk."""


class DetectionError(PiplyError):
    """A detector failed irrecoverably on a page."""


class OCREngineError(PiplyError):
    """An OCR engine failed while recognising a region."""


class OCREngineUnavailableError(OCREngineError):
    """The requested OCR engine is not installed or could not be initialised."""


class KnowledgeBaseError(PiplyError):
    """The knowledge base could not be read or written."""
