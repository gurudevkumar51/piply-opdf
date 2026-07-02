import os
import json
import logging
from typing import Dict, Any

from piply_opdf.knowledge.registry import KnowledgeRegistry
from piply_opdf.database.knowledge_models import OCRKnowledgeEntry
from piply_opdf.modules.feature_extractor import DefaultFeatureExtractor

logger = logging.getLogger(__name__)

# Global registry instance, can be loaded once at startup
_registry = None

def get_registry() -> KnowledgeRegistry:
    global _registry
    if _registry is None:
        _registry = KnowledgeRegistry()
        _registry.load_all()
    return _registry

def register_correction(image_path: str, correct_text: str, source: str = "human", component_type: str = "CELL") -> bool:
    """
    Registers a human correction directly into the Knowledge Base.
    Generates hashes and image features automatically.
    """
    if not os.path.exists(image_path):
        logger.error(f"Cannot register correction, image not found: {image_path}")
        return False
        
    extractor = DefaultFeatureExtractor()
    features = extractor.extract_features(image_path)
    
    if not features or "phash" not in features:
        logger.error(f"Failed to extract features for: {image_path}")
        return False
        
    registry = get_registry()
    session = registry.get_default_session()
    
    try:
        phash = features["phash"]
        
        # Check if it already exists
        existing = session.query(OCRKnowledgeEntry).filter_by(phash=phash).first()
        if existing:
            existing.text_value = correct_text
            existing.source = source
            existing.confidence = 1.0
            existing.component_type = component_type
            
            # Preserve existing ML fields if not provided by the extractor
            if features.get("cluster_id") is not None:
                existing.cluster_id = features.get("cluster_id")
                
            if features.get("quality_score") is not None:
                existing.quality_score = features.get("quality_score")
            if features.get("rotation_angle") is not None:
                existing.rotation_angle = features.get("rotation_angle")
            if features.get("foreground_ratio") is not None:
                existing.foreground_ratio = features.get("foreground_ratio")
            if features.get("entropy") is not None:
                existing.entropy = features.get("entropy")
            if features.get("skeleton_length") is not None:
                existing.skeleton_length = features.get("skeleton_length")
        else:
            entry = OCRKnowledgeEntry(
                phash=phash,
                text_value=correct_text,
                source=source,
                confidence=1.0,
                component_type=component_type,
                cluster_id=features.get("cluster_id"),
                quality_score=features.get("quality_score", 1.0),
                rotation_angle=features.get("rotation_angle", 0.0),
                foreground_ratio=features.get("foreground_ratio", 0.0),
                entropy=features.get("entropy", 0.0),
                skeleton_length=features.get("skeleton_length", 0),
                dhash=features.get("dhash", ""),
                ahash=features.get("ahash", ""),
                width=features.get("width", 0),
                height=features.get("height", 0),
                aspect_ratio=features.get("aspect_ratio", 0.0),
                edge_density=features.get("edge_density", 0.0),
                stroke_density=features.get("stroke_density", 0.0),
                connected_components=features.get("connected_components", 0),
                histogram_features=json.dumps(features.get("histogram_features", [])),
                projection_profiles=json.dumps(features.get("projection_profiles", {})),
                hu_moments=json.dumps(features.get("hu_moments", [])),
                hog_features=json.dumps(features.get("hog_features", []))
            )
            session.add(entry)
            
        session.commit()
        # Copy image for knowledge preview
        import shutil
        images_dir = os.path.join(registry.knowledge_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        target_img_path = os.path.join(images_dir, f"{phash}.png")
        if not os.path.exists(target_img_path):
            shutil.copy2(image_path, target_img_path)
            
        # Refresh registry index in-memory
        registry.hash_index[phash] = "piply_opdf_knowledge-001.db"
        logger.info(f"Registered correction for {phash}: '{correct_text}'")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to register correction: {e}")
        return False
    finally:
        session.close()
