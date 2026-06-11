import subprocess
import os

python_exe = r"C:\Users\Gurudev\.conda\envs\py313_piply_opdf\python.exe"

def run(cmd):
    print(f"Running: {' '.join(cmd)}")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, check=True, env=env)

try:
    print("Processing 134242485947340351.pdf...")
    run([python_exe, "-m", "piply_opdf.cli", "detect-layout", "134242485947340351.pdf"])

    print("Processing sample.pdf...")
    run([python_exe, "-m", "piply_opdf.cli", "detect-layout", "sample.pdf"])
except Exception as e:
    print(e)
