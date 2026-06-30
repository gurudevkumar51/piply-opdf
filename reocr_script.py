import os
import sys

# Ensure piply_opdf can be imported
sys.path.insert(0, os.path.abspath('.'))

from app.database import SessionLocal
from app import models
from app.ocr_service import extract_cell_text
from app.services import export_ocr_manifest

def reocr_all():
    session = SessionLocal()
    
    doc_id = 1
    
    components = session.query(models.Component).filter(
        models.Component.document_id == doc_id,
        models.Component.component_type == "CELL"
    ).all()
    
    print(f"Found {len(components)} cells for document {doc_id}")
    
    for c in components:
        # Check current prediction
        pred = session.query(models.OCRPrediction).filter(models.OCRPrediction.component_id == c.id).first()
        if pred:
            # We want to re-run OCR without ML Cache
            res = extract_cell_text(c.manifest_path, session, bypass_kb=True, engine_name="paddle")
            pred.predicted_text = res.text
            pred.confidence = res.confidence
            
            # Also clear any feedback to be safe
            fbs = session.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == pred.id).all()
            for fb in fbs:
                session.delete(fb)
                
    session.commit()
    print("Committed all new OCR predictions.")
    
    # Regenerate master manifest
    export_ocr_manifest(doc_id, session)
    print("Regenerated master manifest.")
    
if __name__ == "__main__":
    reocr_all()
