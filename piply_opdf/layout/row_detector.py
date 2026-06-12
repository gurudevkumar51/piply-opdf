import cv2
import numpy as np
from typing import List, Dict
from piply_opdf.models.grid import GridBoundingBox, ColumnModel

class RowDetector:
    """Detects row candidates independently for each column using horizontal projection of text/borders."""
    
    def __init__(self):
        pass
        
    def detect_row_candidates(self, image: np.ndarray, columns: List[ColumnModel]) -> Dict[str, List[int]]:
        """
        Detects row dividers independently for each column by projecting text bands and borders.
        Returns a dictionary mapping column_id to a list of row divider Y-coordinates.
        """
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4
        )
        
        candidates = {}
        for col in columns:
            cx, cy, cw, ch = col.bbox.to_tuple()
            roi_thresh = thresh[cy:cy+ch, cx:cx+cw]
            
            # Compute full horizontal projection (text + borders)
            h_proj = np.sum(roi_thresh / 255.0, axis=1)
            
            row_dividers = [0]
            in_blank = True
            start_blank = 0
            
            for i in range(len(h_proj)):
                # If there are very few pixels, we are in a blank row divider area
                if h_proj[i] < cw * 0.05:
                    if not in_blank:
                        in_blank = True
                        start_blank = i
                else:
                    if in_blank:
                        in_blank = False
                        # The divider is the middle of the blank space
                        row_dividers.append((start_blank + i) // 2)
                        
            if in_blank:
                row_dividers.append((start_blank + len(h_proj)) // 2)
            row_dividers.append(ch)
            
            # Clean dividers
            res = [row_dividers[0]]
            for d in row_dividers[1:]:
                if d - res[-1] > 10:
                    res.append(d)
                else:
                    res[-1] = (res[-1] + d) // 2
                    
            candidates[col.column_id] = res
            
        return candidates
