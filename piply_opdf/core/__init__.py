"""Core contracts and value types for piply_opdf.

Import from here rather than from submodules::

    from piply_opdf.core import BBox, PageContext, DetectedComponent
    from piply_opdf.core import Detector, DetectionStrategy, registry
"""

from piply_opdf.core.detector import (
    CompositeDetector,
    DetectionStrategy,
    Detector,
    DetectorRegistry,
    registry,
)
from piply_opdf.core.exceptions import (
    ConfigurationError,
    DetectionError,
    KnowledgeBaseError,
    OCREngineError,
    OCREngineUnavailableError,
    PiplyError,
    SourceNotFoundError,
    UnsupportedFormatError,
)
from piply_opdf.core.types import (
    BBox,
    ComponentType,
    DetectedComponent,
    PageContext,
    TextBlock,
)

__all__ = [
    # types
    "BBox", "TextBlock", "PageContext", "DetectedComponent", "ComponentType",
    # detection
    "Detector", "DetectionStrategy", "CompositeDetector", "DetectorRegistry", "registry",
    # exceptions
    "PiplyError", "ConfigurationError", "UnsupportedFormatError", "SourceNotFoundError",
    "DetectionError", "OCREngineError", "OCREngineUnavailableError", "KnowledgeBaseError",
]
