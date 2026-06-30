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
            cv_img_raw = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if cv_img_raw is None:
                raise ValueError(f"Could not read image using OpenCV: {image_path}")

            # Auto-crop white borders so hashes aren't overwhelmed by padding
            _, thresh_for_crop = cv2.threshold(cv_img_raw, 240, 255, cv2.THRESH_BINARY_INV)
            coords = cv2.findNonZero(thresh_for_crop)
            if coords is not None:
                x, y, w, h = cv2.boundingRect(coords)
                # Crop with a small 5px padding
                x = max(0, x - 5)
                y = max(0, y - 5)
                w = min(cv_img_raw.shape[1] - x, w + 10)
                h = min(cv_img_raw.shape[0] - y, h + 10)
                cv_img = cv_img_raw[y:y+h, x:x+w]
                # Re-create pil_img from the cropped cv_img
                pil_img = Image.fromarray(cv_img)
            else:
                cv_img = cv_img_raw
                pil_img = Image.open(image_path)
            
            # Compute hashes on the tightly cropped image
            phash = str(imagehash.phash(pil_img))
            dhash = str(imagehash.dhash(pil_img))
            ahash = str(imagehash.average_hash(pil_img))
            
            # Compute OpenCV features
            height, width = cv_img.shape
            aspect_ratio = float(width) / float(height) if height > 0 else 0.0
            
            # Edge density
            edges = cv2.Canny(cv_img, 100, 200)
            edge_density = float(np.sum(edges > 0)) / (width * height) if width * height > 0 else 0.0
            
            # Histogram features (simplistic 16 bin)
            hist = cv2.calcHist([cv_img], [0], None, [16], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            hist_list = hist.tolist()

            # 1. Stroke Density
            _, thresh = cv2.threshold(cv_img, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
            stroke_density = float(np.sum(thresh > 0)) / (width * height) if width * height > 0 else 0.0
            
            # 2. Connected Components
            num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(thresh, connectivity=8)
            connected_components = max(0, num_labels - 1)
            
            # 3. Projection Profiles
            h_proj = np.sum(thresh, axis=1).tolist()
            v_proj = np.sum(thresh, axis=0).tolist()
            # Normalize profiles to 32 bins to make them easily comparable
            h_proj_fixed = cv2.resize(np.array(h_proj, dtype=np.float32), (1, 32)).flatten().tolist()
            v_proj_fixed = cv2.resize(np.array(v_proj, dtype=np.float32), (32, 1)).flatten().tolist()
            projection_profiles = json.dumps({"h": h_proj_fixed, "v": v_proj_fixed})
            
            # 4. Hu Moments
            moments = cv2.moments(thresh)
            hu_moments_arr = cv2.HuMoments(moments).flatten().tolist()
            hu_moments = json.dumps([-1 * np.sign(h) * np.log10(np.abs(h)) if h != 0 else 0 for h in hu_moments_arr])
            
            # 5. HOG Features
            img_64 = cv2.resize(cv_img, (64, 64))
            hog = cv2.HOGDescriptor((64, 64), (16, 16), (8, 8), (8, 8), 9)
            hog_features = json.dumps(hog.compute(img_64).flatten().tolist())
            
            return {
                "phash": phash,
                "dhash": dhash,
                "ahash": ahash,
                "width": width,
                "height": height,
                "aspect_ratio": aspect_ratio,
                "edge_density": edge_density,
                "stroke_density": stroke_density,
                "connected_components": connected_components,
                "histogram_features": json.dumps(hist_list),
                "projection_profiles": projection_profiles,
                "hu_moments": hu_moments,
                "hog_features": hog_features
            }
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise RuntimeError(f"Failed to extract features for {image_path}: {e}")
