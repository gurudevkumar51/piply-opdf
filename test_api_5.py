import os
import requests
import time
import subprocess
from collections import Counter

proc = subprocess.Popen(["conda", "run", "-n", "py313_piply_opdf", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8005"])
time.sleep(3)

try:
    with open('test_upload_kv.pdf', 'rb') as f:
        resp = requests.post("http://127.0.0.1:8005/upload", files={"file": f})
    
    doc_id = resp.json()["id"]
    requests.post(f"http://127.0.0.1:8005/process/{doc_id}?ocr_engine=paddle")
    
    for _ in range(15):
        time.sleep(2)
        resp = requests.get(f"http://127.0.0.1:8005/components/{doc_id}")
        comps = resp.json()
        if comps:
            preds = sum(len(c.get("predictions", [])) for c in comps)
            if preds > 0:
                print("Predictions generated:", preds)
                break
    else:
        print("No predictions generated.")
        
except Exception as e:
    print("Error:", e)
finally:
    proc.terminate()
