import os
import requests
import time
import subprocess
from collections import Counter

proc = subprocess.Popen(["conda", "run", "-n", "py313_piply_opdf", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8002"])
time.sleep(3)

try:
    with open('test_upload2.pdf', 'rb') as f:
        resp = requests.post("http://127.0.0.1:8002/upload", files={"file": f})
    
    doc_id = resp.json()["id"]
    requests.post(f"http://127.0.0.1:8002/process/{doc_id}?ocr_engine=paddle")
    
    for _ in range(10):
        time.sleep(2)
        resp = requests.get(f"http://127.0.0.1:8002/documents/{doc_id}")
        if resp.json()["status"] in ["completed", "error"]:
            print("Final status:", resp.json()["status"])
            break
            
    resp = requests.get(f"http://127.0.0.1:8002/components/{doc_id}")
    comps = resp.json()
    types = Counter(c["component_type"] for c in comps)
    print("Component types:", dict(types))
except Exception as e:
    print("Error:", e)
finally:
    proc.terminate()
