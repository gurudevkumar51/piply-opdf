import os
import requests
import time
import subprocess
from collections import Counter

proc = subprocess.Popen(["conda", "run", "-n", "py313_piply_opdf", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8003"])
time.sleep(3)

try:
    from reportlab.pdfgen import canvas
    c = canvas.Canvas('test_upload_kv.pdf')
    c.drawString(100, 750, 'Name: John Doe')
    c.drawString(100, 730, 'Date: 2024-01-01')
    c.save()

    with open('test_upload_kv.pdf', 'rb') as f:
        resp = requests.post("http://127.0.0.1:8003/upload", files={"file": f})
    
    doc_id = resp.json()["id"]
    requests.post(f"http://127.0.0.1:8003/process/{doc_id}?ocr_engine=paddle")
    
    for _ in range(10):
        time.sleep(2)
        resp = requests.get(f"http://127.0.0.1:8003/documents/{doc_id}")
        if resp.json()["status"] in ["completed", "error"]:
            print("Final status:", resp.json()["status"])
            break
            
    resp = requests.get(f"http://127.0.0.1:8003/components/{doc_id}")
    comps = resp.json()
    types = Counter(c["component_type"] for c in comps)
    print("Component types:", dict(types))
except Exception as e:
    print("Error:", e)
finally:
    proc.terminate()
