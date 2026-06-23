# CLI Usage

Piply OPDF provides a command-line interface (CLI) powered by Typer for running document processing pipelines without the web UI.

You can execute the CLI using:
```bash
piply-opdf [COMMAND] [OPTIONS]
```

## Available Commands

### 1. `run`
**Description**: Runs the complete Phase 1–5 pipeline in sequence on a given document.
**Usage**: `piply-opdf run <file>`
**Functionality**: This is the primary entry point for full document processing. It executes document assessment, enhancement, grid layout detection, cell extraction, and generates the master manifest.
**Methods Executed**:
- `Document.run_all()`

### 2. `assess`
**Description**: Assesses the quality of the input document (Phase 1).
**Usage**: `piply-opdf assess <file>`
**Functionality**: Evaluates the PDF/Image for contrast, noise, orientation, and resolution. Output is a JSON assessment report determining if enhancement is needed.
**Methods Executed**:
- `Document.assess()`
- `DocumentAssessor.assess()`

### 3. `enhance`
**Description**: Enhances the input document (Phase 2).
**Usage**: `piply-opdf enhance <file>`
**Functionality**: Applies image enhancements like binarization, deskewing, and contrast normalization based on the prior assessment.
**Methods Executed**:
- `Document.enhance()`
- `DocumentEnhancer.enhance()`

### 4. `detect-tables`
**Description**: Detects table bounding boxes and grids.
**Usage**: `piply-opdf detect-tables <file>`
**Functionality**: Runs layout detection (Phase 3). It detects structured tables, columns, rows, borderless tables, headers, and footers.
**Methods Executed**:
- `Document.process_layout()`
- `TableDetector.detect_tables()`
- `BorderlessTableDetector.detect()`

### 5. `extract-grid`
**Description**: Extracts cells from detected grids.
**Usage**: `piply-opdf extract-grid <file>`
**Functionality**: Parses detected tables and extracts individual cells into cropped images.
**Methods Executed**:
- `CellExtractor.extract()`

### 6. `version`
**Description**: Displays the current `piply-opdf` version.
**Usage**: `piply-opdf version`

## Web Server

To start the web application (FastAPI), use:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```
