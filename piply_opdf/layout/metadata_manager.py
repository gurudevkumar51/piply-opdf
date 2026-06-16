import json
from pathlib import Path
from piply_opdf.models.grid import TableModel, TableManifest, ColumnManifest, RowManifest, CellManifest

class MetadataManager:
    """Generates and saves JSON manifests for the grid structure."""
    
    def __init__(self):
        pass
        
    def save_metadata(self, table: TableModel, output_dir: Path):
        """Saves metadata files in the structured format."""
        table_dir = output_dir / f"page_{table.page}" / table.table_id
        table_dir.mkdir(parents=True, exist_ok=True)
        
        # Table Manifest
        table_manifest = TableManifest(
            table_id=table.table_id,
            page=table.page,
            rows=len(table.rows),
            columns=len(table.columns),
            bbox=table.bbox.to_tuple(),
            confidence=table.confidence
        )
        with open(table_dir / "manifest.json", "w") as f:
            json.dump(table_manifest.model_dump(), f, indent=2)
            
        # Columns Manifest
        cols_dir = table_dir / "columns"
        cols_dir.mkdir(parents=True, exist_ok=True)
        cols_manifests = []
        for col in table.columns:
            cols_manifests.append(ColumnManifest(
                column_id=col.column_id,
                parent_table=table.table_id,
                bbox=col.bbox.to_tuple(),
                confidence=col.confidence
            ).model_dump())
        with open(cols_dir / "manifest.json", "w") as f:
            json.dump(cols_manifests, f, indent=2)
            
        # Rows Manifest
        rows_dir = table_dir / "rows"
        rows_dir.mkdir(parents=True, exist_ok=True)
        rows_manifests = []
        for row in table.rows:
            rows_manifests.append(RowManifest(
                row_id=row.row_id,
                parent_table=table.table_id,
                bbox=row.bbox.to_tuple(),
                confidence=row.confidence
            ).model_dump())
        with open(rows_dir / "manifest.json", "w") as f:
            json.dump(rows_manifests, f, indent=2)
            
        # Cells Manifest
        cells_dir = table_dir / "cells"
        cells_dir.mkdir(parents=True, exist_ok=True)
        cells_manifests = []
        for cell in table.cells:
            cells_manifests.append(CellManifest(
                cell_id=cell.cell_id,
                parent_table=table.table_id,
                parent_column=cell.parent_column,
                row=cell.row_index,
                column=cell.col_index,
                bbox=cell.bbox.to_tuple(),
                confidence=cell.confidence
            ).model_dump())
        with open(cells_dir / "manifest.json", "w") as f:
            json.dump(cells_manifests, f, indent=2)
