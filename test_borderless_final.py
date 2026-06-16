import fitz
import sys
import numpy as np
import cv2
sys.path.append('.')
from piply_opdf.detectors.borderless_table_detector import BorderlessTableDetector
doc = fitz.open('sample6.pdf')
page = doc[9]
pix = page.get_pixmap(dpi=300)
img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
if pix.n == 4: img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
elif pix.n == 1: img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

detector = BorderlessTableDetector()
tables = detector.detect_tables('sample6.pdf', 10, [])
print(f'Detected {len(tables)} tables')
if tables:
    t = tables[0]
    print(f"Table has {len(t.columns)} cols and {len(t.rows)} rows")
    for r in t.rows:
        print(r)
