import cv2
import numpy as np

img = cv2.imread("sample_piply/layouts/page_1/table_001/table.png")
if img is None:
    print("Could not load debug table image.")
    exit()

gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4)
h, w = thresh.shape

# Detect vertical lines
v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, h // 20)))
v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
v_close = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
v_lines = cv2.morphologyEx(v_lines, cv2.MORPH_CLOSE, v_close)

line_proj = np.sum(v_lines, axis=0) / 255.0
cv2.imwrite("test_vlines_output.png", v_lines)
max_val = np.max(line_proj)
print(f"Table height: {h}")
print(f"Max vertical line length: {max_val}")
print(f"Threshold used (10%): {h * 0.1}")

# How many columns would we find if threshold was 1%?
for i in range(1, 11):
    thresh_val = h * (i / 100.0)
    count = 0
    in_line = False
    for val in line_proj:
        if val > thresh_val:
            if not in_line:
                in_line = True
                count += 1
        else:
            in_line = False
    print(f"At {i}% threshold ({thresh_val:.1f}px), found {count} vertical lines.")
