import os
import json
import traceback
import threading
from sqlalchemy.orm import Session
from sqlalchemy.orm import scoped_session, sessionmaker
from pathlib import Path
import fitz

from . import models, database
from piply_opdf.config import Config

config = Config()
UPLOAD_DIR = config.get("environment.upload_dir", "uploads")

from piply_opdf.modules.feature_extractor import DefaultFeatureExtractor

_feature_extractor = DefaultFeatureExtractor()

def extract_pdf_pages(file_path: str, output_dir: str):
    try:
        doc = fitz.open(file_path)
        page_paths = []
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(dpi=300)
            page_path = os.path.join(output_dir, f"page_{i+1:03d}.png")
            pix.save(page_path)
            page_paths.append(page_path)
        return page_paths
    except Exception as e:
        print(f"Failed to extract pages: {e}")
        return []

def run_piply_pipeline(document_id: int, filename: str, _db: Session):
    # Create a new session for the background task thread
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
    db = SessionLocal()
    
    doc_record = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc_record:
        db.close()
        return

    try:
        from piply_opdf.document import Document
        file_path = os.path.join(UPLOAD_DIR, filename)
        
        # Run Piply pipeline
        piply_doc = Document(file_path)
        piply_doc.run_all()
        
        doc_record.page_count = piply_doc.assessment.page_count
        
        # Extract page images to work_dir/pages/
        pages_dir = os.path.join(piply_doc.work_dir, "pages")
        enhanced_pages_dir = os.path.join(piply_doc.work_dir, "pages_enhanced")
        os.makedirs(pages_dir, exist_ok=True)
        os.makedirs(enhanced_pages_dir, exist_ok=True)
        
        if file_path.lower().endswith(".pdf"):
            extract_pdf_pages(file_path, pages_dir)
            if piply_doc.enhanced_path and os.path.exists(piply_doc.enhanced_path):
                extract_pdf_pages(str(piply_doc.enhanced_path), enhanced_pages_dir)
        else:
            # Just copy the image as page_001.png
            import shutil
            shutil.copy(file_path, os.path.join(pages_dir, "page_001.png"))
            if piply_doc.enhanced_path and os.path.exists(piply_doc.enhanced_path):
                shutil.copy(str(piply_doc.enhanced_path), os.path.join(enhanced_pages_dir, "page_001.png"))
            
        # Parse output manifests and populate DB
        
        # Helper to process a manifest component
        def insert_component(manifest: dict, comp_type: str, page_num: int, parent_id: int = None):
            # Normalize bbox to [x0, y0, x1, y1] array format
            bbox = manifest.get('bbox', [])
            if isinstance(bbox, dict):
                # Piply uses {"x": ..., "y": ..., "width": ..., "height": ...}
                x = bbox.get('x', bbox.get('x0', 0))
                y = bbox.get('y', bbox.get('y0', 0))
                w = bbox.get('width', bbox.get('w', 0))
                h = bbox.get('height', bbox.get('h', 0))
                bbox = [x, y, x + w, y + h]
            elif not bbox and 'x0' in manifest and 'y0' in manifest:
                bbox = [manifest['x0'], manifest['y0'], manifest.get('x1', manifest['x0']), manifest.get('y1', manifest['y0'])]
            elif not bbox and 'x' in manifest and 'y' in manifest:
                bbox = [manifest['x'], manifest['y'], manifest['x'] + manifest.get('w', 0), manifest['y'] + manifest.get('h', 0)]
            
            # Store image_path in manifest_path for cells so we can re-OCR later
            stored_path = manifest.get('image_path') or manifest.get('sub_manifest_path') or manifest.get('manifest_path')
                
            db_comp = models.Component(
                document_id=document_id,
                component_type=comp_type.upper(),
                page_no=page_num,
                bbox=json.dumps(bbox),
                confidence=manifest.get('confidence', 1.0),
                manifest_path=stored_path,
                parent_id=parent_id
            )
            db.add(db_comp)
            db.flush() # get id
            
            # If there is text / OCR output directly at this level
            if 'text' in manifest:
                db_pred = models.OCRPrediction(
                    component_id=db_comp.id,
                    predicted_text=str(manifest['text']),
                    confidence=manifest.get('ocr_confidence', manifest.get('confidence', 1.0))
                )
                db.add(db_pred)
                
            # If there is an image, extract features and possibly OCR
            img_path = manifest.get('image_path')
            if img_path and os.path.exists(img_path):
                try:
                    features = _feature_extractor.extract_features(img_path)
                    db_feat = models.ImageFeature(
                        component_id=db_comp.id,
                        **features
                    )
                    db.add(db_feat)
                except Exception as e:
                    print(f"Feature extraction failed: {e}")
            
            return db_comp.id

        # 1. Parse tables
        for t in piply_doc.tables:
            page_num = t.page
            t_manifest = t.model_dump()
            t_id = insert_component(t_manifest, "TABLE", page_num)
            
            # Insert Columns
            for c in t.columns:
                c_manifest = c.model_dump()
                insert_component(c_manifest, "COLUMN", page_num, parent_id=t_id)
                
            # Insert Rows
            for r in t.rows:
                r_manifest = r.model_dump()
                insert_component(r_manifest, "ROW", page_num, parent_id=t_id)
                
            # Insert Cells
            for cell in t.cells:
                cell_manifest = cell.model_dump()
                # Determine cell image path based on table_dir structure
                t_dir = os.path.join(piply_doc.work_dir, "layouts", f"page_{page_num}", t.table_id)
                cell_manifest['image_path'] = os.path.join(t_dir, "cells", f"{cell.cell_id}.png")
                insert_component(cell_manifest, "CELL", page_num, parent_id=t_id)

        # 2. Parse borderless tables
        for t in piply_doc.borderless_tables:
            page_num = getattr(t, 'page', getattr(t, 'page_number', 1))
            t_manifest = t.model_dump()
            t_id = insert_component(t_manifest, "BORDERLESS_TABLE", page_num)
            
            # Insert Columns
            for c in getattr(t, 'columns', []):
                insert_component(c.model_dump(), "COLUMN", page_num, parent_id=t_id)
                
            # Insert Rows
            for r in getattr(t, 'rows', []):
                insert_component(r.model_dump(), "ROW", page_num, parent_id=t_id)
                
            # Insert Cells
            for cell in getattr(t, 'cells', []):
                cell_manifest = cell.model_dump()
                t_dir = os.path.join(piply_doc.work_dir, "layouts", f"page_{page_num}", getattr(t, 'id', getattr(t, 'table_id', 'unknown')))
                cell_manifest['image_path'] = os.path.join(t_dir, "cells", f"{getattr(cell, 'cell_id', 'unknown')}.png")
                insert_component(cell_manifest, "CELL", page_num, parent_id=t_id)

        # 3. Parse headers
        for h in piply_doc.headers:
            page_num = getattr(h, 'page', getattr(h, 'page_number', 1))
            insert_component({"bbox": h.bbox, "text": getattr(h, 'text', ''), "confidence": getattr(h, 'confidence', 1.0)}, "HEADER", page_num)
                
        # 4. Parse footers
        for f in piply_doc.footers:
            page_num = getattr(f, 'page', getattr(f, 'page_number', 1))
            insert_component({"bbox": f.bbox, "text": getattr(f, 'text', ''), "confidence": getattr(f, 'confidence', 1.0)}, "FOOTER", page_num)

        db.commit()
        
        # 5. Export OCR Manifest (Initial pass without OCR, later gets updated)
        export_ocr_manifest(document_id, db)

        doc_record.status = "completed"
        db.commit()
        
        # 6. Start OCR in background thread
        threading.Thread(target=run_ocr_on_cells, args=(document_id,)).start()
        
    except Exception as e:
        traceback.print_exc()
        doc_record.status = "error"
        db.commit()
    finally:
        db.close()

