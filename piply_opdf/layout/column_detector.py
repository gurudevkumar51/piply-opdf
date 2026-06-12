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
        
        thresh = cv2.adaptiveThreshold(
            roi_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4
        )
        
        h, w = thresh.shape
        if h == 0 or w == 0:
            return []
            
        h_page, w_page = gray.shape
        
        # 1. Detect explicit vertical lines
        # Use a thickness of 1 and a safe height threshold that won't delete valid segments
        # that are broken by horizontal row lines. 40 pixels is usually safe for 300 DPI.
        v_kernel_size = max(20, min(60, h_page // 50)) 
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
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
        
        # 3. Filter gutters based on minimum width to prevent word gaps from becoming columns
        whitespace_boundaries = []
        
        # A true column gutter is usually at least 15-20 pixels wide at 300 DPI.
        # Gaps between words are typically 5-15 pixels.
        min_gutter_width = max(15, w // 100)
        
        for g_start, g_end in gutters:
            if g_end - g_start >= min_gutter_width:
                # Check if there is an explicit grid line associated with this gutter
                # A grid line is associated if it's anywhere inside the gutter or close to its edges
                has_grid_line = False
                for lb in line_boundaries:
                    if g_start - 15 <= lb <= g_end + 15:
                        has_grid_line = True
                        break
                
                if not has_grid_line:
                    mid = (g_start + g_end) // 2
                    whitespace_boundaries.append(mid)
                    
        boundaries = line_boundaries + whitespace_boundaries
        boundaries.sort()
        
        # Merge boundaries that are very close to each other (< 15px) 
        # to prevent micro-columns, but preserve actual thin columns
        merged_b = []
        for b in boundaries:
            if not merged_b:
                merged_b.append(b)
            else:
                if b - merged_b[-1] < 15:
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
                # Add a 5-pixel padding to left and right to prevent minor cropping from residual tilt
                padding = 5
                col_x = max(0, tx + x1 - padding)
                
                # Ensure the right padding doesn't exceed the table's total width (or page width)
                # We can just cap it loosely, but since we are just returning a bounding box, 
                # the downstream cropper will handle image boundaries.
                col_w = min(tw - (col_x - tx), (x2 - x1) + (padding * 2))
                
                col_bbox = GridBoundingBox(x=col_x, y=ty, width=col_w, height=th)
                columns.append(ColumnModel(
                    column_id=f"{table_id}_col_{col_idx:03d}",
                    parent_table=table_id,
                    col_index=col_idx,
                    bbox=col_bbox
                ))
                col_idx += 1
                
        return columns
