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

    components = relationship("Component", back_populates="document", cascade="all, delete-orphan")

class Component(Base):
    __tablename__ = "components"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"))
    component_type = Column(String, index=True) # TABLE, BORDERLESS_TABLE, ROW, COL, CELL, TITLE, HEADER, FOOTER, PARAGRAPH
    page_no = Column(Integer)
    bbox = Column(String) # JSON string [x0, y0, x1, y1]
    confidence = Column(Float, default=1.0)
    manifest_path = Column(String, nullable=True) # Optional path to sub-manifest (e.g. table_001_manifest.json)
    parent_id = Column(Integer, ForeignKey("components.id"), nullable=True) # For tree structures (Table -> Row -> Cell)

    document = relationship("Document", back_populates="components")
    predictions = relationship("OCRPrediction", back_populates="component", cascade="all, delete-orphan")
    image_features = relationship("ImageFeature", back_populates="component", uselist=False, cascade="all, delete-orphan")
    children = relationship("Component", backref="parent", remote_side=[id])

class OCRPrediction(Base):
    __tablename__ = "ocr_predictions"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("components.id"))
    predicted_text = Column(Text)
    confidence = Column(Float)
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

    prediction = relationship("OCRPrediction", back_populates="feedback")

class OCRKnowledgeBase(Base):
    __tablename__ = "ocr_knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    image_hash = Column(String, unique=True, index=True)
    text_value = Column(Text)
    confidence = Column(Float, default=1.0)
    source = Column(String) # 'human', 'paddle', 'tesseract', 'voted'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class ImageFeature(Base):
    __tablename__ = "image_features"

    id = Column(Integer, primary_key=True, index=True)
    component_id = Column(Integer, ForeignKey("components.id"), unique=True)
    phash = Column(String)
    dhash = Column(String)
    ahash = Column(String)
    width = Column(Integer)
    height = Column(Integer)
    aspect_ratio = Column(Float)
    edge_density = Column(Float)
    histogram_features = Column(Text) # JSON string array

    component = relationship("Component", back_populates="image_features")

class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    image_hash = Column(String, index=True) # pHash for quick lookup
    text_value = Column(Text)
    source = Column(String) # user_feedback, manual
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
