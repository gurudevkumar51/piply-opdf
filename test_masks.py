import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

img = None
for page_idx, page_img in iter_pages("sample.pdf", dpi=300):
    if page_idx == 0:
        img = page_img
        break

gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4)

h, w = gray.shape

h_len = max(w // 40, 30)
v_len = max(h // 40, 30)

h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
horizontal_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)

v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
vertical_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)

cv2.imwrite("test_sample_hmask.png", horizontal_mask)
cv2.imwrite("test_sample_vmask.png", vertical_mask)
print(f"Masks saved. h_len={h_len}, v_len={v_len}")
