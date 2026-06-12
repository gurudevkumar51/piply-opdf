import cv2
import sys
from pathlib import Path
sys.path.append(str(Path('.').resolve()))
from piply_opdf.layout.table_detector import TableDetector
import fitz
import numpy as np

pdf_path = "sample2_piply/sample2_enhanced.pdf"
doc = fitz.open(pdf_path)
detector = TableDetector()

for i in range(len(doc)):
    page = doc[i]
    pix = page.get_pixmap(dpi=300)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if pix.n == 4:
        img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
    elif pix.n == 1:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        
    # Test raw detection
    contours, _ = cv2.findContours(cv2.dilate(cv2.bitwise_or(cv2.morphologyEx(cv2.adaptiveThreshold(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape)==3 else img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(img.shape[1]//40, 30), 1)), iterations=2), cv2.morphologyEx(cv2.adaptiveThreshold(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape)==3 else img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 15, 4), cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(img.shape[0]//40, 30))), iterations=2)), cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)), iterations=2), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"Page {i+1} total contours: {len(contours)}")
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area > 10000:
            print(f"  Contour x={x}, y={y}, w={w}, h={h}")
    
    tables = detector.detect_tables(img)
    print(f"Page {i+1} found {len(tables)} tables")
