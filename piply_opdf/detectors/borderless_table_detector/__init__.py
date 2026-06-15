import fitz
from typing import List, Tuple
from piply_opdf.models.grid import BorderlessTableModel, GridBoundingBox

class BorderlessTableDetector:
    """
    Detects borderless tables by extracting PyMuPDF word coordinates and 
    clustering them into rows and columns based on alignment.
    """
    def __init__(self):
        # We output coordinates in 300 DPI to match the rest of the pipeline
        self.target_dpi = 300
        self.scale = self.target_dpi / 72.0

    def detect_tables(self, doc_path: str, page_num: int, existing_tables: List[GridBoundingBox]) -> List[BorderlessTableModel]:
        """
        Detect borderless tables on the specified page.
        Ignores regions already covered by existing_tables (bordered tables).
        """
        doc = fitz.open(doc_path)
        page = doc[page_num - 1]
        
        words = page.get_text("words")
        if not words:
            return []
            
        # 1. Collect word boxes
        boxes = []
        for w in words:
            x0, y0, x1, y1 = [v * self.scale for v in w[:4]]
            text = w[4]
            # Ignore empty or tiny noise
            if x1 - x0 > 2 and y1 - y0 > 2 and text.strip():
                # Check if it overlaps with an existing bordered table
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                in_existing = False
                for tb in existing_tables:
                    if tb.x <= cx <= tb.x + tb.width and tb.y <= cy <= tb.y + tb.height:
                        in_existing = True
                        break
                
                if not in_existing:
                    boxes.append((x0, y0, x1, y1, text))
                    
        if not boxes:
            return []
            
        # 2. Cluster into lines based on Y center
        boxes.sort(key=lambda b: (b[1] + b[3])/2)
        
        rows = []
        current_row = []
        # Max difference in center Y to be considered same row
        y_threshold = 15
        
        for b in boxes:
            cy = (b[1] + b[3]) / 2
            if not current_row:
                current_row.append(b)
            else:
                prev_cy = (current_row[0][1] + current_row[0][3]) / 2
                if abs(cy - prev_cy) < y_threshold:
                    current_row.append(b)
                else:
                    rows.append(current_row)
                    current_row = [b]
        if current_row:
            rows.append(current_row)
            
        # 3. Identify Table Rows (rows with >= 3 columns)
        table_rows = []
        x_threshold = 30 # minimum gap to separate columns
        
        for r in rows:
            r.sort(key=lambda b: b[0])
            cols = []
            current_col = []
            
            for b in r:
                if not current_col:
                    current_col.append(b)
                else:
                    if b[0] - max(c[2] for c in current_col) > 40:
                        cols.append(current_col)
                        current_col = [b]
                    else:
                        current_col.append(b)
            if current_col:
                cols.append(current_col)
                
            if len(cols) >= 3:
                min_y = min(b[1] for b in r)
                max_y = max(b[3] for b in r)
                min_x = min(b[0] for b in r)
                max_x = max(b[2] for b in r)
                
                col_bounds = []
                for c in cols:
                    c_min_x = min(b[0] for b in c)
                    c_max_x = max(b[2] for b in c)
                    col_bounds.append((c_min_x, c_max_x))
                    
                table_rows.append({
                    "y0": min_y,
                    "y1": max_y,
                    "x0": min_x,
                    "x1": max_x,
                    "cols": len(cols),
                    "col_bounds": col_bounds
                })
                
        # 4. Group consecutive table rows into Borderless Tables
        tables = []
        current_table = []
        max_row_gap = 150 # Max vertical gap between rows in a table
        
        for tr in table_rows:
            if not current_table:
                current_table.append(tr)
            else:
                prev_y1 = current_table[-1]['y1']
                
                # Check for significant column change to split distinct tables
                from collections import Counter
                col_counts = [r['cols'] for r in current_table]
                most_common_cols = Counter(col_counts).most_common(1)[0][0]
                
                is_different_structure = abs(tr['cols'] - most_common_cols) >= 2
                gap = tr['y0'] - prev_y1
                
                if gap >= max_row_gap:
                    # Definitely split if gap is huge
                    if len(current_table) >= 3:
                        tables.append(current_table)
                    current_table = [tr]
                elif is_different_structure and gap >= 40:
                    # Split if structure changes AND there's a moderate gap
                    if len(current_table) >= 3:
                        tables.append(current_table)
                    current_table = [tr]
                else:
                    # Keep accumulating (either same structure, or different structure but tightly packed)
                    current_table.append(tr)
                    
        if len(current_table) >= 3:
            tables.append(current_table)
            
        # 5. Output Metadata
        results = []
        for i, t in enumerate(tables):
            y0 = int(min(tr['y0'] for tr in t))
            y1 = int(max(tr['y1'] for tr in t))
            x0 = int(min(tr['x0'] for tr in t))
            x1 = int(max(tr['x1'] for tr in t))
            
            from collections import Counter
            most_common_cols = Counter(tr['cols'] for tr in t).most_common(1)[0][0]
            
            all_col_bounds = [tr['col_bounds'] for tr in t if tr['cols'] == most_common_cols]
            
            final_cols = []
            if all_col_bounds:
                for col_idx in range(most_common_cols):
                    c_min = min(row_cols[col_idx][0] for row_cols in all_col_bounds)
                    c_max = max(row_cols[col_idx][1] for row_cols in all_col_bounds)
                    final_cols.append([int(c_min), int(c_max)])
            
            # Add padding to table bounds
            padding_x = 40
            padding_y = 50
            x0 = max(0, x0 - padding_x)
            y0 = max(0, y0 - padding_y)
            x1 += padding_x
            y1 += padding_y
            
            # Expand columns to include spilling text, but ignore spanning text
            import copy
            original_cols = copy.deepcopy(final_cols)
            
            all_words_in_table = [b for b in boxes if y0 <= (b[1]+b[3])/2 <= y1]
            for w in all_words_in_table:
                wx0, wy0, wx1, wy1, _ = w
                wcx = (wx0 + wx1) / 2
                
                closest_i = -1
                min_dist = float('inf')
                for idx, (c_min, c_max) in enumerate(original_cols):
                    ccx = (c_min + c_max) / 2
                    dist = abs(wcx - ccx)
                    if dist < min_dist:
                        min_dist = dist
                        closest_i = idx
                        
                if closest_i != -1:
                    # Check against original bounds to see if it intrudes into neighboring lanes
                    spans_left = closest_i > 0 and wx0 < original_cols[closest_i - 1][1]
                    spans_right = closest_i < len(original_cols) - 1 and wx1 > original_cols[closest_i + 1][0]
                    
                    if not spans_left and not spans_right:
                        final_cols[closest_i][0] = min(final_cols[closest_i][0], wx0)
                        final_cols[closest_i][1] = max(final_cols[closest_i][1], wx1)
            
            final_cols.sort(key=lambda c: c[0])
            
            # Reject false positives where "columns" overlap heavily (e.g., bulleted lists or multi-column text)
            is_valid_table = True
            for col_idx in range(len(final_cols) - 1):
                prev_max = final_cols[col_idx][1]
                next_min = final_cols[col_idx+1][0]
                if prev_max - next_min > 100:
                    is_valid_table = False
                    break
            
            if not is_valid_table:
                pass # continue
                
            padded_cols = []
            for col_idx in range(len(final_cols)):
                c_min, c_max = final_cols[col_idx]
                
                if col_idx == 0:
                    left_bound = c_min - 20
                else:
                    prev_max = final_cols[col_idx-1][1]
                    if prev_max >= c_min:
                        # Text overlaps physically! Allow the column image to overlap so we don't chop text.
                        left_bound = c_min - 10
                    else:
                        # Clean whitespace gap, split it down the middle
                        left_bound = (prev_max + c_min) / 2
                        
                if col_idx == len(final_cols) - 1:
                    right_bound = c_max + 20
                else:
                    next_min = final_cols[col_idx+1][0]
                    if c_max >= next_min:
                        # Text overlaps physically! Allow the column image to overlap so we don't chop text.
                        right_bound = c_max + 10
                    else:
                        right_bound = (c_max + next_min) / 2
                
                left_bound = max(0, left_bound)
                
                padded_cols.append((
                    int(left_bound),
                    y0,
                    int(right_bound - left_bound),
                    y1 - y0
                ))
            
            table_rows_extracted = []
            for tr in t:
                r_y0 = int(max(0, tr['y0'] - 2))
                r_y1 = int(tr['y1'] + 2)
                table_rows_extracted.append((x0, r_y0, x1 - x0, r_y1 - r_y0))
                
            results.append(BorderlessTableModel(
                id=f"borderless_table_{i+1:03d}",
                page=page_num,
                bbox=(x0, y0, x1 - x0, y1 - y0),
                columns=padded_cols,
                rows=table_rows_extracted,
                confidence=0.85
            ))
            
        return results
