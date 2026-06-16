import cv2
import numpy as np
import os
from pathlib import Path
from piply_opdf.models.grid import TableModel

class CellExtractor:
    """Extracts cell images directly using grid boundaries."""
    
    def __init__(self):
        pass
        
    def extract(self, image: np.ndarray, table: TableModel, output_dir: Path):
        """
        Crops cells out of the image based strictly on cell_bbox.
        """
        table_dir = output_dir / f"page_{table.page}" / table.table_id
        table_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Save Table Image
        tx, ty, tw, th = table.bbox.to_tuple()
        ih, iw = image.shape[:2]
        ty1, ty2 = max(0, ty), min(ih, ty + th)
        tx1, tx2 = max(0, tx), min(iw, tx + tw)
        if tx2 > tx1 and ty2 > ty1:
            table_img = image[ty1:ty2, tx1:tx2]
            cv2.imwrite(str(table_dir / "table.png"), table_img)
            
        import shutil
        
        # 2. Save Column Images
        cols_dir = table_dir / "columns"
        if cols_dir.exists():
            shutil.rmtree(cols_dir)
        cols_dir.mkdir(parents=True, exist_ok=True)
        for col in table.columns:
            cx, cy, cw, ch = col.bbox.to_tuple()
            cy1, cy2 = max(0, cy), min(ih, cy + ch)
            cx1, cx2 = max(0, cx), min(iw, cx + cw)
            if cx2 > cx1 and cy2 > cy1:
                col_img = image[cy1:cy2, cx1:cx2]
                cv2.imwrite(str(cols_dir / f"{col.column_id}.png"), col_img)
                
        # 3. Save Row Images
        rows_dir = table_dir / "rows"
        if rows_dir.exists():
            shutil.rmtree(rows_dir)
        rows_dir.mkdir(parents=True, exist_ok=True)
        for row in table.rows:
            rx, ry, rw, rh = row.bbox.to_tuple()
            ry1, ry2 = max(0, ry), min(ih, ry + rh)
            rx1, rx2 = max(0, rx), min(iw, rx + rw)
            if rx2 > rx1 and ry2 > ry1:
                row_img = image[ry1:ry2, rx1:rx2]
                cv2.imwrite(str(rows_dir / f"{row.row_id}.png"), row_img)
                
        # 4. Save Cell Images
        cells_dir = table_dir / "cells"
        cells_dir.mkdir(parents=True, exist_ok=True)
        
        for cell in table.cells:
            x, y, w, h = cell.bbox.to_tuple()
            
            y1 = max(0, y)
            y2 = min(ih, y + h)
            x1 = max(0, x)
            x2 = min(iw, x + w)
            
            if x2 > x1 and y2 > y1:
                cell_img = image[y1:y2, x1:x2]
                out_path = cells_dir / f"{cell.cell_id}.png"
                cv2.imwrite(str(out_path), cell_img)
