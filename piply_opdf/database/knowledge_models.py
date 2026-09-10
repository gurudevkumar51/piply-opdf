from sqlalchemy import Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship
import datetime

KnowledgeBase = declarative_base()

class OCRCluster(KnowledgeBase):
    """
    Parent entity representing a single logical concept or normalized text group.
    This is backed by a SQL VIEW.
    """
    __tablename__ = "ocr_cluster"

    id = Column(Integer, primary_key=True) # It's a view, so primary_key is just for SQLAlchemy mapping
    text_value = Column(String)
    representative_phash = Column(String)
    created_at = Column(DateTime)
    status = Column(String)
    sample_size = Column(Integer)

class OCRKnowledgeEntry(KnowledgeBase):
    """
    Unified Knowledge Record stored inside a piply_opdf_knowledge-*.db file.
    Represents an exact piece of verified knowledge.
    """
    __tablename__ = "ocr_knowledge_base"

    id = Column(Integer, primary_key=True, index=True)
    phash = Column(String, unique=True, index=True)  # pHash
    cluster_id = Column(Integer, index=True)
    component_type = Column(String, index=True)
    quality_score = Column(Float)
    rotation_angle = Column(Float)
    foreground_ratio = Column(Float)
    entropy = Column(Float)
    skeleton_length = Column(Integer)
    
    text_value = Column(Text)
    confidence = Column(Float, default=1.0)
    source = Column(String)  # 'human', 'manual_import', etc.
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Mathematical Features for Similarity / ML Training
    dhash = Column(String)
    ahash = Column(String)
    width = Column(Integer)
    height = Column(Integer)
    aspect_ratio = Column(Float)
    edge_density = Column(Float)
    stroke_density = Column(Float)
    connected_components = Column(Integer)
    
    # JSON-encoded string arrays for complex math
    histogram_features = Column(Text)
    projection_profiles = Column(Text)
    hu_moments = Column(Text)
    hog_features = Column(Text)
