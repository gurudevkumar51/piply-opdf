import fitz
import sys
sys.path.append('.')
from piply_opdf.detectors.borderless_table_detector import BorderlessTableDetector
btd = BorderlessTableDetector()
doc = fitz.open('sample5.pdf')
page = doc[0]

words = page.get_text("words")
boxes = []
for w in words:
    x0, y0, x1, y1 = [v * btd.scale for v in w[:4]]
    text = w[4]
    if x1 - x0 > 2 and y1 - y0 > 2 and text.strip():
        boxes.append((x0, y0, x1, y1, text))

boxes.sort(key=lambda b: (b[1] + b[3])/2)
rows = []
current_row = []
for b in boxes:
    cy = (b[1] + b[3]) / 2
    if not current_row:
        current_row.append(b)
    else:
        prev_cy = (current_row[0][1] + current_row[0][3]) / 2
        if abs(cy - prev_cy) < 15:
            current_row.append(b)
        else:
            rows.append(current_row)
            current_row = [b]
if current_row:
    rows.append(current_row)

table_rows = []
for r in rows:
    r.sort(key=lambda b: b[0])
    cols = []
    current_col = []
    for b in r:
        if not current_col:
            current_col.append(b)
        else:
            if b[0] - max(c[2] for c in current_col) > 40:
                cols.append(current_col)
                current_col = [b]
            else:
                current_col.append(b)
    if current_col:
        cols.append(current_col)
    
    if len(cols) >= 2:
        table_rows.append({"y0": min(b[1] for b in r), "y1": max(b[3] for b in r), "cols": len(cols), "text": [c[0][4] for c in cols], "col_bounds": [(min(b[0] for b in c), max(b[2] for b in c)) for c in cols]})

print("Printing ALL table_rows:")
for i, tr in enumerate(table_rows):
    if i > 0:
        prev_y1 = table_rows[i-1]['y1']
        gap = tr['y0'] - prev_y1
    else:
        gap = 0
    print(f"y0={tr['y0']:.1f}, y1={tr['y1']:.1f}, cols={tr['cols']}, text={tr['text'][:2]}, gap={gap:.1f}")

