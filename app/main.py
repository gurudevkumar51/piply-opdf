import os
import shutil
import asyncio
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, BackgroundTasks, Query
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
REVIEWABLE_COMPONENT_TYPES = ["CELL", "KEY_VALUE", "WORD"]

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Piply OPDF Review & Validation")

# Mount static directories
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Removed os._exit(0) to allow graceful uvicorn shutdown

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

    import uuid
    unique_filename = f"{uuid.uuid4().hex[:8]}_{file.filename}"
    
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    db_doc = models.Document(
        filename=unique_filename,
        file_type=ext.replace(".", ""),
        status="uploaded"
    )
    db.add(db_doc)
    db.commit()
    db.refresh(db_doc)
    return db_doc

@app.post("/process/{document_id}", response_model=schemas.ProcessResponse)
async def process_document(
    document_id: int, 
    background_tasks: BackgroundTasks, 
    ocr_engine: str = "paddle",
    db: Session = Depends(database.get_db)
):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if doc.status == "processing":
        raise HTTPException(status_code=400, detail="Document is already processing")

    doc.status = "processing"
    doc.ocr_engine = ocr_engine
    db.commit()

    # Launch processing in background
    background_tasks.add_task(services.run_piply_pipeline, document_id, doc.filename, db)

    return schemas.ProcessResponse(
        job_id=str(doc.id),
        status="processing",
        message="Document processing started in background."
    )

