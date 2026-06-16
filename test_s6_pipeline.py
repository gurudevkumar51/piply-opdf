import sys
sys.path.append('.')
from piply_opdf.document import Document
doc = Document('sample6.pdf')
doc.run_all()
