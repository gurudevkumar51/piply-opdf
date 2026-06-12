import cv2
import numpy as np
from piply_opdf.layout.table_detector import TableDetector

class DebugTableDetector(TableDetector):
    def detect_tables(self, image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4)
        h_len = max(w // 40, 30)
        v_len = max(h // 40, 30)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        h_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        v_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
        grid_mask = cv2.bitwise_or(h_mask, v_mask)
        dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        grid_mask_dilated = cv2.dilate(grid_mask, dilation_kernel, iterations=2)
        contours, _ = cv2.findContours(grid_mask_dilated, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        
        fragments = []
        for c in contours:
            x, y, w_c, h_c = cv2.boundingRect(c)
            # Filter out page-level borders
            if w_c > w * 0.9 and h_c > h * 0.9:
                print(f"Ignored page border: {w_c}x{h_c}")
                continue
            fragments.append((x, y, w_c, h_c))
        fragments.sort(key=lambda f: f[1])
        print("FRAGMENTS:")
        for f in fragments:
            print(f)
            
        return super().detect_tables(image)

img = cv2.imread('C:/Users/Gurudev/.gemini/antigravity/brain/09b826b3-d232-4977-b261-bb964af4fd5e/scratch/sample4_page1_100dpi.png')
td = DebugTableDetector()
td.detect_tables(img)
