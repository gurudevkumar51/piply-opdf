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
            # PaddleX v3 uses use_textline_orientation instead of use_angle_cls
            _paddle_ocr_instance = PaddleOCR(use_doc_orientation_classify=False, use_textline_orientation=False, lang=lang, enable_mkldnn=False)
        except ImportError:
            logger.warning("PaddleOCR is not installed.")
            return None
    return _paddle_ocr_instance

class PaddleOCREngine(IOCREngine):
    """
    Standard OCR fallback using PaddleOCR.
    Handles paddlex dict output and older nested list output.
    """
    
    def recognize_text(self, image_path: str, salt: bool = False) -> Tuple[str, float]:
        """
        Recognize text using PaddleOCR.
        Returns (text, confidence)
        """
        ocr = get_paddle_ocr()
        if not ocr:
            return "", 0.0
            
        paddle_text = ""
        paddle_conf = 0.0
        edge_penalty = False
        
        try:
            import cv2
            import numpy as np
            
            img_array = cv2.imread(image_path)
            if img_array is None:
                return "", 0.0
                
            img_h, img_w = img_array.shape[:2]
            
            if not salt:
                # Add massive white border to help paddleocr's detection model avoid cropping edges
                # Do NOT blur the image, it degrades small digits.
                img_target = cv2.copyMakeBorder(img_array, 30, 30, 30, 30, cv2.BORDER_CONSTANT, value=[255, 255, 255])
            else:
                img_target = image_path

            # Force det=False for pre-cropped cells to drastically improve accuracy on single numbers and short text.
            try:
                # CRITICAL: cls=False prevents PaddleOCR from incorrectly guessing text is upside-down and flipping 6 into 9.
                result = ocr.ocr(img_target, det=False, cls=False)
            except TypeError:
                # If ocr() doesn't accept det=False (very rare), just call predict
                result = ocr.predict(img_target)
            
            def check_edge_penalty(boxes):
                if img_w == 0 or img_h == 0: return False
                for box in boxes:
                    for pt in box:
                        if pt[0] <= 32 or pt[0] >= 30 + img_w - 2: return True
                        if pt[1] <= 32 or pt[1] >= 30 + img_h - 2: return True
                return False

            # Handle PaddleOCR output formats
            if not result:
                pass
            # 1) det=False format: [('text', 0.99)] or [[('text', 0.99)]]
            elif isinstance(result, list) and len(result) > 0 and (isinstance(result[0], tuple) or (isinstance(result[0], list) and len(result[0]) > 0 and isinstance(result[0][0], tuple))):
                texts = []
                confs = []
                # It might be nested depending on the version
                flat_res = result[0] if isinstance(result[0], list) else result
                for item in flat_res:
                    if isinstance(item, tuple) and len(item) == 2:
                        texts.append(str(item[0]))
                        confs.append(float(item[1]))
                if texts:
                    paddle_text = " ".join(texts)
                if confs:
                    paddle_conf = sum(confs) / len(confs)
            
            # 2) dictionary format (PaddleOCR >= v3 with layout/table or specific modes)
            elif isinstance(result[0], dict) and 'rec_texts' in result[0]:
                texts = result[0].get('rec_texts', [])
                confs = result[0].get('rec_scores', [])
                boxes = result[0].get('dt_polys', [])
                
                if boxes and len(boxes) == len(texts):
                    edge_penalty = check_edge_penalty(boxes)
                    combined = sorted(zip(boxes, texts, confs), key=lambda x: (round(x[0][0][1] / 30.0), x[0][0][0]))
                    texts = [c[1] for c in combined]
                    confs = [c[2] for c in combined]
                
                if texts:
                    paddle_text = " ".join(texts)
                if confs:
                    paddle_conf = sum(confs) / len(confs)
                    
            # 3) Handle old list format with boxes: [[box, (text, conf)], ...]
            elif isinstance(result[0], list):
                # result[0] is a list of lines. Each line: [box, (text, conf)]
                def get_sort_key(line):
                    if isinstance(line, list) and len(line) > 0 and isinstance(line[0], list) and len(line[0]) > 0:
                        return (round(line[0][0][1] / 30.0), line[0][0][0])
                    return (0, 0)
                sorted_lines = sorted(result[0], key=get_sort_key)
                
                texts = []
                confs = []
                boxes = []
                for line in sorted_lines:
                    if isinstance(line, list) and len(line) >= 2 and isinstance(line[1], tuple):
                        boxes.append(line[0])
                        texts.append(str(line[1][0]))
                        confs.append(float(line[1][1]))
                if texts:
                    edge_penalty = check_edge_penalty(boxes)
                    paddle_text = " ".join(texts)
                if confs:
                    paddle_conf = sum(confs) / len(confs)
                    
        except Exception as parse_e:
            logger.error(f"Error parsing paddle result for {image_path}: {parse_e}")
            
        if paddle_conf > 1.0:
            paddle_conf /= 100.0
            
        if edge_penalty:
            paddle_conf *= 0.5
            
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
        
    def extract_text(self, image_path: str, bypass_kb: bool = False, salt: bool = False) -> Dict[str, Any]:
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
        if features and "phash" in features and not bypass_kb:
            match = self.knowledge_matcher.find_exact_match(features["phash"])
            if match:
                # Expecting match to be a dict {"text": ..., "confidence": ...}
                return {
                    "text": match.get("text", ""),
                    "confidence": match.get("confidence", 100.0),
                    "source": "exact_match"
                }
                
        # Step 3: Raw OCR (Level 4)
        # Note: Level 2 (Similarity) and 3 (ML) will be inserted here in the future
        text, conf = self.fallback_ocr.recognize_text(image_path, salt=salt)
        
        return {
            "text": text,
            "confidence": conf,
            "source": "paddleocr"
        }

class TesseractOCREngine(IOCREngine):
    """
    Standard OCR using pytesseract.
    """
    def __init__(self):
        try:
            import pytesseract
            self.installed = True
        except ImportError:
            logger.warning("pytesseract is not installed.")
            self.installed = False

    def recognize_text(self, image_path: str, salt: bool = False) -> Tuple[str, float]:
        if not self.installed:
            return ("", 0.0)
            
        try:
            import pytesseract
            from PIL import Image
            import numpy as np
            
            img = Image.open(image_path)
            if salt:
                img_arr = np.array(img)
                noise = np.random.randint(0, 5, img_arr.shape, dtype='uint8')
                img = Image.fromarray(np.clip(img_arr + noise, 0, 255))
                
            text = pytesseract.image_to_string(img, config='--psm 6').strip()
            conf = 0.85 if text else 0.0
            return (text, conf)
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return ("", 0.0)
