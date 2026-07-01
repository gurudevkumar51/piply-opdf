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
        # Delete existing components via ORM to trigger cascade deletes
        old_components = db.query(models.Component).filter(models.Component.document_id == document_id).all()
        for c in old_components:
            db.delete(c)
        db.commit()
        
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
        def insert_component(manifest, comp_type, page_num, parent_id=None, row_idx=None):
            # Normalize bbox to [x0, y0, x1, y1] array format
            bbox = manifest.get('bbox', [])
            if isinstance(bbox, dict):
                x = bbox.get('x', bbox.get('x0', 0))
                y = bbox.get('y', bbox.get('y0', 0))
                w = bbox.get('width', bbox.get('width', 0))
                h = bbox.get('height', bbox.get('height', 0))
                bbox = [x, y, x + w, y + h]
            elif isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                # piply_opdf layout models output lists/tuples exclusively in (x, y, w, h) format
                bbox = [bbox[0], bbox[1], bbox[0] + bbox[2], bbox[1] + bbox[3]]
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
                
            # (Features are now extracted on the fly by the OCR engine and saved to the Knowledge Base on feedback)
            
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
            for idx, c in enumerate(getattr(t, 'columns', [])):
                c_data = c.model_dump() if hasattr(c, 'model_dump') else {"bbox": list(c), "column_id": f"c{idx}"}
                insert_component(c_data, "COLUMN", page_num, parent_id=t_id)
                
            # Insert Rows
            for idx, r in enumerate(getattr(t, 'rows', [])):
                r_data = r.model_dump() if hasattr(r, 'model_dump') else {"bbox": list(r), "row_id": f"r{idx}"}
                insert_component(r_data, "ROW", page_num, parent_id=t_id)
                
            # Insert Cells
            for cell in getattr(t, 'cells', []):
                cell_manifest = cell.model_dump()
                t_dir = os.path.join(piply_doc.work_dir, "layouts", f"page_{page_num}", getattr(t, 'id', getattr(t, 'table_id', 'unknown')))
                cell_manifest['image_path'] = os.path.join(t_dir, "cells", f"{getattr(cell, 'cell_id', 'unknown')}.png")
                insert_component(cell_manifest, "CELL", page_num, parent_id=t_id)

        # 3. Parse headers
        for h in piply_doc.headers:
            if isinstance(h, dict):
                page_num = h.get('page', h.get('page_number', 1))
                insert_component({"bbox": h.get('bbox', []), "text": h.get('text', ''), "confidence": h.get('confidence', 1.0)}, "HEADER", page_num)
            else:
                page_num = getattr(h, 'page', getattr(h, 'page_number', 1))
                insert_component({"bbox": getattr(h, 'bbox', []), "text": getattr(h, 'text', ''), "confidence": getattr(h, 'confidence', 1.0)}, "HEADER", page_num)
                
        # 4. Parse footers
        for f in piply_doc.footers:
            if isinstance(f, dict):
                page_num = f.get('page', f.get('page_number', 1))
                insert_component({"bbox": f.get('bbox', []), "text": f.get('text', ''), "confidence": f.get('confidence', 1.0)}, "FOOTER", page_num)
            else:
                page_num = getattr(f, 'page', getattr(f, 'page_number', 1))
                insert_component({"bbox": getattr(f, 'bbox', []), "text": getattr(f, 'text', ''), "confidence": getattr(f, 'confidence', 1.0)}, "FOOTER", page_num)

        # 5. Parse key-value pairs
        for kv in getattr(piply_doc, "key_values", []):
            if isinstance(kv, dict):
                page_num = kv.get('page', kv.get('page_number', 1))
                insert_component(
                    {
                        "bbox": kv.get('bbox', []),
                        "text": kv.get('text', ''),
                        "key": kv.get('key', ''),
                        "value": kv.get('value', ''),
                        "confidence": kv.get('confidence', 1.0),
                        "image_path": kv.get('image_path'),
                        "manifest_path": kv.get('manifest_path'),
                    },
                    "KEY_VALUE",
                    page_num,
                )

        # 6. Parse paragraphs
        for paragraph in getattr(piply_doc, "paragraphs", []):
            if isinstance(paragraph, dict):
                page_num = paragraph.get('page', paragraph.get('page_number', 1))
                paragraph_id = insert_component(
                    {
                        "bbox": paragraph.get('bbox', []),
                        "text": paragraph.get('text', ''),
                        "confidence": paragraph.get('confidence', 1.0),
                        "image_path": paragraph.get('image_path'),
                        "manifest_path": paragraph.get('manifest_path'),
                    },
                    "PARAGRAPH",
                    page_num,
                )
                for word in paragraph.get("words", []):
                    insert_component(
                        {
                            "bbox": word.get("bbox", []),
                            "text": word.get("text", ""),
                            "confidence": word.get("confidence", 1.0),
                            "image_path": word.get("image_path"),
                            "manifest_path": word.get("manifest_path"),
                        },
                        "WORD",
                        page_num,
                        parent_id=paragraph_id,
                    )

        # 6.5 Parse sentences
        for sentence in getattr(piply_doc, "sentences", []):
            if isinstance(sentence, dict):
                page_num = sentence.get('page', sentence.get('page_number', 1))
                sentence_id = insert_component(
                    {
                        "bbox": sentence.get('bbox', []),
                        "text": sentence.get('text', ''),
                        "confidence": sentence.get('confidence', 1.0),
                        "image_path": sentence.get('image_path'),
                        "manifest_path": sentence.get('manifest_path'),
                    },
                    "SENTENCE",
                    page_num,
                )
                for word in sentence.get("words", []):
                    insert_component(
                        {
                            "bbox": word.get("bbox", []),
                            "text": word.get("text", ""),
                            "confidence": word.get("confidence", 1.0),
                            "image_path": word.get("image_path"),
                            "manifest_path": word.get("manifest_path"),
                        },
                        "WORD",
                        page_num,
                        parent_id=sentence_id,
                    )

        db.commit()
        
        # 7. Export OCR Manifest (Initial pass without OCR, later gets updated)
        export_ocr_manifest(document_id, db)

        doc_record.status = "completed"
        db.commit()
        
        # 8. Start OCR in background thread
        threading.Thread(target=run_ocr_on_cells, args=(document_id,)).start()
        
    except Exception as e:
        traceback.print_exc()
        doc_record.status = "error"
        db.commit()
    finally:
        db.close()

