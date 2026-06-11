# Installation Guide — piply-opdf

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.13+ |
| conda | 24.0+ (recommended) |

---

## 1. Create the Development Environment

```bash
# Create the dedicated conda environment
conda create -n py313_piply_opdf python=3.13 -y

# Activate it
conda activate py313_piply_opdf
```

> **Always activate `py313_piply_opdf` before working on this project.**

---

## 2. Install the Package

### Development install (editable)

```bash
# From the project root
pip install -e ".[dev]"
```

This installs:
- All core dependencies (OpenCV, NumPy, PyMuPDF, Pillow, Pydantic, Typer, etc.)
- Dev dependencies (pytest, ruff, mypy)

### Install with OCR engines

```bash
# PaddleOCR (primary engine — recommended)
pip install -e ".[paddle]"

# Tesseract wrapper (fallback)
pip install -e ".[tesseract]"

# Both at once
pip install -e ".[paddle,tesseract]"

# Everything
pip install -e ".[all]"
```

---

## 3. Tesseract System Binary (if using Tesseract)

`pytesseract` is a Python wrapper — you also need the Tesseract binary:

### Windows
```powershell
# Using winget
winget install UB-Mannheim.TesseractOCR

# Or download installer from:
# https://github.com/UB-Mannheim/tesseract/wiki
```

After installing, add Tesseract to your PATH, or set:
```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

---

## 4. Verify Installation

```bash
# Check CLI is available
piply-opdf version

# Check package import
python -c "import piply_opdf; print(piply_opdf.__version__)"
```

---

## 5. Run Tests

```bash
# All unit tests
pytest tests/unit/ -v

# Specific phase tests
pytest tests/unit/test_phase1_assess.py -v
pytest tests/unit/test_phase2_enhance.py -v
pytest tests/unit/test_phase3_layout.py -v
pytest tests/unit/test_phase4_extract.py -v
pytest tests/unit/test_phase5_ocr.py -v

# With coverage
pytest tests/ --cov=piply_opdf --cov-report=term-missing
```

---

## 6. Quick Test with a Sample PDF

```bash
# Activate env
conda activate py313_piply_opdf

# Run full pipeline
piply-opdf run path/to/your/document.pdf

# Or step by step
piply-opdf assess document.pdf
piply-opdf enhance document.pdf
piply-opdf detect-layout document.pdf
piply-opdf extract-layouts document.pdf
piply-opdf ocr document.pdf
```

All output files are written to `<document_stem>_piply/` next to the input file.

---

## 7. Custom Configuration

```bash
# Use a custom config
piply-opdf assess document.pdf --config my_config.yaml

# Work dir override
piply-opdf run document.pdf --work-dir /path/to/output/
```

See `config/default.yaml` for all available settings.

---

## Directory Structure After Install

```
piply-opdf/
├── piply_opdf/          # Main package
├── tests/               # Unit & integration tests
├── docs/                # Documentation
├── config/              # YAML configs
├── examples/            # Usage examples (coming in Batch 2/3)
└── pyproject.toml       # Package metadata
```
