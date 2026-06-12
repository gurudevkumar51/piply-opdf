import cv2
import numpy as np
from piply_opdf.models.grid import TableModel

class GridValidator:
    """Verifies grid cells using border continuity scores."""
    
    def __init__(self):
        pass
        
    def validate(self, image: np.ndarray, table: TableModel) -> TableModel:
        """
        Validates cells and sets their confidence score using the Grid Verification Engine.
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 11, 2
        )
        
        # We can extract actual line boundaries for scoring
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
        h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)
        h_lines = cv2.morphologyEx(h_lines, cv2.MORPH_CLOSE, h_kernel)
        
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
        v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)
        v_lines = cv2.morphologyEx(v_lines, cv2.MORPH_CLOSE, v_kernel)
        
        grid_lines = cv2.bitwise_or(h_lines, v_lines)
        
        table_cell_scores = []
        for cell in table.cells:
            # grid_score = (left + right + top + bottom) / 4
            x, y, w, h = cell.bbox.to_tuple()
            
            # extract boundary ROIs
            top_roi = h_lines[max(0, y-5):y+5, x:x+w]
            bottom_roi = h_lines[y+h-5:y+h+5, x:x+w]
            left_roi = v_lines[y:y+h, max(0, x-5):x+5]
            right_roi = v_lines[y:y+h, x+w-5:x+w+5]
            
            top_score = min(1.0, np.sum(top_roi > 0) / max(1, w))
            bottom_score = min(1.0, np.sum(bottom_roi > 0) / max(1, w))
            left_score = min(1.0, np.sum(left_roi > 0) / max(1, h))
            right_score = min(1.0, np.sum(right_roi > 0) / max(1, h))
            
            grid_score = (top_score + bottom_score + left_score + right_score) / 4.0
            cell.confidence = grid_score
            table_cell_scores.append(grid_score)
            
        # Calculate Column Confidence
        col_scores = []
        for col in table.columns:
            cx, cy, cw, ch = col.bbox.to_tuple()
            # projection score / line strength
            col_v_roi = v_lines[cy:cy+ch, cx:cx+cw]
            line_strength = min(1.0, np.sum(col_v_roi > 0) / max(1, ch * 2))
            
            col_cells = [c for c in table.cells if c.parent_column == col.column_id]
            continuity_score = np.mean([c.confidence for c in col_cells]) if col_cells else 0.0
            
            # Simple approximation of projection + line_strength + continuity
            col.confidence = (line_strength + continuity_score) / 2.0
            col_scores.append(col.confidence)
            
        # Row Confidence
        row_scores = []
        for row in table.rows:
            rx, ry, rw, rh = row.bbox.to_tuple()
            row_cells = [c for c in table.cells if c.row_index == row.row_index]
            row.confidence = np.mean([c.confidence for c in row_cells]) if row_cells else 0.0
            row_scores.append(row.confidence)
            
        # Table Confidence
        if col_scores and row_scores:
            table.confidence = (np.mean(col_scores) + np.mean(row_scores) + np.mean(table_cell_scores)) / 3.0
        else:
            table.confidence = 0.0
            
        return table