@app.post("/resume-ocr/{document_id}")
async def resume_ocr(document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    background_tasks.add_task(services.run_ocr_on_cells, document_id)
    return {"status": "resumed", "message": "OCR resumed in background"}

@app.get("/documents", response_model=List[schemas.DocumentResponse])
async def get_documents(skip: int = 0, limit: int = 100, db: Session = Depends(database.get_db)):
    return db.query(models.Document).offset(skip).limit(limit).all()

@app.get("/documents/{document_id}", response_model=schemas.DocumentResponse)
async def get_document(document_id: int, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc

from sqlalchemy.orm import joinedload

@app.get("/components/{document_id}", response_model=List[schemas.ComponentResponse])
async def get_components(document_id: int, db: Session = Depends(database.get_db)):
    components = db.query(models.Component).options(
        joinedload(models.Component.predictions).joinedload(models.OCRPrediction.feedback)
    ).filter(models.Component.document_id == document_id).all()
    return components



@app.post("/feedback/{prediction_id}")
async def submit_feedback(prediction_id: int, feedback: schemas.FeedbackUpdate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    prediction = db.query(models.OCRPrediction).filter(models.OCRPrediction.id == prediction_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")
        
    # If the user clicks Accept, it's a human verification, regardless of if the text changed.
    submitted_value = feedback.user_value if feedback.user_value is not None else prediction.predicted_text
    is_modified = submitted_value != prediction.predicted_text
    final_val = submitted_value if is_modified else prediction.predicted_text
    
    # ANY feedback submitted through this endpoint is human feedback.
    final_source = "human"

    fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == prediction_id).first()
    if not fb:
        fb = models.OCRFeedback(
            prediction_id=prediction_id,
            user_value=final_val,
            is_accepted=feedback.is_accepted,
            source=final_source
        )
        db.add(fb)
    else:
        fb.user_value = final_val
        fb.is_accepted = feedback.is_accepted
        fb.source = final_source

    if feedback.is_accepted and prediction.component.manifest_path:
        from piply_opdf.feedback import register_correction
        background_tasks.add_task(
            register_correction, 
            prediction.component.manifest_path, 
            final_val, 
            final_source, 
            prediction.component.component_type,
            prediction.component.cluster_id,
            prediction.component.quality_score,
            prediction.component.rotation_angle,
            prediction.component.foreground_ratio,
            prediction.component.entropy,
            prediction.component.skeleton_length
        )
            
    db.commit()
    return {"status": "success"}
        

@app.post("/feedback/bulk")
async def bulk_accept(bulk_update: schemas.BulkFeedbackUpdate, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    for pred_id in bulk_update.prediction_ids:
        prediction = db.query(models.OCRPrediction).filter(models.OCRPrediction.id == pred_id).first()
        if not prediction:
            continue
        
        final_val = prediction.predicted_text
        # ANY feedback submitted through this endpoint is human feedback.
        final_source = "human"
            
        fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == pred_id).first()
        if not fb:
            fb = models.OCRFeedback(
                prediction_id=pred_id,
                user_value=final_val,
                is_accepted=True,
                source=final_source
            )
            db.add(fb)
        else:
            fb.user_value = final_val
            fb.is_accepted = True
            fb.source = final_source
            
        if prediction.component.manifest_path:
            from piply_opdf.feedback import register_correction
            background_tasks.add_task(
                register_correction, 
                prediction.component.manifest_path, 
                fb.user_value, 
                fb.source, 
                prediction.component.component_type,
                prediction.component.cluster_id,
                prediction.component.quality_score,
                prediction.component.rotation_angle,
                prediction.component.foreground_ratio,
                prediction.component.entropy,
                prediction.component.skeleton_length
            )
                
    db.commit()
    return {"status": "success", "count": len(bulk_update.prediction_ids)}

@app.post("/ocr-cell/{component_id}/reload", response_model=schemas.ComponentResponse)
async def reload_ocr_cell(component_id: int, strategy: Optional[str] = Query("default"), db: Session = Depends(database.get_db)):
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
        # Default strategy: use document's engine, no salt
        engine_name = None # Will fall back to document engine inside extract_cell_text
        use_salt = False
        
        if strategy == "salt":
            use_salt = True
        elif strategy == "tesseract":
            engine_name = "tesseract"
        elif strategy == "paddle":
            engine_name = "paddle"
            
        ocr_res = ocr_service.extract_cell_text(
            comp.manifest_path, 
            db, 
            engine_name=engine_name,
            bypass_kb=True, 
            salt=use_salt
        )
        
        if ocr_res is not None:
            db_pred = models.OCRPrediction(
                component_id=comp.id,
                predicted_text=ocr_res.text,
                confidence=ocr_res.confidence,
                source=ocr_res.source
            )
            db.add(db_pred)
            db.commit()
            
            # Re-fetch component with predictions eagerly loaded to ensure they serialize correctly
            from sqlalchemy.orm import joinedload
            comp = db.query(models.Component).options(
                joinedload(models.Component.predictions)
            ).filter(models.Component.id == component_id).first()
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
        
    # Fast bulk delete to avoid slow SQLAlchemy cascading
    subq_comp = db.query(models.Component.id).filter(models.Component.document_id == document_id).subquery()
    subq_pred = db.query(models.OCRPrediction.id).filter(models.OCRPrediction.component_id.in_(subq_comp)).subquery()

    db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id.in_(subq_pred)).delete(synchronize_session=False)
    db.query(models.OCRPrediction).filter(models.OCRPrediction.component_id.in_(subq_comp)).delete(synchronize_session=False)
    db.query(models.Component).filter(models.Component.document_id == document_id).delete(synchronize_session=False)

    db.delete(doc)
    db.commit()
    
    # Optionally delete the file from disk
    file_path = os.path.join(UPLOAD_DIR, doc.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        
    # Delete the piply processing folder
    import shutil
    base_name = doc.filename.rsplit('.', 1)[0]
    piply_dir = os.path.join(UPLOAD_DIR, f"{base_name}_piply")
    if os.path.exists(piply_dir):
        shutil.rmtree(piply_dir, ignore_errors=True)
        
    return {"status": "success"}

@app.get("/cell-image/{component_id}")
async def get_cell_image(component_id: int, db: Session = Depends(database.get_db)):
    """Serve the cropped review-unit image file."""
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    if not comp.manifest_path or not os.path.exists(comp.manifest_path):
        raise HTTPException(status_code=404, detail="Component image not found")
    return FileResponse(comp.manifest_path, media_type="image/png")

@app.post("/ocr-cell/{component_id}", response_model=schemas.ComponentResponse)
async def run_ocr_cell(component_id: int, db: Session = Depends(database.get_db)):
    """Run OCR on a specific review-unit component."""
    comp = db.query(models.Component).filter(models.Component.id == component_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Component not found")
    if comp.component_type not in REVIEWABLE_COMPONENT_TYPES:
        raise HTTPException(status_code=400, detail="Component is not reviewable")
    if not comp.manifest_path or not os.path.exists(comp.manifest_path):
        raise HTTPException(status_code=404, detail="Component image not found on disk")
    
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
            existing.source = ocr_res.source
        else:
            db_pred = models.OCRPrediction(
                component_id=component_id,
                predicted_text=ocr_res.text,
                confidence=ocr_res.confidence,
                source=ocr_res.source
            )
            db.add(db_pred)
        db.commit()

    from sqlalchemy.orm import joinedload
    comp = db.query(models.Component).options(
        joinedload(models.Component.predictions)
    ).filter(models.Component.id == component_id).first()
    return comp

@app.post("/ocr-all/{document_id}")
async def ocr_all_cells(document_id: int, background_tasks: BackgroundTasks, db: Session = Depends(database.get_db)):
    """Run OCR on all reviewable cropped components of a document in background."""
    cells = db.query(models.Component).filter(
        models.Component.document_id == document_id,
        models.Component.component_type.in_(REVIEWABLE_COMPONENT_TYPES)
    ).all()
    if not cells:
        raise HTTPException(status_code=404, detail="No reviewable components found for this document")
    
    background_tasks.add_task(services.run_ocr_on_cells, document_id, db)
    return {"status": "started", "cell_count": len(cells)}

@app.get("/download-manifest/{document_id}")
async def download_manifest(document_id: int, db: Session = Depends(database.get_db)):
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    base_name = doc.filename.rsplit('.', 1)[0]
    # Always regenerate on the fly to include latest OCR and user feedback
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

@app.get("/api/knowledge/image/{phash}")
async def get_knowledge_image(phash: str):
    from piply_opdf.feedback import get_registry
    registry = get_registry()
    img_path = os.path.join(registry.knowledge_dir, "images", f"{phash}.png")
    if os.path.exists(img_path):
        return FileResponse(img_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="Image not found")

@app.get("/api/knowledge")
async def get_knowledge(skip: int = 0, limit: int = 50, search: str = "", sort: str = ""):
    from piply_opdf.feedback import get_registry
    registry = get_registry()
    session = registry.get_default_session()
    try:
        from piply_opdf.database.knowledge_models import OCRKnowledgeEntry
        from sqlalchemy import or_, desc
        
        query = session.query(OCRKnowledgeEntry)
        
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    OCRKnowledgeEntry.text_value.ilike(search_pattern),
                    OCRKnowledgeEntry.phash.ilike(search_pattern)
                )
            )
            
        if sort == "value_asc":
            query = query.order_by(OCRKnowledgeEntry.text_value.asc())
        elif sort == "value_desc":
            query = query.order_by(OCRKnowledgeEntry.text_value.desc())
        else:
            query = query.order_by(OCRKnowledgeEntry.id.asc())
            
        total = query.count()
        
        if limit == 0:
            kb_entries = query.offset(skip).all()
        else:
            kb_entries = query.offset(skip).limit(limit).all()
        
        results = []
        for kb in kb_entries:
            kb_dict = {
                "id": kb.id,
                "phash": kb.phash,
                "text_value": kb.text_value,
                "source": kb.source,
                "entropy": kb.entropy,
                "component_type": kb.component_type,
                "confidence": kb.confidence,
                "sample_component_id": None
            }
            results.append(kb_dict)
            
        return {"total": total, "items": results}
    finally:
        session.close()

@app.put("/api/knowledge/{kb_id}")
async def update_knowledge(kb_id: int, request: Request, db: Session = Depends(database.get_db)):
    data = await request.json()
    from piply_opdf.feedback import get_registry
    registry = get_registry()
    session = registry.get_default_session()
    
    try:
        from piply_opdf.database.knowledge_models import OCRKnowledgeEntry
        kb = session.query(OCRKnowledgeEntry).filter(OCRKnowledgeEntry.id == kb_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base entry not found")
            
        new_val = data.get("text_value", kb.text_value)
        if new_val != kb.text_value:
            kb.text_value = new_val
            kb.source = "human_update" 
        session.commit()
    finally:
        session.close()
        
    return {"status": "success"}

@app.delete("/api/knowledge/{kb_id}")
async def delete_knowledge(kb_id: int):
    from piply_opdf.feedback import get_registry
    registry = get_registry()
    session = registry.get_default_session()
    try:
        from piply_opdf.database.knowledge_models import OCRKnowledgeEntry
        kb = session.query(OCRKnowledgeEntry).filter(OCRKnowledgeEntry.id == kb_id).first()
        if not kb:
            raise HTTPException(status_code=404, detail="Knowledge base entry not found")
            
        session.delete(kb)
        session.commit()
    finally:
        session.close()
    return {"status": "success"}
