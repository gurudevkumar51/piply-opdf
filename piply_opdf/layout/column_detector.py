import cv2
import numpy as np
from typing import List
from piply_opdf.models.grid import GridBoundingBox, ColumnModel

class ColumnDetector:
    """Detects columns using geometric line projections and whitespace gutters."""
    
    def __init__(self):
        pass

    def detect_columns(self, image: np.ndarray, table_bbox: GridBoundingBox, table_id: str) -> List[ColumnModel]:
        """Detect columns within a table block using projection math."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        tx, ty, tw, th = table_bbox.to_tuple()
        roi_gray = gray[ty:ty+th, tx:tx+tw]
        
        _, thresh = cv2.threshold(roi_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        h, w = thresh.shape
        if h == 0 or w == 0:
            return []
            
        # 1. Detect explicit vertical lines
        # Use a thickness of 1 and standard height threshold
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 20)))
        v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
        
        # Dilate slightly vertically to bridge minor gaps
        v_close = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
        v_lines = cv2.morphologyEx(v_lines, cv2.MORPH_CLOSE, v_close)
        
        line_proj = np.sum(v_lines, axis=0) / 255.0
        
        # 2. Detect text/content to find whitespace gutters
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 20), 1))
        h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        
        # Remove horizontal lines and vertical lines from content to isolate text/data
        content = cv2.subtract(thresh, h_lines)
        text_only = cv2.subtract(content, v_lines)
        
        # Apply vertical dilation so text on multiple lines merges into a solid block vertically
        vertical_merge = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
        text_merged = cv2.morphologyEx(text_only, cv2.MORPH_DILATE, vertical_merge)
        text_proj = np.sum(text_merged, axis=0) / 255.0
        # Smooth text projection to avoid micro-valleys from character kerning
        text_proj_smoothed = np.convolve(text_proj, np.ones(5)/5, mode='same')
        
        # 1. Find explicit line boundaries
        line_boundaries = []
        in_line = False
        start = 0
        for i in range(len(line_proj)):
            if line_proj[i] > h * 0.1: # 10% height is safe to capture valid structural grid lines
                if not in_line:
                    in_line = True
                    start = i
            else:
                if in_line:
                    in_line = False
                    line_boundaries.append((start + i) // 2)
                    
        if in_line: 
            line_boundaries.append((start + len(line_proj)) // 2)
        
        # 2. Find raw whitespace gutters
        in_gutter = False
        start = 0
        
        # 3% noise threshold allows for faint stray marks in the gutter or slight text spillage
        threshold = h * 0.03
        
        gutters = []
        for i, val in enumerate(text_proj_smoothed):
            if val < threshold: 
                if not in_gutter:
                    in_gutter = True
                    start = i
            else:
                if in_gutter:
                    in_gutter = False
                    gutters.append((start, i))
                    
        if in_gutter: 
            gutters.append((start, len(text_proj_smoothed)))
        
        # 3. Filter gutters based on intelligent text-line separation
        whitespace_boundaries = []
        for g_start, g_end in gutters:
            if g_end - g_start >= 1: # Very low threshold to catch the tightest columns in sample.pdf
                
                # Find nearest text to the left
                p_left = g_start - 1
                while p_left >= 0 and text_proj_smoothed[p_left] < h * 0.02:
                    p_left -= 1
                    
                # Find nearest text to the right
                p_right = g_end
                while p_right < len(text_proj_smoothed) and text_proj_smoothed[p_right] < h * 0.02:
                    p_right += 1
                    
                # Every significant whitespace gutter is a valid column divider!
                # If there happens to be an explicit grid line nearby, the `< 5px` merge logic below will deduplicate them.
                mid = (g_start + g_end) // 2
                whitespace_boundaries.append(mid)
                    
        boundaries = line_boundaries + whitespace_boundaries
        boundaries.sort()
        
        # Merge boundaries that are very close to each other (< 5px) 
        # to prevent micro-columns, but preserve actual thin columns
        merged_b = []
        for b in boundaries:
            if not merged_b:
                merged_b.append(b)
            else:
                if b - merged_b[-1] < 5:
                    merged_b[-1] = (merged_b[-1] + b) // 2
                else:
                    merged_b.append(b)
        boundaries = merged_b
        
        # Ensure table edges are treated as boundaries
        if not boundaries or boundaries[0] > 15:
            boundaries.insert(0, 0)
        if boundaries[-1] < w - 15:
            boundaries.append(w)
            
        columns = []
        col_idx = 0
        for i in range(len(boundaries) - 1):
            x1 = boundaries[i]
            x2 = boundaries[i+1]
            
            # Reject columns narrower than 25 pixels
            if x2 - x1 >= 25: 
                col_bbox = GridBoundingBox(x=tx + x1, y=ty, width=x2 - x1, height=th)
                columns.append(ColumnModel(
                    column_id=f"{table_id}_col_{col_idx:03d}",
                    parent_table=table_id,
                    col_index=col_idx,
                    bbox=col_bbox
                ))
                col_idx += 1
                
        return columns