def run_ocr_on_cells(document_id: int):
    """Run 3-Layer OCR on all CELL components of a document."""
    from . import ocr_service
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
    db = SessionLocal()
    
    try:
    
        cells = db.query(models.Component).filter(
            models.Component.document_id == document_id,
            models.Component.component_type == "CELL"
        ).all()
        
        for cell in cells:
            if not cell.manifest_path or not os.path.exists(cell.manifest_path):
                continue
            
            # Skip if already has a prediction
            existing = db.query(models.OCRPrediction).filter(
                models.OCRPrediction.component_id == cell.id
            ).first()
            if existing:
                continue
                
            try:
                ocr_res = ocr_service.extract_cell_text(cell.manifest_path, db)
                if ocr_res is not None:
                    db_pred = models.OCRPrediction(
                        component_id=cell.id,
                        predicted_text=ocr_res.text,
                        confidence=ocr_res.confidence
                    )
                    db.add(db_pred)
                    db.commit()
            except Exception as e:
                print(f"OCR failed for cell {cell.id}: {e}")
                db.rollback()
    finally:
        db.close()

def export_ocr_manifest(document_id: int, db: Session):
    doc_record = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc_record:
        return None
        
    filename = doc_record.filename
    base_name = filename.rsplit('.', 1)[0]
    work_dir = os.path.join("uploads", f"{base_name}_piply")
    os.makedirs(work_dir, exist_ok=True)
    
    components = db.query(models.Component).filter(models.Component.document_id == document_id).all()
    
    # We also need OCR predictions to include in the master manifest
    preds = db.query(models.OCRPrediction).filter(
        models.OCRPrediction.component_id.in_([c.id for c in components])
    ).all()
    
    pred_dict = {p.component_id: {
        "text": p.predicted_text,
        "confidence": p.confidence
    } for p in preds}

    manifest = {
        "document_id": document_id,
        "filename": filename,
        "tables": [],
        "borderless_tables": [],
        "headers": [],
        "footers": []
    }
    
    comp_dict = {c.id: {
        "id": c.id,
        "type": c.component_type,
        "page": c.page_no,
        "bbox": json.loads(c.bbox) if c.bbox else None,
        "manifest_path": c.manifest_path,
        "ocr": pred_dict.get(c.id),
        "children": []
    } for c in components}
    
    # Group children
    for c in components:
        if c.parent_id and c.parent_id in comp_dict:
            comp_dict[c.parent_id]["children"].append(comp_dict[c.id])
            
    # Organize root elements
    for c in components:
        if c.parent_id is None:
            if c.component_type == "TABLE":
                manifest["tables"].append(comp_dict[c.id])
            elif c.component_type == "BORDERLESS_TABLE":
                manifest["borderless_tables"].append(comp_dict[c.id])
            elif c.component_type == "HEADER":
                manifest["headers"].append(comp_dict[c.id])
            elif c.component_type == "FOOTER":
                manifest["footers"].append(comp_dict[c.id])
                
    master_manifest_path = os.path.join(work_dir, "master_manifest.json")
    with open(master_manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
        
    return master_manifest_path
