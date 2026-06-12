import cv2
import numpy as np
from piply_opdf.utils.pdf import iter_pages

for page_idx, page_img in iter_pages("sample.pdf", dpi=300):
    if page_idx == 0:
        cv2.imwrite("sample_page1.png", cv2.cvtColor(page_img, cv2.COLOR_RGB2BGR))
        break
