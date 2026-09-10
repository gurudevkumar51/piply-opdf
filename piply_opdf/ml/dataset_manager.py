import csv
import os
import json
from sqlalchemy.orm import Session
from .. import models

class DatasetManager:
    """
    Manages exporting verified OCR data for offline ML training.
    Specifically targeting the 4 specialized models:
    1. Printed Text
    2. Handwritten Text
    3. Numeric / Date
    4. Symbols / Special Characters
    """
    def __init__(self, db: Session, export_dir: str = "dataset"):
        self.db = db
        self.export_dir = export_dir
        os.makedirs(self.export_dir, exist_ok=True)
        
    def export_csv(self, filename="verified_dataset.csv"):
        """
        Exports all knowledge base entries into a CSV for training.
        """
        path = os.path.join(self.export_dir, filename)
        kb_entries = self.db.query(models.OCRKnowledgeBase).filter(
            models.OCRKnowledgeBase.text_value != None
        ).all()
        
        with open(path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Write Header
            writer.writerow([
                "phash", "width", "height", "aspect_ratio", "edge_density",
                "stroke_density", "connected_components", "hog_len", "text_value", "label_class", "component_type"
            ])
            
            for entry in kb_entries:
                hog_len = 0
                if entry.hog_features:
                    try:
                        hog_len = len(json.loads(entry.hog_features))
                    except:
                        pass
                        
                # Simple logic for label class classification (could be improved)
                label_class = "printed" # Default
                val = entry.text_value.strip()
                if val.isnumeric() or "/" in val or "-" in val:
                    label_class = "numeric_date"
                elif len(val) == 1 and not val.isalnum():
                    label_class = "symbols"
                    
                writer.writerow([
                    entry.phash, entry.width, entry.height, entry.aspect_ratio,
                    entry.edge_density, entry.stroke_density, entry.connected_components,
                    hog_len, entry.text_value, label_class, entry.component_type
                ])
                
        return path
