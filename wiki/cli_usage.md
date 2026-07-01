# CLI Usage

Piply OPDF provides a command-line interface (CLI) powered by Typer for running document processing pipelines without the web UI. This allows for modular, programmatic use of the `piply-opdf` library in automated scripts or backend tasks.

You can execute the CLI using:
```bash
piply-opdf [COMMAND] [OPTIONS]
```

---

## Global Options

For most commands, you can pass the following optional flags:

- `--config`, `-c`: Path to a custom YAML config file to override defaults (e.g., thresholds, OCR engine).
- `--work-dir`, `-w`: Output directory for artefacts. If omitted, a folder named `<filename>_piply` is created alongside the source file.
- `--output`, `-o`: Override the output file path for specific commands like `enhance` and `assess`.

---

## Available Commands

### 1. `run`
**Description**: Runs the complete processing pipeline in sequence on a given document.
**Usage**: `piply-opdf run <file>`
**Functionality**: This is the primary entry point for full document processing via CLI. It executes document assessment, enhancement, layout detection, and cell extraction.
**Methods Executed**:
- `Document.assess()`
- `Document.enhance()`
- `Document.process_layout()`
**Output**: All artefacts are written to the `<filename>_piply` directory.

### 2. `assess`
**Description**: Assesses the quality of the input document (Phase 1).
**Usage**: `piply-opdf assess <file> [--json]`
**Functionality**: Evaluates the PDF/Image for contrast, noise, orientation, and resolution. Output is a JSON assessment report determining if enhancement is needed.
**Methods Executed**:
- `Document.assess()`
**Output**: `assessment.json` in the work directory, or raw JSON output in terminal if `--json` is passed.

### 3. `enhance`
**Description**: Enhances the input document (Phase 2).
**Usage**: `piply-opdf enhance <file> [--no-assess]`
**Functionality**: Applies smart image enhancements like binarization, deskewing, and contrast normalization based on the prior assessment.
**Methods Executed**:
- `Document.enhance()`
**Output**: `<filename>_enhanced.pdf` in the work directory.

### 4. `detect-tables`
**Description**: Detects structured (bordered) tables using OpenCV.
**Usage**: `piply-opdf detect-tables <file>`
**Functionality**: Detects structured tables via horizontal and vertical grid lines, extracting the individual cells.
**Methods Executed**:
- `Document.process_layout()`

### 5. `detect-borderless-tables`
**Description**: Detects borderless tables using PyMuPDF and OpenCV text alignments.
**Usage**: `piply-opdf detect-borderless-tables <file>`
**Functionality**: Parses PDF text blocks and detects tables without visible borders by analyzing horizontal/vertical alignments and column spacing.
**Methods Executed**:
- `Document.process_layout()`

### 6. `detect-headers`
**Description**: Detects page headers.
**Usage**: `piply-opdf detect-headers <file>`
**Functionality**: Detects structural page headers in the top margin area (configurable ratio).
**Methods Executed**:
- `Document.process_layout()`

### 7. `detect-footers`
**Description**: Detects page footers.
**Usage**: `piply-opdf detect-footers <file>`
**Functionality**: Detects structural page footers in the bottom margin area.
**Methods Executed**:
- `Document.process_layout()`

### 8. `detect-key-values`
**Description**: Detects key-value pairs.
**Usage**: `piply-opdf detect-key-values <file>`
**Functionality**: Detects structured key-value configurations inside the document outside of standard tables.
**Methods Executed**:
- `Document.process_layout()`

### 9. `detect-paragraphs`
**Description**: Detects paragraph and textual blocks.
**Usage**: `piply-opdf detect-paragraphs <file>`
**Functionality**: Detects distinct text groups utilizing block analysis while excluding tables and key-value bounding boxes.
**Methods Executed**:
- `Document.process_layout()`

### 10. `ocr`
**Description**: Runs OCR processing on extracted components.
**Usage**: `piply-opdf ocr <file>`
**Functionality**: Extracts strings and performs OCR processing across PaddleOCR/Tesseract.
**Output**: `ocr_result.json` containing confidence scores and text properties.

### 11. `version`
**Description**: Displays the current `piply-opdf` library version.
**Usage**: `piply-opdf version`

---

## Example Workflow

If you want to integrate the library into a bash script, you can chain specific phases:

```bash
# 1. Assess the quality (output raw JSON)
piply-opdf assess invoice.pdf --json > quality.json

# 2. Run the full extraction pipeline with a custom config
piply-opdf run invoice.pdf --config custom_thresholds.yaml
```

---

## Web Server

While the CLI is useful for modular library operations, `piply-opdf` also ships with a fully-featured FastAPI web application for Dashboard management, Human-in-the-loop OCR Review, Reconstruct engine, and Knowledge Base management.

To start the Web Server:
```bash
conda run -n py313_piply_opdf python run_server.py
```
Or you can use the provided Windows batch scripts:
- `run_web.bat`: Quick-starts the FastAPI web server with automatic live-reloading.
