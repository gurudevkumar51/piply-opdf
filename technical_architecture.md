# Piply OPDF - Technical Architecture

## 1. Overview
Piply OPDF is a modular document layout extraction and analysis pipeline. It processes PDF documents by classifying them, enhancing visual quality, and extracting structural components in a strictly prioritized sequence.

## 2. Metadata-First Design
Every detected component serves as a source of truth via its metadata. Images are considered temporary artifacts.
All detectors must output metadata in the following structure:
```json
{
  "id": "component_id",
  "type": "component_type",
  "page": 1,
  "bbox": [x, y, w, h],
  "confidence": 0.95
}
```

## 3. Detector Independence & Priorities
Detectors are standalone modules located in `piply_opdf/detectors/`. A detector never depends on another detector's internal implementation; they only share metadata.

Layout detection executes in a fixed priority order:

### Stage 1: Structured Table Detection (P1)
- **Module:** `detectors/table_detector/`
- **Libraries:** OpenCV
- **Detection:** Tables with visible borders, grid tables, multi-page tables, nested tables (e.g. Invoices, Claims).
- **Output:** Table -> Columns -> Rows -> Cells

### Stage 2: Borderless Table Detection (P2)
- **Module:** `detectors/borderless_table_detector/`
- **Libraries:** PyMuPDF + OpenCV
- **Detection:** Tables without borders (e.g. Bank Statements, Financial Statements).
- **Strategy:** Uses PyMuPDF to extract text blocks and OpenCV for whitespace analysis, projection profiles, and column/text alignment. Stable column positions indicate a table structure.
- **Output:** BorderlessTableModel

### Stage 3: Header Detection (P3)
- **Module:** `detectors/header_detector/`
- **Libraries:** PyMuPDF
- **Detection:** Page Headers, Document Titles, Company Info.
- **Location:** Top 10-20% of the page.
- **Output:** `{"type": "header"}`

### Stage 4: Footer Detection (P4)
- **Module:** `detectors/footer_detector/`
- **Libraries:** PyMuPDF
- **Detection:** Page Numbers, Disclaimers, Signatures.
- **Location:** Bottom 10-20% of the page.
- **Output:** `{"type": "footer"}`

## 4. CLI Interface
The pipeline exposes specific subcommands for modular extraction:
- `piply-opdf detect-tables file.pdf`
- `piply-opdf detect-borderless-tables file.pdf`
- `piply-opdf detect-headers file.pdf`
- `piply-opdf detect-footers file.pdf`
