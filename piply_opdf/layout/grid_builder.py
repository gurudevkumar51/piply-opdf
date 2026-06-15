from typing import List, Dict
from piply_opdf.models.grid import TableModel, ColumnModel, RowModel, CellModel, GridBoundingBox

import cv2
import numpy as np

class GridBuilder:
    """Assembles the final TableModel using Consensus Row Detection."""
    
    def __init__(self, consensus_threshold: float = 0.5):
        self.consensus_threshold = consensus_threshold
        
    def build_grid(self, image: np.ndarray, table_id: str, table_bbox: GridBoundingBox, page_num: int, columns: List[ColumnModel], row_candidates: Dict[str, List[int]]) -> TableModel:
        """
        Builds the grid structure using consensus voting for row dividers.
        """
        # Collect all unique row dividers across all columns
        all_dividers = []
        for divs in row_candidates.values():
            all_dividers.extend(divs)
            
        all_dividers.sort()
        
        # Cluster nearby dividers
        if not all_dividers:
            return TableModel(table_id=table_id, page=page_num, bbox=table_bbox)
            
        clusters = [[all_dividers[0]]]
        for d in all_dividers[1:]:
            if d - clusters[-1][-1] <= 15: # 15px threshold for clustering
                clusters[-1].append(d)
            else:
                clusters.append([d])
                
        consensus_dividers = []
        num_cols = len(columns)
        
        # We also want to guarantee top (0) and bottom (th) are included
        th = table_bbox.height
        
        for c in clusters:
            avg_d = int(sum(c) / len(c))
            # Voting: how many columns had a divider near this average?
            votes = 0
            for col_id, divs in row_candidates.items():
                if any(abs(avg_d - d) <= 15 for d in divs):
                    votes += 1
                    
            # If majority agrees, keep it (or if it's the very top/bottom boundary)
            if votes >= num_cols * self.consensus_threshold or avg_d < 15 or (th - avg_d) < 15:
                consensus_dividers.append(avg_d)
                
        # Make sure 0 and th are present
        if not consensus_dividers:
            consensus_dividers = [0, th]
        else:
            if consensus_dividers[0] > 25:
                consensus_dividers.insert(0, 0)
            else:
                consensus_dividers[0] = 0
                
            if consensus_dividers[-1] < th - 25:
                consensus_dividers.append(th)
            else:
                consensus_dividers[-1] = th
            
        # Ensure strict monotonicity and fix top/bottom perfectly
        consensus_dividers[0] = 0
        consensus_dividers[-1] = th
        
        # Clean up any that are too close after consensus
        final_dividers = [consensus_dividers[0]]
        for d in consensus_dividers[1:]:
            if d - final_dividers[-1] > 35:
                final_dividers.append(d)
        
        # Ensure last divider is th
        if final_dividers[-1] != th:
            final_dividers[-1] = th
                
        # Create RowModels
        rows = []
        row_idx = 0
        tx, ty, tw, _ = table_bbox.to_tuple()
        
        for i in range(len(final_dividers) - 1):
            y1, y2 = final_dividers[i], final_dividers[i+1]
            h = y2 - y1
            if h > 35:
                # Top margin artifact: first row is usually empty space if < 60px
                if len(rows) == 0 and h < 60:
                    continue
                # Bottom margin artifact: last row is usually empty space if < 60px
                if i == len(final_dividers) - 2 and h < 60:
                    continue
                    
                row_bbox = GridBoundingBox(x=tx, y=ty + y1, width=tw, height=h)
                rows.append(RowModel(
                    row_id=f"{table_id}_row_{row_idx}",
                    parent_table=table_id,
                    row_index=row_idx,
                    bbox=row_bbox
                ))
                row_idx += 1
                
        # Create CellModels
        cells = []
        for r in rows:
            for c in columns:
                cx, cy, cw, ch = c.bbox.to_tuple()
                rx, ry, rw, rh = r.bbox.to_tuple()
                
                # Intersection of column and row is the cell
                cell_x = cx
                cell_y = ry
                cell_w = cw
                cell_h = rh
                
                cell_bbox = GridBoundingBox(x=cell_x, y=cell_y, width=cell_w, height=cell_h)
                
                cells.append(CellModel(
                    cell_id=f"{table_id}_r{r.row_index}_c{c.col_index}",
                    parent_table=table_id,
                    parent_column=c.column_id,
                    row_index=r.row_index,
                    col_index=c.col_index,
                    bbox=cell_bbox
                ))
                
        return TableModel(
            table_id=table_id,
            page=page_num,
            bbox=table_bbox,
            columns=columns,
            rows=rows,
            cells=cells
        )
