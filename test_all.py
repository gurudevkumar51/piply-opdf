import sys
sys.path.append('.')
from piply_opdf.document import Document
for f in ['sample.pdf', 'sample2.pdf', 'sample4.pdf', 'sample6.pdf']:
    print(f'Testing {f}...')
    try:
        doc = Document(f)
        doc.process_layout()
        print(f'Done {f}')
    except Exception as e:
        print(f'Error processing {f}: {e}')
