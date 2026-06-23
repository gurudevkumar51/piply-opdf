from typing import Any, Dict, Optional, Tuple
from piply_opdf.core.interfaces import IOCREngine, IFeatureExtractor, IKnowledgeMatcher
import logging
from piply_opdf.config import Config

logger = logging.getLogger(__name__)

# Global singleton for PaddleOCR to avoid reloading it constantly
_paddle_ocr_instance = None

def get_paddle_ocr():
    global _paddle_ocr_instance
    if _paddle_ocr_instance is None:
        try:
            from paddleocr import PaddleOCR
            lang = Config().get("ocr.lang", "en")
            _paddle_ocr_instance = PaddleOCR(use_angle_cls=True, lang=lang, enable_mkldnn=False)
        except ImportError:
            logger.warning("PaddleOCR is not installed.")
            return None
    return _paddle_ocr_instance

class PaddleOCREngine(IOCREngine):
    """
    Standard OCR fallback using PaddleOCR.
    Handles paddlex dict output and older nested list output.
    """
    
    def recognize_text(self, image_path: str) -> Tuple[str, float]:
        """
        Returns (text, confidence)
        """
        ocr = get_paddle_ocr()
        if not ocr:
            return ("", 0.0)
            
        paddle_text = ""
        paddle_conf = 0.0
        
        try:
            # Add padding to prevent edge characters from being truncated by PaddleOCR
            import cv2
            img_array = cv2.imread(image_path)
            if img_array is not None:
                # Upscale by 2x to help OCR det model capture boundaries better
                img_array = cv2.resize(img_array, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
                
                # Add a 30-pixel white border around the image (no distortion)
                img_target = cv2.copyMakeBorder(img_array, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])
            else:
                img_target = image_path

            # Use predict if available, else fallback to ocr
            result = ocr.predict(img_target) if hasattr(ocr, 'predict') else ocr.ocr(img_target)
            
            # Handle new dictionary format (paddlex/paddleocr >= v3)
            if result and isinstance(result[0], dict) and 'rec_texts' in result[0]:
                texts = result[0].get('rec_texts', [])
                confs = result[0].get('rec_scores', [])
                if texts:
                    paddle_text = " ".join(texts)
                if confs:
                    paddle_conf = sum(confs) / len(confs)
                    
            # Handle old list format (paddleocr < v3)
            elif result and result[0] and isinstance(result[0], list):
                texts = []
                confs = []
                for line in result[0]:
                    if isinstance(line, list) and len(line) >= 2 and isinstance(line[1], tuple):
                        texts.append(str(line[1][0]))
                        confs.append(float(line[1][1]))
                if texts:
                    paddle_text = " ".join(texts)
                if confs:
                    paddle_conf = sum(confs) / len(confs)
                    
        except Exception as parse_e:
            logger.error(f"Error parsing paddle result for {image_path}: {parse_e}")
            
        # Normalize confidence if PaddleOCR returned it as 0-100 instead of 0.0-1.0
        if paddle_conf > 1.0:
            paddle_conf /= 100.0
            
        return (paddle_text, paddle_conf)

class SmartOCREngine:
    """
    Orchestrator for the 5-Layer Knowledge Strategy for text extraction.
    Currently implements:
    Level 1: Exact Match (via IKnowledgeMatcher)
    Level 4: Raw OCR (via PaddleOCREngine)
    """
    def __init__(self, feature_extractor: IFeatureExtractor, knowledge_matcher: IKnowledgeMatcher, fallback_ocr: IOCREngine):
        self.feature_extractor = feature_extractor
        self.knowledge_matcher = knowledge_matcher
        self.fallback_ocr = fallback_ocr
        
    def extract_text(self, image_path: str) -> Dict[str, Any]:
        """
        Returns a dict: {"text": str, "confidence": float, "source": str}
        """
        # Step 1: Feature Extraction
        features = None
        try:
            features = self.feature_extractor.extract_features(image_path)
        except Exception as e:
            logger.warning(f"Feature extraction failed: {e}")
            
        # Step 2: Knowledge Match (Level 1)
        if features and "phash" in features:
            match = self.knowledge_matcher.find_exact_match(features["phash"])
            if match:
                # Expecting match to be a dict {"text": ..., "confidence": ...}
                return {
                    "text": match.get("text", ""),
                    "confidence": match.get("confidence", 100.0),
                    "source": match.get("source", "knowledge_base")
                }
                
        # Step 3: Raw OCR (Level 4)
        # Note: Level 2 (Similarity) and 3 (ML) will be inserted here in the future
        text, conf = self.fallback_ocr.recognize_text(image_path)
        
        return {
            "text": text,
            "confidence": conf,
            "source": "paddleocr"
        }
