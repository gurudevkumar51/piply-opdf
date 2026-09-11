from typing import Any, Dict, List, Tuple
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
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ColumnModel(BaseModel):
    column_id: str
    parent_table: str
    col_index: int
    bbox: GridBoundingBox
    confidence: float = 1.0
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RowModel(BaseModel):
    row_id: str
    parent_table: str
    row_index: int
    bbox: GridBoundingBox
    confidence: float = 1.0
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class TableModel(BaseModel):
    table_id: str
    page: int
    bbox: GridBoundingBox
    columns: List[ColumnModel] = Field(default_factory=list)
    rows: List[RowModel] = Field(default_factory=list)
    cells: List[CellModel] = Field(default_factory=list)
    confidence: float = 1.0
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

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
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CellManifest(BaseModel):
    cell_id: str
    parent_table: str
    parent_column: str
    row: int
    column: int
    bbox: Tuple[int, int, int, int]
    confidence: float
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class RowManifest(BaseModel):
    row_id: str
    parent_table: str
    bbox: Tuple[int, int, int, int]
    confidence: float
    #: Free-form extras. Carries the itemised confidence evidence under
    #: ``metadata["confidence"]``, which is how it reaches the database
    #: without every caller having to know about it.
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BorderlessTableModel(BaseModel):
    id: str
    type: str = "borderless_table"
    page: int
    bbox: Tuple[int, int, int, int]
    columns: List[Tuple[int, int, int, int]] = Field(default_factory=list)
    rows: List[Tuple[int, int, int, int]] = Field(default_factory=list)
    cells: List[Any] = Field(default_factory=list)
    confidence: float = 1.0
    #: How strongly each row boundary is a boundary, in row order, from
    #: `piply_opdf.structure`. A wrapped description folded back into its row
    #: leaves fewer, better-evidenced rows than the line count suggests, and a
    #: low value here is a split worth a person's glance.
    row_confidence: List[float] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
