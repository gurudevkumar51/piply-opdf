import sys
sys.path.append('.')
from piply_opdf.document import Document
doc = Document('sample4.pdf')
tables = doc.process_layout()
for i, t in enumerate(tables):
    print(f'Table {i} ID: {t.table_id}, Rows: {len(t.rows)}')
