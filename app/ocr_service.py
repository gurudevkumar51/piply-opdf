from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from pydantic import BaseModel
import os

from piply_opdf.core.interfaces import IKnowledgeMatcher
from piply_opdf.modules.feature_extractor import DefaultFeatureExtractor
from piply_opdf.modules.ocr_engine import PaddleOCREngine, SmartOCREngine
from . import models

class OCRResult(BaseModel):
    text: str
    confidence: float
    source: str

from piply_opdf.core.interfaces import IKnowledgeMatcher
from piply_opdf.modules.feature_extractor import DefaultFeatureExtractor
from piply_opdf.modules.ocr_engine import PaddleOCREngine, SmartOCREngine
from . import models
from piply_opdf.ml.pipeline import PipelineOrchestrator

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

_engines = {
    "paddle": PaddleOCREngine(),
    # Tesseract engine would be instantiated here, assuming we have one in piply_opdf
    # "tesseract": TesseractOCREngine() if we have it, else fallback to paddle for now
}

# If a Tesseract engine exists in the module, let's try to import it
try:
    from piply_opdf.modules.ocr_engine import TesseractOCREngine
    _engines["tesseract"] = TesseractOCREngine()
except ImportError:
    pass

def get_engine(engine_name: str):
    if engine_name in _engines:
        return _engines[engine_name]
    return _engines.get("paddle")

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
        
    # Directly Fallback to Level 6: Selected Engine
    engine = get_engine(engine_name)
    try:
        text, conf = engine.recognize_text(image_path, salt=salt)
    except TypeError:
        # Some engines might not support salt parameter
        text, conf = engine.recognize_text(image_path)
    
    return OCRResult(
        text=text,
        confidence=conf,
        source=engine_name or "paddle"
    )
