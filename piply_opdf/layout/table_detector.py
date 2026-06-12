import cv2
import numpy as np
from typing import List
from piply_opdf.models.grid import GridBoundingBox

class TableDetector:
    """Detects strictly valid table regions and rejects false page-level grids."""
    
    def __init__(self):
        pass
        
    def detect_tables(self, image: np.ndarray) -> List[GridBoundingBox]:
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image.copy()
            
        h, w = gray.shape[:2]

        # 1. Adaptive Thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4
        )

        # 2. Extract Horizontal and Vertical Lines
        h_len = max(w // 40, 30)
        v_len = max(h // 40, 30)
        
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        horizontal_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        vertical_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)

        # 3. Merge to Grid Mask
        grid_mask = cv2.bitwise_or(horizontal_mask, vertical_mask)
        
        # 4. Standard small dilation to connect broken corners within a single cell/row
        dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        grid_mask_dilated = cv2.dilate(grid_mask, dilation_kernel, iterations=2)

        # 5. Detect raw fragments (rows, cells, or partial borders)
        contours, _ = cv2.findContours(grid_mask_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        fragments = []
        for c in contours:
            x, y, w_c, h_c = cv2.boundingRect(c)
            # Filter out tiny noise specks
            if w_c > 50 and h_c > 10:
                fragments.append((x, y, w_c, h_c, c))
                
        # Sort fragments strictly top to bottom
        fragments.sort(key=lambda f: f[1])
        
        # 6. Cluster fragments into Unified Tables
        # A fragment belongs to a cluster if it overlaps horizontally and is close vertically
        MAX_VERTICAL_GAP = h * 0.05  # Max 5% of page height gap between rows
        MIN_HORIZONTAL_OVERLAP = 0.2  # Must share at least 20% horizontal bounds
        
        clusters = []
        for frag in fragments:
            fx, fy, fw, fh, fc = frag
            added_to_cluster = False
            
            for cluster in clusters:
                cx, cy, cw, ch = cluster["bbox"]
                
                # Check vertical proximity (is the new fragment just below the cluster?)
                # We measure from the bottom of the cluster to the top of the fragment
                cluster_bottom = cy + ch
                if fy - cluster_bottom <= MAX_VERTICAL_GAP and fy + fh >= cy:
                    
                    # Check horizontal overlap
                    overlap_left = max(fx, cx)
                    overlap_right = min(fx + fw, cx + cw)
                    overlap_width = overlap_right - overlap_left
                    
                    if overlap_width > 0:
                        # Calculate overlap ratio relative to the smaller width
                        min_width = min(fw, cw)
                        max_width = max(fw, cw)
                        
                        # Only group if they have somewhat similar widths (e.g. > 70% of each other)
                        # This prevents wide tables from swallowing short header/footer lines
                        width_similarity = min_width / max_width
                        
                        if (overlap_width / min_width) >= MIN_HORIZONTAL_OVERLAP and width_similarity > 0.7:
                            # Merge fragment into cluster
                            new_x = min(cx, fx)
                            new_y = min(cy, fy)
                            new_w = max(cx + cw, fx + fw) - new_x
                            new_h = max(cy + ch, fy + fh) - new_y
                            cluster["bbox"] = (new_x, new_y, new_w, new_h)
                            cluster["contours"].append(fc)
                            added_to_cluster = True
                            break
                            
            if not added_to_cluster:
                clusters.append({
                    "bbox": (fx, fy, fw, fh),
                    "contours": [fc]
                })

        # 7. Validate Clusters into Tables
        tables = []
        for cluster in clusters:
            x, y, w_c, h_c = cluster["bbox"]
            
            # Basic size filtering. Allow shorter fragments (2% page height) for multi-page continuations
            if w_c < w * 0.1 or h_c < h * 0.02:
                continue
                
            # Table Confidence Scoring
            rect_area = w_c * h_c
            
            # Calculate composite contour area for the cluster
            contour_area = sum(cv2.contourArea(c) for c in cluster["contours"])
            
            # Combine all points to find hull
            all_pts = np.vstack(cluster["contours"])
            hull = cv2.convexHull(all_pts)
            hull_area = cv2.contourArea(hull)
            
            if hull_area == 0:
                continue
                
            rectangularity = contour_area / hull_area
            
            # Line density inside the bounding box
            roi = grid_mask[y:y+h_c, x:x+w_c]
            line_pixels = cv2.countNonZero(roi)
            line_density = line_pixels / rect_area
            
            # We don't want the density to be too high (solid black block) or too low (empty box)
            if line_density < 0.01 or line_density > 0.3:
                continue
                
            # Score
            # Tables tend to have high rectangularity and a reasonable line density.
            table_confidence = (rectangularity * 0.6) + (min(line_density * 10, 1.0) * 0.4)
            
            # Allow sparse table fragments by dropping confidence threshold to 0.50
            if table_confidence >= 0.50:
                # Find tighter bounds using just the non-zero pixels inside the ROI
                pts = cv2.findNonZero(roi)
                if pts is not None:
                    rx, ry, rw, rh = cv2.boundingRect(pts)
                    
                    # Apply configurable padding to ensure borders and first/last rows are not cropped
                    TOP_PADDING = 10
                    BOTTOM_PADDING = 10
                    LEFT_PADDING = 5
                    RIGHT_PADDING = 5
                    
                    new_x = max(0, x + rx - LEFT_PADDING)
                    new_y = max(0, y + ry - TOP_PADDING)
                    new_w = min(w - new_x, rw + LEFT_PADDING + RIGHT_PADDING)
                    new_h = min(h - new_y, rh + TOP_PADDING + BOTTOM_PADDING)
                    
                    tables.append(GridBoundingBox(x=new_x, y=new_y, width=new_w, height=new_h))

        # Sort top to bottom
        tables.sort(key=lambda b: b.y)
        return tables
