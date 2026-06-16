import sys
sys.path.append('.')
from piply_opdf.document import Document
doc = Document('sample6.pdf')
# process only page 10
tables = doc.process_layout()
page10_tables = [t for t in tables if t.page == 10]
print(f"Found {len(page10_tables)} tables on page 10.")
for i, t in enumerate(page10_tables):
    print(f'Table {i} ID: {t.table_id}, Rows: {len(t.rows)}')
    for j, r in enumerate(t.rows[:5]):
        print(f"  Row {j}: {r.bbox}")
