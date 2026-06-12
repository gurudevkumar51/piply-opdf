# piply-opdf

**OCR + PDF Document Understanding Framework**

A production-grade, lightweight, self-learning platform for:
- 📄 Document quality assessment
- ✨ Selective image enhancement
- 🔍 Layout detection (header, footer, table, paragraph, cell, image…)
- ✂️ Region-level extraction & Content Classification
- 🗂️ Similarity clustering & deduplication
- 🤖 OCR with confidence analysis
- 🧠 Human feedback learning *(Batch 2)*
- 🔄 Document rebuilding *(Batch 3)*

> **OCR is only one component.**
> The primary value is: **Understand Layout → Learn → Correct → Rebuild**

---

## Key Design Principles

- ⚡ **Lightweight first** — OpenCV, NumPy, PyMuPDF, ImageHash, Scikit-Learn
- 🔌 **Pluggable** — swap OCR engines, add phases, configure via YAML
- 🧩 **Independent modules** — every phase has its own public API + CLI command
- 📊 **No heavy transformers** — pure CV mathematics and analytics
- 🔁 **Self-learning** — continuous improvement from human feedback *(Batch 2)*

---

## Quick Start

```bash
# Create & activate conda environment
conda create -n py313_piply_opdf python=3.13 -y
conda activate py313_piply_opdf

# Install with PaddleOCR (primary engine)
pip install -e ".[paddle,dev]"

# Run full pipeline
piply-opdf run invoice.pdf
```

---

## Python API

```python
from piply_opdf import Document

doc = Document("invoice.pdf")

# Run individual phases
assessment = doc.assess()
enhanced_path = doc.enhance()
layout = doc.detect_layout()
manifest = doc.extract_layouts()
ocr_result = doc.ocr()

# Or full pipeline
results = doc.run_all()

print(f"Enhancement needed: {assessment.any_enhancement_needed}")
print(f"Regions detected: {len(layout.regions)}")
print(f"OCR confidence: {ocr_result.mean_confidence:.1%}")
```

---

## CLI

```bash
piply-opdf assess invoice.pdf          # Phase 1 — quality assessment
piply-opdf enhance invoice.pdf         # Phase 2 — smart enhancement
piply-opdf detect-layout invoice.pdf   # Phase 3 — layout structure
piply-opdf extract-layouts invoice.pdf # Phase 4 — crop regions
piply-opdf ocr invoice.pdf             # Phase 5 — OCR regions
piply-opdf run invoice.pdf             # All phases in sequence
```

Each command writes output to `invoice_piply/` alongside the source file.

---

## OCR Engines

| Engine | Install | Notes |
|--------|---------|-------|
| **PaddleOCR** (primary) | `pip install piply-opdf[paddle]` | Better accuracy |
| **Tesseract** (fallback) | `pip install piply-opdf[tesseract]` | Simpler install |

Configure in `config/default.yaml`:
```yaml
ocr:
  engine: paddleocr       # primary
  fallback_engine: tesseract
```

---

## Output Files

| Phase | Output |
|-------|--------|
| Assessment | `assessment.json` |
| Enhancement | `<name>_enhanced.pdf` |
| Layout Detection | `layout.json` |
| Layout Extraction | `layouts/<type>/<class>/` + `layout_manifest.json` |
| Similarity Clustering | `clusters/cluster_manifest.json` |
| OCR | `ocr_result.json` |

---

## Project Status

See **[docs/status.md](docs/status.md)** for detailed feature status.

| Batch | Phases | Status |
|-------|--------|--------|
| Batch 1 | 1–5 (Assessment → OCR) | ✅ Complete |
| Batch 2 | 6–10 (Confidence → ML Engine) | 🔲 Pending |
| Batch 3 | 11–12 (Rebuilding + Demo App) | 🔲 Pending |

---

## Development Environment

```bash
conda activate py313_piply_opdf
pip install -e ".[dev]"
pytest tests/unit/ -v
```

---

## Validation run

```bash
piply-opdf run 134242485947340351.pdf
piply-opdf run sample.pdf
piply-opdf run 2000267806.pdf
```

## License

MIT

