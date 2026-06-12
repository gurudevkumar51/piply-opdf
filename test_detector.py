import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

img = None
for page_idx, page_img in iter_pages("sample2.pdf", dpi=300):
    if page_idx == 0:
        img = page_img
        break


# We will copy the exact logic here to debug
gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
h, w = gray.shape

thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4)

h_len = max(w // 40, 30)
v_len = max(h // 40, 30)

h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_len, 1))
horizontal_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)

v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_len))
vertical_mask = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)

grid_mask = cv2.bitwise_or(horizontal_mask, vertical_mask)

dilation_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
grid_mask_dilated = cv2.dilate(grid_mask, dilation_kernel, iterations=2)

contours, _ = cv2.findContours(grid_mask_dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

fragments = []
for c in contours:
    x, y, w_c, h_c = cv2.boundingRect(c)
    if w_c > 50 and h_c > 10:
        fragments.append((x, y, w_c, h_c, c))

fragments.sort(key=lambda f: f[1])

MAX_VERTICAL_GAP = h * 0.15
MIN_HORIZONTAL_OVERLAP = 0.2

clusters = []
for frag in fragments:
    fx, fy, fw, fh, fc = frag
    added_to_cluster = False
    for cluster in clusters:
        cx, cy, cw, ch = cluster["bbox"]
        cluster_bottom = cy + ch
        if fy - cluster_bottom <= MAX_VERTICAL_GAP and fy + fh >= cy:
            overlap_left = max(fx, cx)
            overlap_right = min(fx + fw, cx + cw)
            overlap_width = overlap_right - overlap_left
            if overlap_width > 0:
                # Calculate overlap ratio relative to the smaller width
                min_width = min(fw, cw)
                max_width = max(fw, cw)
                
                # Only group if they have somewhat similar widths (e.g. > 70% of each other)
                # This prevents wide tables from swallowing short header/footer lines
                width_similarity = min_width / max_width
                
                if (overlap_width / min_width) >= MIN_HORIZONTAL_OVERLAP and width_similarity > 0.7:
                    new_x = min(cx, fx)
                    new_y = min(cy, fy)
                    new_w = max(cx + cw, fx + fw) - new_x
                    new_h = max(cy + ch, fy + fh) - new_y
                    cluster["bbox"] = (new_x, new_y, new_w, new_h)
                    cluster["contours"].append(fc)
                    added_to_cluster = True
                    break
    if not added_to_cluster:
        clusters.append({"bbox": (fx, fy, fw, fh), "contours": [fc]})

print(f"Found {len(fragments)} fragments.")
print(f"Grouped into {len(clusters)} clusters.")

for i, cluster in enumerate(clusters):
    x, y, w_c, h_c = cluster["bbox"]
    if w_c < w * 0.1 or h_c < h * 0.02:
        print(f"Cluster {i}: Size filtered ({w_c}x{h_c})")
        continue

    rect_area = w_c * h_c
    contour_area = sum(cv2.contourArea(c) for c in cluster["contours"])
    all_pts = np.vstack(cluster["contours"])
    hull = cv2.convexHull(all_pts)
    hull_area = cv2.contourArea(hull)

    if hull_area == 0:
        print(f"Cluster {i}: Zero hull area")
        continue

    rectangularity = contour_area / hull_area
    roi = grid_mask[y:y+h_c, x:x+w_c]
    line_pixels = cv2.countNonZero(roi)
    line_density = line_pixels / rect_area

    table_confidence = (rectangularity * 0.6) + (min(line_density * 10, 1.0) * 0.4)
    print(f"Cluster {i}: BBox=({w_c}x{h_c}), Rect={rectangularity:.2f}, LineDens={line_density:.4f}, Conf={table_confidence:.2f}")

