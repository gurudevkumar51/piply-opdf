import sys
sys.path.append('.')
from piply_opdf.document import Document
doc = Document('sample5.pdf')
doc.run_all()
print(f"Sample 5 Borderless tables: {len(doc.borderless_tables)}")
