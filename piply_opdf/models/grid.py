from typing import List, Tuple
from pydantic import BaseModel, Field

class GridBoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int

    @property
    def x2(self) -> int:
        return self.x + self.width

    @property
    def y2(self) -> int:
        return self.y + self.height

    def to_tuple(self) -> Tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

class CellModel(BaseModel):
    cell_id: str
    parent_table: str
    parent_column: str
    row_index: int
    col_index: int
    bbox: GridBoundingBox
    confidence: float = 1.0

class ColumnModel(BaseModel):
    column_id: str
    parent_table: str
    col_index: int
    bbox: GridBoundingBox
    confidence: float = 1.0

class RowModel(BaseModel):
    row_id: str
    parent_table: str
    row_index: int
    bbox: GridBoundingBox
    confidence: float = 1.0

class TableModel(BaseModel):
    table_id: str
    page: int
    bbox: GridBoundingBox
    columns: List[ColumnModel] = Field(default_factory=list)
    rows: List[RowModel] = Field(default_factory=list)
    cells: List[CellModel] = Field(default_factory=list)
    confidence: float = 1.0

# Manifest Models
class TableManifest(BaseModel):
    table_id: str
    page: int
    rows: int
    columns: int
    bbox: Tuple[int, int, int, int]
    confidence: float

class ColumnManifest(BaseModel):
    column_id: str
    parent_table: str
    bbox: Tuple[int, int, int, int]
    confidence: float

class CellManifest(BaseModel):
    cell_id: str
    parent_table: str
    parent_column: str
    row: int
    column: int
    bbox: Tuple[int, int, int, int]
    confidence: float

class BorderlessTableModel(BaseModel):
    id: str
    type: str = "borderless_table"
    page: int
    bbox: Tuple[int, int, int, int]
    columns: List[Tuple[int, int, int, int]] = Field(default_factory=list)
    confidence: float = 1.0
