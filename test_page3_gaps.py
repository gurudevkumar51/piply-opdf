import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

img = None
for page_idx, page_img in iter_pages("sample2.pdf", dpi=300):
    if page_idx == 2:  # Page 3
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

grid_mask = cv2.bitwise_or(horizontal_mask, vertical_mask)
cv2.imwrite("test_page3_grid.png", grid_mask)

dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
grid_mask_dilated = cv2.dilate(grid_mask, dilation_kernel, iterations=2)

contours, _ = cv2.findContours(grid_mask_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

fragments = []
for c in contours:
    x, y, w_c, h_c = cv2.boundingRect(c)
    if w_c > 50 and h_c > 10:
        fragments.append((x, y, w_c, h_c, c))

fragments.sort(key=lambda f: f[1])

print(f"Total fragments on Page 3: {len(fragments)}")
for i in range(1, len(fragments)):
    prev_f = fragments[i-1]
    curr_f = fragments[i]
    
    prev_bottom = prev_f[1] + prev_f[3]
    curr_top = curr_f[1]
    
    gap = curr_top - prev_bottom
    print(f"Gap between {i-1} and {i}: {gap} pixels")

