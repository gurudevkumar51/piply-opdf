import os
import shutil
import asyncio
from typing import List
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy.orm import Session
from pathlib import Path

from . import models, schemas, database, services
from piply_opdf.config import Config

config = Config()
UPLOAD_DIR = config.get("environment.upload_dir", "uploads")

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Piply OPDF Review & Validation")

# Mount static directories
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Make piply output folders and uploads available statically for viewer
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount(f"/{UPLOAD_DIR}", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# Dynamic mounting of output folders is tricky, but we can mount the whole root directory's outputs or specific project folders
# We'll just mount the root directory as "outputs" to serve the _piply generated files
app.mount("/outputs", StaticFiles(directory="."), name="outputs")

templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.post("/upload", response_model=schemas.DocumentResponse)
async def upload_file(file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    allowed_extensions = [".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"]
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Unsupported file format")

    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_doc = models.Document(
        filename=file.filename,
        file_type=ext.replace(".", ""),
        status="uploaded"
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@app.post("/process/{document_id}", response_model=schemas.ProcessResponse)
async def process_document(document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.status == "processing":
        raise HTTPException(status_code=400, detail="Document is already processing")

    doc.status = "processing"
    db.commit()

    # Launch processing in background
    background_tasks.add_task(services.run_piply_pipeline, document_id, doc.filename, db)

    return schemas.ProcessResponse(
        job_id=str(doc.id),
        status="processing",
        message="Document processing started in background."
    )

@app.get("/documents", response_model=List[schemas.DocumentResponse])
async def get_documents(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Document).offset(skip).limit(limit).all()

@app.get("/documents/{document_id}", response_model=schemas.DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

@app.get("/components/{document_id}", response_model=List[schemas.ComponentResponse])
async def get_components(document_id: int, db: Session = Depends(database.get_db)):
    components = db.query(models.Component).filter(models.Component.document_id == document_id).all()
    return components

def _update_knowledge_base(db: Session, prediction: models.OCRPrediction, user_value: str, source: str = "human"):
    comp = prediction.component
    if comp and comp.image_features and comp.image_features.phash:
        phash = comp.image_features.phash
        kb = db.query(models.OCRKnowledgeBase).filter(models.OCRKnowledgeBase.image_hash == phash).first()
        if not kb:
            kb = models.OCRKnowledgeBase(
                image_hash=phash,
                text_value=user_value,
                source=source,
                confidence=1.0
            )
            db.add(kb)
        else:
            kb.text_value = user_value
            kb.source = source
            kb.confidence = 1.0
            
        # Update ALL existing predictions across all documents that share this phash!
        # Instead of overwriting predicted_text, we insert/update OCRFeedback to preserve original ML/OCR value
        other_feats = db.query(models.ImageFeature).filter(models.ImageFeature.phash == phash).all()
        comp_ids = [f.component_id for f in other_feats]
        if comp_ids:
            preds = db.query(models.OCRPrediction).filter(models.OCRPrediction.component_id.in_(comp_ids)).all()
            for p in preds:
                fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == p.id).first()
                if fb:
                    fb.user_value = user_value
                    fb.is_accepted = True
                else:
                    fb = models.OCRFeedback(prediction_id=p.id, user_value=user_value, is_accepted=True)
                    db.add(fb)

@app.post("/feedback/{prediction_id}")
async def submit_feedback(prediction_id: int, feedback: schemas.FeedbackUpdate, db: Session = Depends(database.get_db)):
    prediction = db.query(models.OCRPrediction).filter(models.OCRPrediction.id == prediction_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")

    fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == prediction_id).first()
    final_val = feedback.user_value if feedback.user_value is not None else prediction.predicted_text
    
    if fb:
        if feedback.user_value is not None:
            fb.user_value = feedback.user_value
        fb.is_accepted = feedback.is_accepted
    else:
        fb = models.OCRFeedback(
            prediction_id=prediction_id,
            user_value=final_val,
            is_accepted=feedback.is_accepted
        )
        db.add(fb)
        
    if feedback.is_accepted:
        source = "human" if final_val != prediction.predicted_text else "ocr"
        _update_knowledge_base(db, prediction, final_val, source=source)
        
    db.commit()
    return {"status": "success"}

@app.post("/feedback/bulk")
async def bulk_accept(bulk_update: schemas.BulkFeedbackUpdate, db: Session = Depends(database.get_db)):
    for pred_id in bulk_update.prediction_ids:
        prediction = db.query(models.OCRPrediction).filter(models.OCRPrediction.id == pred_id).first()
        if not prediction:
            continue
            
        fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == pred_id).first()
        if not fb:
            fb = models.OCRFeedback(
                prediction_id=pred_id,
                user_value=prediction.predicted_text,
                is_accepted=bulk_update.is_accepted
            )
            db.add(fb)
        else:
            fb.is_accepted = bulk_update.is_accepted
            
        if bulk_update.is_accepted:
            source = "human" if fb.user_value != prediction.predicted_text else "ocr"
            _update_knowledge_base(db, prediction, fb.user_value, source=source)
            
    db.commit()
    return {"status": "success", "count": len(bulk_update.prediction_ids)}

@app.post("/ocr-cell/{component_id}/reload")
async def reload_ocr_cell(component_id: int, db: Session = Depends(database.get_db)):
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
        
    if not comp.manifest_path or not os.path.exists(comp.manifest_path):
        raise HTTPException(status_code=400, detail="Image not found for this component")
        
    # Delete existing prediction and feedback
    existing_pred = db.query(models.OCRPrediction).filter(models.OCRPrediction.component_id == component_id).first()
    if existing_pred:
        db.delete(existing_pred)
        db.commit()
        
    # Re-run OCR
    from app import ocr_service
    try:
        ocr_res = ocr_service.extract_cell_text(comp.manifest_path, db)
        if ocr_res is not None:
            db_pred = models.OCRPrediction(
                component_id=comp.id,
                predicted_text=ocr_res.text,
                confidence=ocr_res.confidence
            )
            db.add(db_pred)
            db.commit()
            db.refresh(db_pred)
            
            # Re-serialize component to return
            comp = db.query(models.Component).filter(models.Component.id == component_id).first()
            return comp
        else:
            raise HTTPException(status_code=500, detail="OCR returned no result")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")

@app.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request):
    return templates.TemplateResponse(request=request, name="manage.html")

@app.delete("/documents/{document_id}")
async def delete_document(document_id: int, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    db.delete(doc)
    db.commit()
    return {"status": "success"}

@app.get("/cell-image/{component_id}")
async def get_cell_image(component_id: int, db: Session = Depends(database.get_db)):
    """Serve the cropped cell image file."""
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    if not comp.manifest_path or not os.path.exists(comp.manifest_path):
        raise HTTPException(status_code=404, detail="Cell image not found")
    return FileResponse(comp.manifest_path, media_type="image/png")

@app.post("/ocr-cell/{component_id}")
async def ocr_cell(component_id: int, db: Session = Depends(database.get_db)):
    """Run 3-Layer OCR on a specific cell component."""
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    if comp.component_type != "CELL":
        raise HTTPException(status_code=400, detail="Component is not a cell")
    if not comp.manifest_path or not os.path.exists(comp.manifest_path):
        raise HTTPException(status_code=404, detail="Cell image not found on disk")
    
    from app import ocr_service
    ocr_res = ocr_service.extract_cell_text(comp.manifest_path, db)
    
    if ocr_res is not None:
        # Check if prediction already exists for this component
        existing = db.query(models.OCRPrediction).filter(
            models.OCRPrediction.component_id == component_id
        ).first()
        if existing:
            existing.predicted_text = ocr_res.text
            existing.confidence = ocr_res.confidence
        else:
            db_pred = models.OCRPrediction(
                component_id=component_id,
                predicted_text=ocr_res.text,
                confidence=ocr_res.confidence
            )
            db.add(db_pred)
        db.commit()
    
    return {
        "text": ocr_res.text if ocr_res else "",
        "confidence": ocr_res.confidence if ocr_res else 0,
        "source": ocr_res.source if ocr_res else "none"
    }

@app.post("/ocr-all/{document_id}")
async def ocr_all_cells(document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    """Run OCR on all CELL components of a document in background."""
    cells = db.query(models.Component).filter(
        models.Component.document_id == document_id,
        models.Component.component_type == "CELL"
    ).all()
    if not cells:
        raise HTTPException(status_code=404, detail="No cells found for this document")
    
    background_tasks.add_task(services.run_ocr_on_cells, document_id, db)
    return {"status": "started", "cell_count": len(cells)}

@app.get("/download-manifest/{document_id}")
async def download_manifest(document_id: int, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    base_name = doc.filename.rsplit('.', 1)[0]
    manifest_path = os.path.join("uploads", f"{base_name}_piply", "master_manifest.json")
    
    if not os.path.exists(manifest_path):
        # Generate on the fly if it doesn't exist
        manifest_path = services.export_ocr_manifest(document_id, db)
        if not manifest_path:
            raise HTTPException(status_code=404, detail="Could not generate manifest")
            
    return FileResponse(
        manifest_path, 
        media_type="application/json", 
        filename=f"{base_name}_manifest.json"
    )

@app.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    return templates.TemplateResponse(request=request, name="ocr_review.html")

@app.get("/reconstruct", response_class=HTMLResponse)
async def reconstruct_page(request: Request):
    return templates.TemplateResponse(request=request, name="reconstruct.html")

@app.get("/knowledge", response_class=HTMLResponse)
async def knowledge_page(request: Request):
    return templates.TemplateResponse(request=request, name="knowledge.html")

@app.get("/api/knowledge")
async def get_knowledge(skip: int = 0, limit: int = 5000, db: Session = Depends(database.get_db)):
    if limit == 0:
        kb_entries = db.query(models.OCRKnowledgeBase).offset(skip).all()
    else:
        kb_entries = db.query(models.OCRKnowledgeBase).offset(skip).limit(limit).all()
    
    # Enhance entries with a sample component ID for image preview
    results = []
    for kb in kb_entries:
        feat = db.query(models.ImageFeature).filter(models.ImageFeature.phash == kb.image_hash).first()
        kb_dict = {
            "id": kb.id,
            "image_hash": kb.image_hash,
            "text_value": kb.text_value,
            "source": kb.source,
            "confidence": kb.confidence,
            "sample_component_id": feat.component_id if feat else None
        }
        results.append(kb_dict)
        
    return results

@app.put("/api/knowledge/{kb_id}")
async def update_knowledge(kb_id: int, request: Request, db: Session = Depends(database.get_db)):
    data = await request.json()
    kb = db.query(models.OCRKnowledgeBase).filter(models.OCRKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")
        
    kb.text_value = data.get("text_value", kb.text_value)
    kb.source = "human" # Manual edit assumes human source
    db.commit()
    
    # Sync OCRFeedback across matching hashes
    other_feats = db.query(models.ImageFeature).filter(models.ImageFeature.phash == kb.image_hash).all()
    comp_ids = [f.component_id for f in other_feats]
    if comp_ids:
        preds = db.query(models.OCRPrediction).filter(models.OCRPrediction.component_id.in_(comp_ids)).all()
        for p in preds:
            fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == p.id).first()
            if fb:
                fb.user_value = kb.text_value
                fb.is_accepted = True
            else:
                fb = models.OCRFeedback(prediction_id=p.id, user_value=kb.text_value, is_accepted=True)
                db.add(fb)
        db.commit()
        
    return {"status": "success"}

@app.delete("/api/knowledge/{kb_id}")
async def delete_knowledge(kb_id: int, db: Session = Depends(database.get_db)):
    kb = db.query(models.OCRKnowledgeBase).filter(models.OCRKnowledgeBase.id == kb_id).first()
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base entry not found")
        
    db.delete(kb)
    db.commit()
    return {"status": "success"}
