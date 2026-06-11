"""
piply-opdf — OCR + PDF Document Understanding Framework
========================================================

A production-grade, lightweight, self-learning platform for:
- Document quality assessment
- Selective image enhancement
- Layout detection and extraction
- Region-level OCR
- Confidence analysis and doubt detection
- Human feedback learning
- Document rebuilding

Quick start
-----------
>>> from piply_opdf import Document
>>> doc = Document("invoice.pdf")
>>> doc.assess()
>>> doc.enhance()
>>> doc.detect_layout()
>>> doc.extract_layouts()
>>> doc.ocr()
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("piply-opdf")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

__author__ = "Piply Team"
__all__ = ["Document"]

from piply_opdf.document import Document  # noqa: E402

__all__ = ["Document", "__version__"]
