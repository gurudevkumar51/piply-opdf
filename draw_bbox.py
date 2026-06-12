import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages
import json

img = None
for page_idx, page_img in iter_pages("sample.pdf", dpi=300):
    if page_idx == 0:
        img = cv2.cvtColor(page_img, cv2.COLOR_RGB2BGR)
        break

with open("sample_piply/layouts/page_1/table_001/manifest.json") as f:
    manifest = json.load(f)

x, y, w, h = manifest["bbox"]

# Draw bounding box
cv2.rectangle(img, (x, y), (x+w, y+h), (0, 0, 255), 4)

# Crop the bottom part to see what is included
bottom_crop = img[y+h-500:y+h+100, x-50:x+w+50]
cv2.imwrite("test_sample_bbox.png", bottom_crop)
