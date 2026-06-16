import sys
sys.path.append('.')
from piply_opdf.layout.grid_builder import GridBuilder
from piply_opdf.detectors.table_detector import TableDetector

import cv2
import numpy as np
import fitz

def test_grid(pdf_path, page_num):
    print(f"Testing {pdf_path} page {page_num}")
    doc = fitz.open(pdf_path)
    page = doc[page_num - 1]
    pix = page.get_pixmap(dpi=300)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 1:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        
    detector = TableDetector()
    tables = detector.detect_tables(img)
    if not tables:
        print("No tables found")
        return
        
    t = tables[0]
    tx, ty, tw, th = t.x, t.y, t.width, t.height
    
    # We need the table image
    table_img = img[ty:ty+th, tx:tx+tw]
    
    gb = GridBuilder()
    
    # Let's mock the GridBuilder process
    gray = cv2.cvtColor(table_img, cv2.COLOR_BGR2GRAY)
    thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4)
    
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
    h_close = cv2.getStructuringElement(cv2.MORPH_RECT, (10, 1))
    h_lines = cv2.morphologyEx(h_lines, cv2.MORPH_CLOSE, h_close)
    
    h_proj = np.sum(h_lines, axis=1) / 255.0
    thresh_val = tw * 0.1
    
    dividers = []
    in_line = False
    start_y = 0
    for y, val in enumerate(h_proj):
        if val > thresh_val:
            if not in_line:
                in_line = True
                start_y = y
        else:
            if in_line:
                in_line = False
                dividers.append((start_y + y) // 2)
                
    if not dividers or dividers[0] > 10:
        dividers.insert(0, 0)
    if dividers[-1] < th - 10:
        dividers.append(th)
        
    print(f"Total dividers: {len(dividers)}")
    for i in range(len(dividers) - 1):
        y1, y2 = dividers[i], dividers[i+1]
        h = y2 - y1
        print(f"Row {i} height: {h}")

test_grid('sample4.pdf', 1)
test_grid('sample2.pdf', 1)
