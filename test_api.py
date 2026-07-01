import os
import requests
import time
import subprocess

# Start the server
proc = subprocess.Popen(["conda", "run", "-n", "py313_piply_opdf", "python", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8001"])
time.sleep(3)

try:
    # Create test pdf
    from reportlab.pdfgen import canvas
    c = canvas.Canvas('test_upload2.pdf')
    c.drawString(100, 750, 'Hello World. This is a paragraph. It has many words. Let us see if it works.')
    c.save()

    # Upload
    with open('test_upload2.pdf', 'rb') as f:
        resp = requests.post("http://127.0.0.1:8001/upload", files={"file": f})
    
    print("Upload response:", resp.status_code, resp.text)
    if resp.status_code == 200:
        doc_id = resp.json()["id"]
        # Process
        resp = requests.post(f"http://127.0.0.1:8001/process/{doc_id}?ocr_engine=paddle")
        print("Process response:", resp.status_code, resp.text)
        
        # Poll
        for _ in range(10):
            time.sleep(2)
            resp = requests.get(f"http://127.0.0.1:8001/documents/{doc_id}")
            print("Poll:", resp.json()["status"])
            if resp.json()["status"] in ["completed", "error"]:
                break
        
        # Get components
        resp = requests.get(f"http://127.0.0.1:8001/components/{doc_id}")
        print("Components count:", len(resp.json()))
except Exception as e:
    print("Error:", e)
finally:
    proc.terminate()
