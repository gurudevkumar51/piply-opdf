from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime

class ComponentBase(BaseModel):
    component_type: str
    page_no: int
    bbox: str
    confidence: float
    manifest_path: Optional[str] = None
    parent_id: Optional[int] = None

class ComponentCreate(ComponentBase):
    pass

class OCRFeedbackBase(BaseModel):
    user_value: str
    is_accepted: bool

class OCRFeedbackResponse(OCRFeedbackBase):
    id: int
    prediction_id: int
    reviewed_at: datetime

    class Config:
        from_attributes = True

class OCRPredictionBase(BaseModel):
    predicted_text: str
    confidence: float

class OCRPredictionResponse(OCRPredictionBase):
    id: int
    component_id: int
    created_at: datetime
    feedback: List[OCRFeedbackResponse] = []

    class Config:
        from_attributes = True

class ComponentResponse(ComponentBase):
    id: int
    document_id: int
    predictions: List[OCRPredictionResponse] = []

    class Config:
        from_attributes = True

class DocumentBase(BaseModel):
    filename: str
    file_type: str
    page_count: int
    status: str

class DocumentCreate(DocumentBase):
    pass

class DocumentResponse(DocumentBase):
    id: int
    uploaded_at: datetime

    class Config:
        from_attributes = True

class ProcessResponse(BaseModel):
    job_id: str
    status: str
    message: str

class FeedbackUpdate(BaseModel):
    user_value: Optional[str] = None
    is_accepted: bool = True

class BulkFeedbackUpdate(BaseModel):
    prediction_ids: List[int]
    is_accepted: bool = True
