import os
import json
import numpy as np
from typing import Any, Dict
from piply_opdf.core.interfaces import IFeatureExtractor

try:
    import imagehash
    from PIL import Image
    import cv2
except ImportError:
    imagehash = None
    Image = None
    cv2 = None

class DefaultFeatureExtractor(IFeatureExtractor):
    """
    Extracts image features such as perceptual hashes (pHash, dHash, aHash),
    dimensions, aspect ratio, edge density, and histogram features.
    """
    
    def extract_features(self, image_path: str) -> Dict[str, Any]:
        if not imagehash or not cv2 or not Image:
            raise ImportError("Required libraries (imagehash, PIL, cv2) are not installed.")
            
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Image not found: {image_path}")
            
        try:
            pil_img = Image.open(image_path)
            
            # Compute hashes
            phash = str(imagehash.phash(pil_img))
            dhash = str(imagehash.dhash(pil_img))
            ahash = str(imagehash.average_hash(pil_img))
            
            # Compute OpenCV features
            cv_img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if cv_img is None:
                raise ValueError(f"Could not read image using OpenCV: {image_path}")
                
            height, width = cv_img.shape
            aspect_ratio = float(width) / float(height) if height > 0 else 0.0
            
            # Edge density
            edges = cv2.Canny(cv_img, 100, 200)
            edge_density = float(np.sum(edges > 0)) / (width * height) if width * height > 0 else 0.0
            
            # Histogram features (simplistic 16 bin)
            hist = cv2.calcHist([cv_img], [0], None, [16], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            hist_list = hist.tolist()
            
            return {
                "phash": phash,
                "dhash": dhash,
                "ahash": ahash,
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "edge_density": edge_density,
                "histogram_features": json.dumps(hist_list)
            }
        except Exception as e:
            raise RuntimeError(f"Failed to extract features for {image_path}: {e}")
