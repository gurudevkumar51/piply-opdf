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

class SqlAlchemyKnowledgeMatcher(IKnowledgeMatcher):
    """
    Implements IKnowledgeMatcher by querying the SQLAlchemy database 
    for exact pHash matches (Level 1 Learning).
    """
    def __init__(self, db: Session):
        self.db = db
        
    def find_exact_match(self, feature_hash: str) -> Optional[Dict[str, Any]]:
        kb_entry = self.db.query(models.OCRKnowledgeBase).filter(
            models.OCRKnowledgeBase.image_hash == feature_hash
        ).first()
        
        if kb_entry and kb_entry.text_value is not None:
            return {
                "text": kb_entry.text_value,
                "confidence": kb_entry.confidence,
                "source": kb_entry.source
            }
        return None

# Global instances for the stateless core engines to avoid recreation overhead
_feature_extractor = DefaultFeatureExtractor()
_paddle_engine = PaddleOCREngine()

def extract_cell_text(image_path: str, db: Session) -> OCRResult:
    """
    Extracts text from an image using the unified SmartOCREngine 
    from the piply_opdf core library.
    """
    if not os.path.exists(image_path):
        return OCRResult(text="", confidence=0.0, source="not_found")
        
    # Inject the session-dependent matcher
    db_matcher = SqlAlchemyKnowledgeMatcher(db)
    
    # Initialize the Smart Orchestrator
    orchestrator = SmartOCREngine(
        feature_extractor=_feature_extractor,
        knowledge_matcher=db_matcher,
        fallback_ocr=_paddle_engine
    )
    
    # Extract!
    result_dict = orchestrator.extract_text(image_path)
    
    return OCRResult(
        text=result_dict.get("text", ""),
        confidence=result_dict.get("confidence", 0.0),
        source=result_dict.get("source", "unknown")
    )
