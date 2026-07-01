import os
import requests
import time
import subprocess
from collections import Counter
import cv2
import numpy as np

proc = subprocess.Popen(["conda", "run", "-n", "py313_piply_opdf", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8004"])
time.sleep(3)

try:
    img = np.zeros((800, 600, 3), dtype=np.uint8)
    cv2.putText(img, 'Hello World', (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
    cv2.imwrite('test_upload.png', img)

    with open('test_upload.png', 'rb') as f:
        resp = requests.post("http://127.0.0.1:8004/upload", files={"file": f})
    
    print("Upload:", resp.status_code)
    doc_id = resp.json()["id"]
    requests.post(f"http://127.0.0.1:8004/process/{doc_id}?ocr_engine=paddle")
    
    for _ in range(10):
        time.sleep(2)
        resp = requests.get(f"http://127.0.0.1:8004/documents/{doc_id}")
        if resp.json()["status"] in ["completed", "error"]:
            print("Final status:", resp.json()["status"])
            break
            
    resp = requests.get(f"http://127.0.0.1:8004/components/{doc_id}")
    comps = resp.json()
    types = Counter(c["component_type"] for c in comps)
    print("Component types:", dict(types))
except Exception as e:
    print("Error:", e)
finally:
    proc.terminate()
