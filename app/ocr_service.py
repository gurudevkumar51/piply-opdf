import hashlib
from PIL import Image
import pytesseract
from sqlalchemy.orm import Session
from . import models

_paddle_ocr = None

def get_paddle_ocr():
    global _paddle_ocr
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR
        _paddle_ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
    return _paddle_ocr

def hash_image(image_path: str) -> str:
    hasher = hashlib.sha256()
    try:
        with open(image_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception as e:
        print(f"Error hashing image {image_path}: {e}")
        return ""

class OCRResult:
    def __init__(self, text: str, confidence: float, source: str):
        self.text = text
        self.confidence = confidence
        self.source = source

def vote_text(text1: str, text2: str) -> str:
    t1 = text1.strip()
    t2 = text2.strip()
    if not t1: return t2
    if not t2: return t1
    return t2

def extract_cell_text(image_path: str, db: Session) -> OCRResult:
    img_hash = hash_image(image_path)
    
    # Layer 1
    if img_hash:
        kb_entry = db.query(models.OCRKnowledgeBase).filter(models.OCRKnowledgeBase.image_hash == img_hash).first()
        if kb_entry and kb_entry.text_value is not None:
            return OCRResult(text=kb_entry.text_value, confidence=kb_entry.confidence, source=kb_entry.source)
            
    # Layer 2
    paddle_text = ""
    paddle_conf = 0.0
    try:
        ocr = get_paddle_ocr()
        result = ocr.ocr(image_path, cls=True)
        if result and result[0]:
            texts = []
            confs = []
            for line in result[0]:
                if len(line) >= 2:
                    texts.append(line[1][0])
                    confs.append(line[1][1])
            paddle_text = " ".join(texts)
            if confs:
                paddle_conf = sum(confs) / len(confs)
    except Exception as e:
        print(f"PaddleOCR failed for {image_path}: {e}")
        
    # Layer 3
    final_text = paddle_text
    final_conf = paddle_conf
    final_source = "paddle"
    
    if paddle_conf < 0.90:
        tess_text = ""
        try:
            tess_text = pytesseract.image_to_string(Image.open(image_path), lang='eng').strip()
            if tess_text and tess_text != paddle_text:
                final_text = vote_text(paddle_text, tess_text)
                final_source = "voted"
                final_conf = max(paddle_conf, 0.85) 
        except Exception as e:
            print(f"Tesseract failed for {image_path}: {e}")
            
    if img_hash and final_text:
        try:
            new_kb = models.OCRKnowledgeBase(
                image_hash=img_hash,
                text_value=final_text,
                confidence=final_conf,
                source=final_source
            )
            db.add(new_kb)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Failed to save KB entry: {e}")
            
    return OCRResult(text=final_text, confidence=final_conf, source=final_source)
