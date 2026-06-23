# Piply OPDF Requirements

## Functional requirements

### Current functional requirements

- Accept PDF and image inputs.
- Assess document quality before enhancement.
- Apply enhancement selectively instead of blindly.
- Detect bordered tables.
- Detect borderless tables.
- Detect headers and footers.
- Detect columns, row candidates, and cells for structured tables.
- Export table-related images and metadata into a work directory.
- Provide a CLI for common processing tasks.
- Provide a Python API through `Document`.
- Provide a web workflow for upload, processing, component storage, OCR review, and feedback.

### Planned functional requirements

- Confidence analysis for OCR results.
- Doubt-region detection.
- Human correction loop integrated with reusable knowledge.
- Lightweight ML-assisted matching.
- Document rebuilding into corrected/searchable outputs.
- Richer layout understanding for paragraphs, titles, key-value regions, signatures, and images.

## Non-functional requirements

- Lightweight and CPU-friendly.
- Prefer OpenCV, NumPy, PyMuPDF, and other classical tooling over heavy transformer models.
- Keep modules loosely coupled and independently testable.
- Use metadata as stable contracts between stages.
- Preserve deterministic, reproducible extraction where possible.
- Support configuration through YAML.
- Keep output artifacts debuggable on disk.

## Runtime requirements

- Python 3.13+
- Core dependencies from `pyproject.toml`
- Optional OCR engines:
  - PaddleOCR
  - Tesseract

## Quality requirements

- Type hints across Python modules.
- Unit tests for implemented modules.
- Clear logging and inspectable output artifacts.
- Debug output for difficult layout cases.

## Documentation requirements

- Keep current-state docs separate from future-state vision.
- Update docs whenever CLI commands or `Document` methods change.
- Record mismatches between plan docs and implemented code explicitly.
