# Piply OPDF Context

**Piply OPDF** is a lightweight, offline, CPU-friendly Self-Learning Document Intelligence Framework.

## Core Vision
It is designed to minimize traditional OCR dependency by utilizing a 5-Layer Knowledge First pipeline:
1. Exact Knowledge Match (Hashes)
2. Similar Image Match (SSIM, Histograms)
3. ML Prediction (KNN, RF, SVM)
4. OCR (PaddleOCR fallback)
5. Human Review (Feeds back into Level 1/2)

The system detects and extracts structural components (Tables, Cells, Paragraphs, Titles, Headers, Footers) and processes them at the smallest possible OCR unit to maximize learning reuse across all projects.

## Tech Stack
* **Python 3.10+**
* **Core:** Typer, Pydantic, OpenCV, NumPy (pure Python logic)
* **Backend UI:** FastAPI, SQLAlchemy, SQLite, Jinja2, Vanilla JS/HTML
* **OCR Engines:** PaddleOCR, Tesseract (as fallback)

## Developer Guidelines
When contributing to this repository, understand that this is NOT just an OCR wrapper; it is an intelligent, highly-modular OOP-based framework. Read `coding_guidelines.md` before making any structural changes to the pipeline.
