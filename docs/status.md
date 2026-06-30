# piply-opdf — Feature Status

> **Batch 1** of 3 delivered. Phases 1–5 are implemented and tested.
> Pending phases are stubs — they will be implemented in future batches after review.

---

## ✅ Completed — Batch 1 (Phases 1–5)

### Phase 1 — Document Assessment Engine
**Status:** ✅ Complete  
**Module:** `piply_opdf/phases/phase1_assess.py`  
**API:** `DocumentAssessor().assess(path) → AssessmentResult`  
**CLI:** `piply-opdf assess <file>`  
**Output:** `assessment.json`

Features implemented:
- Blur detection (Laplacian variance)
- Noise estimation (Gaussian difference)
- Contrast scoring (RMS)
- Skew detection (Hough line transform — angle estimation)
- Per-page quality rating (`good` / `acceptable` / `poor`)
- Smart enhancement recommendation list
- Configurable thresholds via `config/default.yaml`

---

### Phase 2 — Document Enhancement Engine
**Status:** ✅ Complete  
**Module:** `piply_opdf/phases/phase2_enhance.py`  
**API:** `DocumentEnhancer().enhance(path, assessment) → Path`  
**CLI:** `piply-opdf enhance <file>`  
**Output:** `<name>_enhanced.pdf`

Features implemented:
- Deskew (affine rotation correction)
- Denoise (fast non-local means)
- Contrast enhancement (CLAHE in LAB colour space)
- Unsharp mask sharpening
- Border enhancement (morphological close)
- Table border reconstruction (dilation + contour overlay)
- **Smart mode:** only applies operations flagged by assessment

---

### Phase 3 — Layout Detection Engine
**Status:** ✅ Complete  
**Module:** `piply_opdf/phases/phase3_layout.py`  
**API:** `LayoutDetector().detect(path) → LayoutResult`  
**CLI:** `piply-opdf detect-layout <file>`  
**Output:** `layout.json`

Features implemented:
- Header / footer zone detection (configurable ratio)
- Table detection via horizontal + vertical line grid analysis
- Borderless table detection using line projection alignment
- Cell extraction within bordered and borderless tables
- Paragraph / text block detection (projection profiles + dilation)
- Key-Value region detection (aspect ratio heuristic)
- Embedded image region detection (density heuristic)
- Region hierarchy: `Table → [Row] → Cell`
- Pure OpenCV — no ML models

> **Note:** Layout detection uses classical CV heuristics (projection profiles, contour analysis, grid-line detection). This works well for structured documents (forms, invoices, tables). Complex multi-column academic papers may require future refinement in Batch 2/3.

---

### Phase 4 — Layout Extraction Engine
**Status:** ✅ Complete  
**Module:** `piply_opdf/phases/phase4_extract.py`  
**API:** `LayoutExtractor().extract(path, layout) → LayoutManifest`  
**CLI:** `piply-opdf extract-layouts <file>`  
**Output:** `layouts/` directory + `layout_manifest.json`

Features implemented:
- Crops each region from the page image
- Runs mathematical Content Classification (`phase4a_classify.py`) using edge density and connected components
- Classifies crops into: `printed_text`, `handwriting`, `signature`, `stamp`, `image`, `empty_region`
- Saves images into categorical folders: `layouts/<region_type>/<content_type>/`
- Handles nested children (e.g., cells inside tables)
- Output: `layouts/cell/printed_text/cell_001.png`, …
- `layout_manifest.json` with: coordinates, page number, type, classification, width, height, image path

---

### Phase 4.5 — Similarity Clustering & Deduplication Engine
**Status:** ✅ Complete  
**Module:** `piply_opdf/phases/phase4b_cluster.py`  
**API:** `SimilarityClusterer().cluster(manifest, output_dir) → ClusterManifest`  
**Output:** `clusters/cluster_manifest.json`

Features implemented:
- Purely mathematical, offline, fast grouping of visually identical/similar layout crops.
- Multi-stage evaluation weights:
  - Perceptual Hashing (pHash): 40% (Exact/near matches)
  - Structural Similarity (SSIM): 30% (Lightweight OpenCV/NumPy implementation)
  - Histogram Correlation: 15% (Brightness/scan variations)
  - Edge Density: 10% (Content density check)
  - Projection Profiles (H+V): 5% (Text line structural match)
- Reduces redundant OCR passes by picking 1 representative image for N identical cells.
- Deduplicates empty regions, similar headers, footers, and standardized grid cells.
- Logical clustering: Prevents I/O overhead by writing groups to a metadata manifest rather than duplicating files on disk.

---

### Phase 5 — OCR Engine
**Status:** ✅ Complete  
**Module:** `piply_opdf/phases/phase5_ocr.py`  
**API:** `OCRProcessor().ocr_manifest(manifest) → OCRResult`  
**CLI:** `piply-opdf ocr <file>`  
**Output:** `ocr_result.json`