def run_ocr_on_cells(document_id: int):
    """Run OCR on all reviewable cropped components of a document."""
    from . import ocr_service
    from piply_opdf.modules.feature_extractor import DefaultFeatureExtractor
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=database.engine)
    db = SessionLocal()
    extractor = DefaultFeatureExtractor()
    
    try:
        doc_record = db.query(models.Document).filter(models.Document.id == document_id).first()
        engine_name = doc_record.ocr_engine if doc_record and getattr(doc_record, 'ocr_engine', None) else "paddle"
    
        cells = db.query(models.Component).filter(
            models.Component.document_id == document_id,
            models.Component.component_type.in_(["CELL", "KEY_VALUE", "WORD"])
        ).all()
        
        for cell in cells:
            if not cell.manifest_path or not os.path.exists(cell.manifest_path):
                continue
                
            # If phash is not computed yet, compute it now
            if not cell.phash:
                try:
                    features = extractor.extract_features(cell.manifest_path)
                    if features and "phash" in features:
                        cell.phash = features["phash"]
                except Exception as e:
                    pass
            
            # Skip if already has a prediction
            existing = db.query(models.OCRPrediction).filter(
                models.OCRPrediction.component_id == cell.id
            ).first()
            if existing:
                continue
                
            try:
                ocr_res = ocr_service.extract_cell_text(cell.manifest_path, db, engine_name=engine_name)
                if ocr_res is not None:
                    db_pred = models.OCRPrediction(
                        component_id=cell.id,
                        predicted_text=ocr_res.text,
                        confidence=ocr_res.confidence,
                        source=ocr_res.source
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
    
    # We also need OCR predictions and feedback to include in the master manifest
    preds = db.query(models.OCRPrediction).filter(
        models.OCRPrediction.component_id.in_([c.id for c in components])
    ).all()
    
    pred_ids = [p.id for p in preds]
    feedbacks = db.query(models.OCRFeedback).filter(
        models.OCRFeedback.prediction_id.in_(pred_ids)
    ).all() if pred_ids else []
    feedback_dict = {f.prediction_id: f for f in feedbacks}
    
    pred_dict = {}
    for p in preds:
        fb = feedback_dict.get(p.id)
        final_text = p.predicted_text
        is_human = False
        
        if fb and fb.is_accepted and fb.source != "hash_match":
            if fb.user_value is not None:
                final_text = fb.user_value
            is_human = True
            
        pred_dict[p.component_id] = {
            "text": final_text,
            "confidence": 1.0 if is_human else p.confidence,
            "is_human": is_human
        }

    manifest = {
        "document_id": document_id,
        "filename": filename,
        "tables": [],
        "borderless_tables": [],
        "headers": [],
        "footers": [],
        "key_values": [],
        "paragraphs": [],
        "sentences": []
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
            elif c.component_type == "KEY_VALUE":
                manifest["key_values"].append(comp_dict[c.id])
            elif c.component_type == "PARAGRAPH":
                manifest["paragraphs"].append(comp_dict[c.id])
            elif c.component_type == "SENTENCE":
                manifest["sentences"].append(comp_dict[c.id])
                
    master_manifest_path = os.path.join(work_dir, "master_manifest.json")
    with open(master_manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2)
        
    return master_manifest_path
