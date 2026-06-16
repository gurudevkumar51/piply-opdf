import sqlite3
c = sqlite3.connect('piply.db')
try:
    c.execute('ALTER TABLE ocr_predictions ADD COLUMN image_hash VARCHAR')
    c.commit()
    print('Column added')
except Exception as e:
    print('Error:', e)
