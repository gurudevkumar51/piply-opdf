# Installation

## Requirements

- Python 3.13+
- conda 24.0+ (recommended)

## Environment

```bash
conda create -n py313_piply_opdf python=3.13 -y
conda activate py313_piply_opdf
```

> Always activate `py313_piply_opdf` before working on this project.

## Install

```bash
pip install -e ".[dev]"
```

Core dependencies: OpenCV, NumPy, PyMuPDF, Pydantic, Typer, PyYAML.

With OCR engines:

```bash
pip install -e ".[paddle]"        # PaddleOCR — primary, better accuracy
pip install -e ".[tesseract]"     # Tesseract — fallback, simpler install
pip install -e ".[all]"
```

## Tesseract binary

`pytesseract` is a wrapper; the binary is separate.

```powershell
winget install UB-Mannheim.TesseractOCR
```

Add it to `PATH`, or set:

```python
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## Verify

```bash
piply-opdf version
```

```bash
python -c "import piply_opdf; print(piply_opdf.__version__)"
```

## Tests

```bash
pytest tests/unit -v
```

585 tests. See [testing.md](testing.md).

## Configuration

All thresholds live in `config/default.yaml`.

```bash
piply-opdf assess document.pdf --config my_config.yaml
```

| Setting | Default | Meaning |
|---------|---------|---------|
| `assessment.blur_threshold` | `100.0` | Laplacian variance below this = blurry |
| `assessment.noise_threshold` | `0.02` | Above this = noisy |
| `assessment.contrast_threshold` | `50.0` | RMS below this = low contrast |
| `assessment.skew_threshold` | `0.1` | Degrees above this flags deskew |
| `ocr.engine` | `paddleocr` | Primary engine |
| `ocr.fallback_engine` | `tesseract` | Fallback |
| `layout_detection.header_ratio` | `0.12` | Top 12% = header zone |
| `layout_detection.footer_ratio` | `0.10` | Bottom 10% = footer zone |

## Deployment

SQLite plus local filesystem suits single-user and small-team use. Output
folders grow quickly — page renders, crops and debug images are all persisted.
Multi-user production would need a stronger database and a job queue.

The knowledge database (`knowledge/piply_opdf_knowledge-*.db`) is portable and
worth backing up separately — it is the accumulated human-verified truth.