Features implemented:
- **PaddleOCR** as primary engine (install: `pip install piply-opdf[paddle]`)
- **Tesseract** as fallback engine (install: `pip install piply-opdf[tesseract]`)
- Pluggable `OCREngine` ABC — add new engines by subclassing
- OCRs **only** extracted layout region images (never full pages)
- Character/word/region-level confidence scores
- `ocr_result.json` with full text, word list, and confidence per region

---

### High-Level Document API
**Status:** ✅ Complete  
**Module:** `piply_opdf/document.py`

```python
from piply_opdf import Document

doc = Document("invoice.pdf")
doc.assess()           # Phase 1
doc.enhance()          # Phase 2
doc.detect_layout()    # Phase 3
doc.extract_layouts()  # Phase 4
doc.ocr()              # Phase 5

# Or all at once:
doc.run_all()
```

---

### CLI
**Status:** ✅ Complete  
**Module:** `piply_opdf/cli.py`

```bash
piply-opdf assess invoice.pdf
piply-opdf enhance invoice.pdf
piply-opdf detect-layout invoice.pdf
piply-opdf extract-layouts invoice.pdf
piply-opdf ocr invoice.pdf
piply-opdf run invoice.pdf        # full Phase 1-5 pipeline
piply-opdf --help
```

---

## ✅ Completed — Batch 2 (Phases 6–10)

| Phase | Name | Status |
|-------|------|--------|
| 6 | Confidence Analysis Engine | ✅ Complete |
| 7 | Doubt Detection Engine | ✅ Complete |
| 8 | Human Feedback Engine | ✅ Complete |
| 9 | Knowledge Engine | ✅ Complete |
| 10 | Lightweight ML Engine (Feature Clustering) | ✅ Complete |

**Batch 2 implementations:**
- ML Cache implemented utilizing `pHash`, `dHash`, HOG features, and SSIM to bypass OCR when encountering visually identical cell structures.
- SQLite-backed Knowledge Base (`piply_opdf.db`) using SQLAlchemy.
- Propagates human-verified values to identical cells (Hash Match).
- Fallback to OCR engines (PaddleOCR, Tesseract) if confidence is too low or layout is unrecognized.

---

## ✅ Completed — Batch 3 (Phases 11–12)

| Phase | Name | Status |
|-------|------|--------|
| 11 | Document Rebuilding Engine | ✅ Complete |
| 12 | Web Application (FastAPI + Tailwind) | ✅ Complete |

**Batch 3 implementations:**
- FastAPI REST service (`run_server.py`) with Jinja2 templates and Tailwind CSS.
- Interactive Dashboard for uploading and tracking documents.
- OCR Review UI for human-in-the-loop verification and ML training.
- Knowledge Base UI for searching and managing learned cell layouts.
- Reconstruct Engine allowing users to download CSV/Excel representations of detected layouts with verified values.

---

## Architecture

```
Document
  ↓
Phase 1: DocumentAssessor    → assessment.json
  ↓
Phase 2: DocumentEnhancer    → <name>_enhanced.pdf
  ↓
Phase 3: LayoutDetector      → layout.json
  ↓
Phase 4: LayoutExtractor     → layouts/<type>/<class>/ + layout_manifest.json
  ↓
Phase 4.5: SimilarityClusterer → clusters/cluster_manifest.json
  ↓
Phase 5: OCRProcessor        → ocr_result.json
  ↓ [Batch 2]
Phase 6: ConfidenceAnalyser  → enriched ocr_result.json
Phase 8/9/10: Knowledge/ML Engine → SQLite DB (piply_opdf.db) Feature Matching
  ↓ [Batch 3]
Phase 11: DocumentRebuilder  → reconstructed grid data (.csv / .xlsx)
Phase 12: Web Application    → FastAPI + Jinja2 + Tailwind
```

---

## Configuration

All thresholds are configurable via `config/default.yaml` or a custom YAML:

```bash
piply-opdf assess invoice.pdf --config my_config.yaml
```

Key tuneable values:

| Setting | Default | Description |
|---------|---------|-------------|
| `assessment.blur_threshold` | `100.0` | Laplacian variance below this = blurry |
| `assessment.noise_threshold` | `0.02` | Noise level above this = noisy |
| `assessment.contrast_threshold` | `50.0` | RMS contrast below this = low contrast |
| `assessment.skew_threshold` | `2.0` | Degrees above this = deskew needed |
| `ocr.engine` | `paddleocr` | Primary OCR engine |
| `ocr.fallback_engine` | `tesseract` | Fallback OCR engine |
| `layout_detection.header_ratio` | `0.12` | Top 12% = header zone |
| `layout_detection.footer_ratio` | `0.10` | Bottom 10% = footer zone |

---

*Last updated: Batches 1, 2, and 3 delivered.*
