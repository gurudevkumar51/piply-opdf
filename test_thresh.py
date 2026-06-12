import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

for page_idx, page_img in iter_pages("sample.pdf", dpi=300):
    if page_idx == 0:
        gray = cv2.cvtColor(page_img, cv2.COLOR_RGB2GRAY)
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4)
        h, w = thresh.shape
        bottom_thresh = thresh[int(h*0.9):, :]
        cv2.imwrite("test_sample_thresh_bottom.png", bottom_thresh)
        break
