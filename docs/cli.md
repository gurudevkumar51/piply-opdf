# Piply OPDF CLI Documentation

Piply OPDF provides a command-line interface (CLI) to execute the document understanding pipeline either phase-by-phase or all at once.

## Global Options

All CLI commands accept the following global options:

- `--config <path_to_yaml>`: Override default configuration with a custom YAML file.
- `--help`: Display the help message and exit.

## Commands

### `run` (Full Pipeline)

Executes all phases in sequence: Assessment, Enhancement, Layout Detection, Layout Extraction, Clustering, and OCR. This is the recommended command for general use.

```bash
piply-opdf run <path_to_pdf>
```

**What it does:**
1. Assesses the document quality.
2. Automatically applies enhancements (deskew, denoise, sharpening) if the assessment flags the document as poor or acceptable.
3. Detects layout structures (tables, borderless tables, headers, footers, paragraphs).
4. Extracts cropped images for every layout region.
5. Groups visually identical crops to avoid redundant OCR processing.
6. Runs the OCR engine (PaddleOCR/Tesseract) on the extracted regions.
7. Generates a `master_manifest.json` containing the fully reconstructed document hierarchy and text.

---

### `assess` (Phase 1: Document Assessment)

Analyzes the document for blur, noise, contrast, and skew.

```bash
piply-opdf assess <path_to_pdf>
```

**Output:** `assessment.json` in the generated working directory. Contains boolean flags indicating if enhancement is necessary.

---

### `enhance` (Phase 2: Image Enhancement)

Applies computer vision filters to improve OCR readiness. 

```bash
piply-opdf enhance <path_to_pdf>
```

**Output:** `<filename>_enhanced.pdf` in the working directory. Only applies operations recommended by the assessment phase (unless forced via config).

---

### `detect-layout` (Phase 3: Layout Detection)

Identifies structural regions within the document.

```bash
piply-opdf detect-layout <path_to_pdf>
```

**Output:** `layout.json` containing the bounding boxes and hierarchical relationships (e.g., Table -> Rows -> Cells).

---

### `extract-layouts` (Phase 4: Layout Extraction)

Crops the detected regions into individual image files and performs content classification (e.g., printed text, signature, empty).

```bash
piply-opdf extract-layouts <path_to_pdf>
```

**Output:** A `layouts/` folder containing the cropped PNG images, and a `layout_manifest.json` cataloging them.

---

### `ocr` (Phase 5: Optical Character Recognition)

Runs the OCR engine on the extracted layout crops. Incorporates ML Cache and Hash Matching to skip OCR for previously verified identical cells.

```bash
piply-opdf ocr <path_to_pdf>
```

**Output:** `ocr_result.json` containing raw predictions, and `master_manifest.json` which aggregates the OCR text back into the layout hierarchy.

---

## Output Structure

Running `piply-opdf run invoice.pdf` creates an `uploads/invoice_piply/` folder relative to where the command was executed:

```
uploads/invoice_piply/
├── pages/                  # PDF pages converted to PNG images
├── layouts/                # Cropped regions organized by type
├── assessment.json         # Phase 1 output
├── layout.json             # Phase 3 output
├── layout_manifest.json    # Phase 4 output
├── cluster_manifest.json   # Phase 4.5 output
├── ocr_result.json         # Phase 5 raw output
└── master_manifest.json    # Final structured hierarchy and text
```
