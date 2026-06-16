import sys
sys.path.append('.')
from piply_opdf.detectors.borderless_table_detector import BorderlessTableDetector
btd = BorderlessTableDetector()
tables = btd.detect_tables('sample6.pdf', 10, [])
print('Found', len(tables), 'tables')
for i, t in enumerate(tables):
    print(f'Table {i}:')
    for r in t.rows:
        print('  Row bbox:', r)
