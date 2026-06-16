import sys
sys.path.append('.')
from piply_opdf.detectors.borderless_table_detector import BorderlessTableDetector
btd = BorderlessTableDetector()
tables = btd.detect_tables('sample6.pdf', 10, [])
print('Detected borderless tables for sample6 page 10:', len(tables))
