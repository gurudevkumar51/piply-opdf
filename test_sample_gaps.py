import cv2
import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

img = None
for page_idx, page_img in iter_pages("sample.pdf", dpi=300):
    if page_idx == 0:
        img = page_img
        break

gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4)

h, w = gray.shape

h_len = max(w // 40, 30)
v_len = max(h // 40, 30)

h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
horizontal_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)

v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
vertical_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)

cv2.imwrite("test_sample_vmask_51.png", vertical_mask)

bottom_part = vertical_mask[int(h*0.9):, :]

contours, _ = cv2.findContours(bottom_part, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

print(f"Total contours in bottom 10% V-mask: {len(contours)}")
for i, c in enumerate(contours):
    x, y, w_c, h_c = cv2.boundingRect(c)
    if w_c > 50 or h_c > 10:
        print(f"Contour {i}: x={x}, y={y + int(h*0.9)}, w={w_c}, h={h_c}")
