import os
import cv2
import json
import numpy as np
import imagehash
from typing import Dict, Any, Optional, Tuple
class PipelineOrchestrator:
    """
    Implements the 7-Level ML Pipeline.
    """
    def __init__(self):
        from piply_opdf.feedback import get_registry
        self.registry = get_registry()

    def calculate_euclidean(self, vec1, vec2):
        if not vec1 or not vec2: return float('inf')
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        if v1.shape != v2.shape: return float('inf')
        return np.linalg.norm(v1 - v2)

    def ssim(self, img1_path, img2_path):
        if not img1_path or not img2_path or not os.path.exists(img1_path) or not os.path.exists(img2_path):
            return 0.0
        try:
            from skimage.metrics import structural_similarity as compare_ssim
            i1 = cv2.imread(img1_path, cv2.IMREAD_GRAYSCALE)
            i2 = cv2.imread(img2_path, cv2.IMREAD_GRAYSCALE)
            # Resize i2 to i1's dimensions for SSIM
            i2 = cv2.resize(i2, (i1.shape[1], i1.shape[0]))
            score, _ = compare_ssim(i1, i2, full=True)
            return max(0.0, score)
        except:
            return 0.0

    def find_match(self, image_path: str, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        phash_str = features.get('phash')
        if not phash_str:
            return None

        # Level 1: Exact Hash Match
        exact = self.registry.search_exact(features)
        if exact and exact.text_value is not None:
            return {"text": exact.text_value, "confidence": 1.0, "source": "exact_match"}

        # Level 2: Near Hash Match
        if phash_str:
            near = self.registry.search_near_hash(phash_str, max_distance=4)
            if near and near.text_value is not None:
                return {"text": near.text_value, "confidence": 1.0, "source": "near_match"}

        # User requested to remove ML CACHE (near hash, structural similarity, heuristics)
        return None


    def run_level_5(self, image_path: str, features: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # Level 5: Rule-Based Heuristics & Router
        aspect = features.get("aspect_ratio", 0)
        ccs = features.get("connected_components", 0)
        edge_density = features.get("edge_density", 0)
        stroke_density = features.get("stroke_density", 0)
        
        # Heuristic 1: Empty Cell
        if edge_density < 0.001 and ccs <= 1 and stroke_density < 0.001:
            return {"text": "", "confidence": 0.99, "source": "heuristic_empty"}

        # Heuristic 2: Dash or Hyphen (-)
        # Very low aspect ratio (wide and short), 1 CC, low stroke density
        if aspect > 3.0 and ccs == 1 and 0.01 < stroke_density < 0.15:
            # We can run a quick check or just route it to the Symbols model
            pass

        # Heuristic 3: Checkmark / Tick (✓)
        # Roughly square aspect ratio, 1 CC, specific Hu Moments
        if 0.7 < aspect < 1.3 and ccs == 1:
            # Route to Symbols Model
            model_type = "symbols"
        elif ccs > 5 and aspect > 2.0:
            # Likely Printed or Handwritten Text or Date
            # Further classify based on projection profiles
            model_type = "printed"
        else:
            model_type = "numeric"

        # Specialized ML Models (Level 5.5)
        text, conf = self.run_specialized_model(model_type, features)
        if text is not None and conf > 0.95:
            return {"text": text, "confidence": conf, "source": f"ml_{model_type}"}
        
        return None

    def run_specialized_model(self, model_type: str, features: Dict[str, Any]) -> Tuple[Optional[str], float]:
        """
        Loads the specific Scikit-Learn Random Forest model (Printed, Handwritten, Numeric, Symbols)
        and predicts the text. Returns (text, confidence).
        """
        # Placeholder: In a fully trained environment, we load e.g. `models/rf_symbols.joblib`
        # and run `.predict_proba()`
        return None, 0.0
