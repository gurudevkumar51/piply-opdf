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

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

app = FastAPI(title="Piply OPDF Review & Validation")

# Mount static directories
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Make piply output folders and uploads available statically for viewer
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

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

    file_path = os.path.join("uploads", file.filename)
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

@app.post("/feedback/{prediction_id}")
async def submit_feedback(prediction_id: int, feedback: schemas.FeedbackUpdate, db: Session = Depends(database.get_db)):
    prediction = db.query(models.OCRPrediction).filter(models.OCRPrediction.id == prediction_id).first()
    if not prediction:
        raise HTTPException(status_code=404, detail="Prediction not found")

    fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == prediction_id).first()
    if fb:
        if feedback.user_value is not None:
            fb.user_value = feedback.user_value
        fb.is_accepted = feedback.is_accepted
    else:
        fb = models.OCRFeedback(
            prediction_id=prediction_id,
            user_value=feedback.user_value if feedback.user_value is not None else prediction.predicted_text,
            is_accepted=feedback.is_accepted
        )
        db.add(fb)
    db.commit()
    return {"status": "success"}

@app.post("/feedback/bulk")
async def bulk_accept(bulk_update: schemas.BulkFeedbackUpdate, db: Session = Depends(database.get_db)):
    for pred_id in bulk_update.prediction_ids:
        fb = db.query(models.OCRFeedback).filter(models.OCRFeedback.prediction_id == pred_id).first()
        if not fb:
            prediction = db.query(models.OCRPrediction).filter(models.OCRPrediction.id == pred_id).first()
            if prediction:
                fb = models.OCRFeedback(
                    prediction_id=pred_id,
                    user_value=prediction.predicted_text,
                    is_accepted=bulk_update.is_accepted
                )
                db.add(fb)
        else:
            fb.is_accepted = bulk_update.is_accepted
    db.commit()
    return {"status": "success", "count": len(bulk_update.prediction_ids)}

@app.get("/manage", response_class=HTMLResponse)
async def manage_page(request: Request):
    return templates.TemplateResponse("manage.html", {"request": request})

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
    
    from . import ocr_service
    ocr_res = ocr_service.extract_cell_text(comp.manifest_path, db)
    
    if ocr_res and ocr_res.text:
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

