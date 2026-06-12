import cv2
import numpy as np
from pathlib import Path
from piply_opdf.models.grid import TableModel

class DebugVisualizer:
    """Generates debug images to visualize the mathematical layout detection."""
    
    def __init__(self):
        pass
        
    def visualize(self, image: np.ndarray, table: TableModel, debug_dir: Path):
        """Generates numbered debug artifacts."""
        debug_dir.mkdir(parents=True, exist_ok=True)
        
        prefix = f"{table.table_id}_"
        
        # 1. Threshold
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2)
        cv2.imwrite(str(debug_dir / f"{prefix}01_threshold.png"), thresh)
        
        # 2. Repaired Lines (we approximate it for visualization)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
        h_lines = cv2.morphologyEx(h_lines, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1)))
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
        v_lines = cv2.morphologyEx(v_lines, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40)))
        repaired = cv2.bitwise_or(h_lines, v_lines)
        cv2.imwrite(str(debug_dir / f"{prefix}02_repaired_lines.png"), repaired)
        
        # 3. Columns
        img_cols = image.copy()
        for col in table.columns:
            cx, cy, cw, ch = col.bbox.to_tuple()
            cv2.rectangle(img_cols, (cx, cy), (cx+cw, cy+ch), (255, 0, 0), 2)
            cv2.putText(img_cols, f"{col.confidence:.2f}", (cx+5, cy+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)
        cv2.imwrite(str(debug_dir / f"{prefix}03_columns.png"), img_cols)
        
        # 4. Rows
        img_rows = image.copy()
        for row in table.rows:
            rx, ry, rw, rh = row.bbox.to_tuple()
            cv2.rectangle(img_rows, (rx, ry), (rx+rw, ry+rh), (0, 255, 255), 2)
        cv2.imwrite(str(debug_dir / f"{prefix}04_rows.png"), img_rows)
        
        # 5. Grid Model
        img_grid = image.copy()
        tx, ty, tw, th = table.bbox.to_tuple()
        cv2.rectangle(img_grid, (tx, ty), (tx+tw, ty+th), (0, 0, 255), 3)
        for col in table.columns:
            cx, cy, cw, ch = col.bbox.to_tuple()
            cv2.line(img_grid, (cx, cy), (cx, cy+ch), (255, 0, 0), 1)
        for row in table.rows:
            rx, ry, rw, rh = row.bbox.to_tuple()
            cv2.line(img_grid, (rx, ry), (rx+rw, ry), (0, 255, 255), 1)
        cv2.imwrite(str(debug_dir / f"{prefix}05_grid_model.png"), img_grid)
        
        # 6. Cells
        img_cells = image.copy()
        for cell in table.cells:
            x, y, w, h = cell.bbox.to_tuple()
            cv2.rectangle(img_cells, (x, y), (x+w, y+h), (0, 255, 0), 2)
        cv2.imwrite(str(debug_dir / f"{prefix}06_cells.png"), img_cells)
