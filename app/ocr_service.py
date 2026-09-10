from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os

from piply_opdf.core.interfaces import IKnowledgeMatcher
from piply_opdf.ml.pipeline import PipelineOrchestrator
from piply_opdf.modules.feature_extractor import DefaultFeatureExtractor
from piply_opdf.ocr import read_text

from . import models


class OCRResult(BaseModel):
    text: str
    confidence: float
    source: str

class MLPipelineMatcher(IKnowledgeMatcher):
    """
    Bridges the core SmartOCREngine with our 7-Level Pipeline Orchestrator.
    """
    def __init__(self, db: Session):
        self.orchestrator = PipelineOrchestrator()
        
    def find_exact_match(self, feature_hash: str) -> Optional[Dict[str, Any]]:
        # The core library only passes feature_hash here. We need the full features.
        # But wait! SmartOCREngine needs to be bypassed if we want to pass full features.
        pass

# Global instances for the stateless core engines to avoid recreation overhead
_feature_extractor = DefaultFeatureExtractor()

# Engine selection lives in the package, not here: piply_opdf.ocr holds the
# registry, reads `ocr.engine` from configuration, and falls back when the
# primary cannot run. The application only translates its own stored names.
#
# "paddle" is the name already written into existing `documents.ocr_engine`
# rows, so it is kept as an alias rather than migrated.
_ENGINE_ALIASES = {
    "paddle": "paddleocr",
    "paddleocr": "paddleocr",
    "tesseract": "tesseract",
}


def resolve_engine_name(engine_name: str | None) -> str | None:
    """Translate a stored engine name into a registry name."""
    if not engine_name:
        return None
    return _ENGINE_ALIASES.get(engine_name.lower(), engine_name)

def extract_cell_text(image_path: str, db: Session, bypass_kb: bool = False, salt: bool = False, engine_name: str = "paddle") -> OCRResult:
    """
    Extracts text using the 7-Level Pipeline, falling back to the selected OCR engine.
    """
    if not os.path.exists(image_path):
        return OCRResult(text="", confidence=0.0, source="not_found")
        
    # 1. Feature Extraction
    try:
        features = _feature_extractor.extract_features(image_path)
    except Exception as e:
        features = {}
        
    orchestrator = PipelineOrchestrator()
    if not bypass_kb:
        match = orchestrator.find_match(image_path, features)
        
        if match:
            return OCRResult(
                text=match.get("text", ""),
                confidence=match.get("confidence", 1.0),
                source=match.get("source", "ml_pipeline")
            )
        
    # Level 6: the configured OCR engine.
    reading = read_text(image_path, engine=resolve_engine_name(engine_name), salt=salt)

    return OCRResult(
        text=reading.text,
        confidence=reading.confidence,
        # The engine that actually read it, which is not always the one asked
        # for — the package falls back when the primary cannot run.
        source=reading.engine,
    )
