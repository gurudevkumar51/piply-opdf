@echo off
set PYTHONIOENCODING=utf-8
conda run -n py313_piply_opdf python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pause
