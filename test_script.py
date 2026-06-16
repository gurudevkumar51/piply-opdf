import sys
sys.path.append('.')
from piply_opdf.document import Document
doc2 = Document('sample2.pdf')
doc2.process_layout()
doc4 = Document('sample4.pdf')
doc4.process_layout()
print('Done!')
