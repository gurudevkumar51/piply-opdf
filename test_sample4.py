import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

for page_idx, page_img in iter_pages("sample4.pdf", dpi=300):
    if page_idx == 0:
        gray = cv2.cvtColor(page_img, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4)
        h_len = max(w // 40, 30)
        v_len = max(h // 40, 30)
        h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
        h_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
        v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
        v_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
        grid_mask = cv2.bitwise_or(h_mask, v_mask)
        cv2.imwrite("scratch/sample4_grid_mask.png", grid_mask)
        cv2.imwrite("scratch/sample4_thresh.png", thresh)
        break
