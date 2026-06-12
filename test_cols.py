import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages
import json

img = None
for page_idx, page_img in iter_pages("sample.pdf", dpi=300):
    if page_idx == 0:
        img = page_img
        break

with open("sample_piply/layouts/page_1/table_001/manifest.json") as f:
    manifest = json.load(f)

x, y, tw, th = manifest["bbox"]
roi_gray = cv2.cvtColor(img[y:y+th, x:x+tw], cv2.COLOR_RGB2GRAY)
thresh = cv2.adaptiveThreshold(roi_gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 4)

h_page, w_page = img.shape[:2]
h, w = thresh.shape

v_kernel_size = 40
v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_kernel_size))
v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
v_close = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 10))
v_lines = cv2.morphologyEx(v_lines, cv2.MORPH_CLOSE, v_close)
line_proj = np.sum(v_lines, axis=0) / 255.0

peaks = []
in_peak = False
start = 0
for i in range(len(line_proj)):
    if line_proj[i] > 10: # any small line
        if not in_peak:
            in_peak = True
            start = i
    else:
        if in_peak:
            in_peak = False
            peaks.append((start, i, max(line_proj[start:i])))
if in_peak: 
    peaks.append((start, len(line_proj), max(line_proj[start:])))
print(f"All line_proj peaks (>10px): {peaks}")
print(f"h * 0.1 threshold is {h * 0.1}")

line_boundaries = []
in_line = False
start = 0
for i in range(len(line_proj)):
    if line_proj[i] > h * 0.1:
        if not in_line:
            in_line = True
            start = i
    else:
        if in_line:
            in_line = False
            line_boundaries.append((start + i) // 2)
if in_line: 
    line_boundaries.append((start + len(line_proj)) // 2)

print(f"Line Boundaries ({len(line_boundaries)}):", line_boundaries)

h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(20, w // 20), 1))
h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
content = cv2.subtract(thresh, h_lines)
text_only = cv2.subtract(content, v_lines)
vertical_merge = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 15))
text_merged = cv2.morphologyEx(text_only, cv2.MORPH_DILATE, vertical_merge)
text_proj = np.sum(text_merged, axis=0) / 255.0
text_proj_smoothed = np.convolve(text_proj, np.ones(5)/5, mode='same')

in_gutter = False
start = 0
gutters = []
for i, val in enumerate(text_proj_smoothed):
    if val < h * 0.03: 
        if not in_gutter:
            in_gutter = True
            start = i
    else:
        if in_gutter:
            in_gutter = False
            gutters.append((start, i))
if in_gutter: 
    gutters.append((start, len(text_proj_smoothed)))

print("Gutters:", gutters)

whitespace_boundaries = []
min_gutter_width = max(15, w // 100)
for g_start, g_end in gutters:
    if g_end - g_start >= min_gutter_width:
        has_grid_line = False
        for lb in line_boundaries:
            if g_start - 15 <= lb <= g_end + 15:
                has_grid_line = True
                break
        print(f"Gutter {g_start}-{g_end} (width {g_end-g_start}), has_grid_line={has_grid_line}")
        if not has_grid_line:
            mid = (g_start + g_end) // 2
            whitespace_boundaries.append(mid)

print(f"Whitespace Boundaries ({len(whitespace_boundaries)}):", whitespace_boundaries)
