from sqlalchemy import Column, Integer, String, Float, Boolean, ForeignKey, DateTime, Text
from sqlalchemy.orm import relationship
import datetime
from .database import Base

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_type = Column(String)
    uploaded_at = Column(DateTime, default=datetime.datetime.utcnow)
    page_count = Column(Integer, default=0)
    status = Column(String, default="uploaded") # uploaded, processing, completed, error
    ocr_engine = Column(String, default="paddle")

    components = relationship("Component", back_populates="document", cascade="all, delete-orphan")

class Component(Base):
    __tablename__ = "components"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    component_type = Column(String, index=True) # TABLE, BORDERLESS_TABLE, ROW, COLUMN, CELL, TITLE, HEADER, FOOTER, KEY_VALUE, PARAGRAPH, WORD
    page_no = Column(Integer)
    bbox = Column(String) # JSON string [x0, y0, x1, y1]
    confidence = Column(Float, default=1.0)
    manifest_path = Column(String, nullable=True) # Optional path to sub-manifest (e.g. table_001_manifest.json)
    parent_id = Column(Integer, ForeignKey("components.id"), nullable=True) # For tree structures (Table -> Row -> Cell)
    phash = Column(String(64), nullable=True) # Perceptual hash for grouping identical cells

    document = relationship("Document", back_populates="components")
    predictions = relationship("OCRPrediction", back_populates="component", cascade="all, delete-orphan")
    children = relationship("Component", backref="parent", remote_side=[id])

class OCRPrediction(Base):
    __tablename__ = "ocr_predictions"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("components.id"))
    predicted_text = Column(Text)
    confidence = Column(Float)
    source = Column(String, default="ocr")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    component = relationship("Component", back_populates="predictions")
    feedback = relationship("OCRFeedback", back_populates="prediction", cascade="all, delete-orphan")

class OCRFeedback(Base):
    __tablename__ = "ocr_feedback"

    id = Column(Integer, primary_key=True, index=True)
    prediction_id = Column(Integer, ForeignKey("ocr_predictions.id"))
    user_value = Column(Text)
    is_accepted = Column(Boolean, default=False)
    reviewed_at = Column(DateTime, default=datetime.datetime.utcnow)
    source = Column(String, default="human") # human trust source for accepted feedback

    prediction = relationship("OCRPrediction", back_populates="feedback")
