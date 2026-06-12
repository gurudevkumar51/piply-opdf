# Piply OPDF - Table/Grid Detection Refactoring Plan

## Context

The current table extraction implementation works well on simple PDFs containing clean and perfectly aligned tables.

However, testing on real-world documents exposed several architectural weaknesses:

### Current Issues

1. Column images are not being generated.
2. Table images are not being generated.
3. Entire pages are sometimes incorrectly treated as a single table/grid.
4. Horizontal and vertical lines outside actual tables are influencing cell extraction.
5. PDFs containing multiple tables on the same page are not handled correctly.
6. Slightly rotated tables are not being corrected before table detection.
7. Row detection depends too heavily on global horizontal line detection.
8. Complex tables with variable row heights produce incorrect cell boundaries.
9. Cell extraction should be driven by column structure rather than page-level row separators.

The goal of this refactoring is to build a robust mathematical table extraction engine before continuing OCR development.

OCR work should pause until this foundation is stable.

---

# Design Philosophy

Do NOT think:

```text
Image
 ↓
Detect Cells
```

Think:

```text
Image
 ↓
Detect Table Regions
 ↓
Validate Tables
 ↓
Detect Stable Columns
 ↓
Generate Column Assets
 ↓
Detect Rows Per Column
 ↓
Consensus Row Detection
 ↓
Build TableModel
 ↓
Validate Grid
 ↓
Extract Cells
 ↓
Generate Metadata
```

Grid structure is the source of truth.

Text is not the source of truth.

OCR must never influence table detection.

---

# Architecture Overview

## Phase 1 - Assessment

Determine:

* DPI
* Noise
* Blur
* Contrast
* Skew Angle

Output:

```json
{
  "dpi": 300,
  "skew_angle": -2.4,
  "quality_score": 0.91
}
```

---

## Phase 2 - Deskew & Enhancement

Before any table detection:

### Detect Skew

Use:

* HoughLinesP
* Projection Optimization

Calculate:

```python
median_angle
```

Rotate image:

```python
corrected_angle = -median_angle
```

Apply:

```python
cv2.warpAffine(...)
```

Only after deskew should table detection begin.

---

# Phase 3 - Table Region Detection

Current implementation incorrectly assumes:

```text
Detected Lines
=
Table
```

This is incorrect.

A page may contain:

```text
Header

Paragraph

Table A

Paragraph

Table B

Signature
```

Each table must be detected independently.

---

## Table Detection Strategy

Generate:

```python
horizontal_mask
vertical_mask
```

Merge:

```python
grid_mask
```

Apply:

```python
cv2.findContours()
```

Detect:

```python
table_regions = [
    table_001,
    table_002,
    table_003
]
```

Each contour becomes a candidate table region.

---

## Table Confidence

Every detected table should be scored.

Formula:

```python
table_confidence = (
    rectangularity +
    line_density +
    continuity +
    column_stability
) / 4
```

Threshold:

```python
>= 0.70
```

Accept table.

Otherwise reject.

This prevents entire pages from becoming tables.

---

# Phase 4 - Table Asset Generation

For every detected table create:

```text
layouts/

table_001/
```

Generate:

```text
table.png
table_manifest.json
```

Example:

```json
{
  "table_id": "table_001",
  "page": 1,
  "bbox": [x1,y1,x2,y2]
}
```

This table image becomes the source for all future operations.

---

# Phase 5 - Border Repair Engine

Many real-world tables contain:

* Broken Borders
* Weak Borders
* Interrupted Borders
* Faded Lines

Before column detection execute:

```python
repair_grid_lines()
```

Pipeline:

```text
Adaptive Threshold
 ↓
MORPH_CLOSE
 ↓
MORPH_OPEN
```

Then:

```python
cv2.HoughLinesP()
```

Bridge missing segments.

Example:

```text
-----      -----
```

becomes:

```text
-------------
```

---

# Phase 6 - Column Detection

Columns are significantly more stable than rows.

Columns become the primary anchors.

---

## Detection

Use:

```python
vertical_projection = np.sum(vertical_mask, axis=0)
```

Detect peaks.

Generate:

```python
col_boundaries = [
    x1,
    x2,
    x3,
    x4,
    x5
]
```

---

## Column Asset Generation

Every detected column must generate:

```text
table_001/

columns/

├── col_001.png
├── col_002.png
├── col_003.png
├── col_004.png
└── manifest.json
```

Example:

```json
{
  "column_id":"col_003",
  "bbox":[x1,y1,x2,y2]
}
```

Column images become the source of truth for row detection.

---

## Column Confidence

Formula:

```python
column_confidence = (
    projection_score +
    line_strength +
    continuity_score
) / 3
```

Store in metadata.

---

# Phase 7 - Row Detection

Do NOT perform global row detection.

Instead:

Process each column independently.

---

## Row Detection Per Column

For each column image:

```python
horizontal_projection =
np.sum(column_slice, axis=1)
```

Detect:

* Text Bands
* Border Lines
* Empty Regions

Generate row candidates.

---

# Phase 8 - Consensus Row Detection

Current:

```text
Horizontal Line
=
Row
```

Wrong.

New:

```text
Column 1
Column 2
Column 3
Column 4
```

vote for row positions.

If:

```text
3 of 4 columns agree
```

Row accepted.

---

## Row Confidence

Formula:

```python
row_confidence = (
    border_score +
    text_alignment_score +
    projection_score
) / 3
```

---

# Phase 9 - TableModel

Introduce:

```python
class TableModel:
    columns=[]
    rows=[]
    cells=[]
```

Example:

```json
{
  "table_id":"table_001",
  "columns":[...],
  "rows":[...],
  "cells":[...]
}
```

Important:

Detected lines are NOT the source of truth.

TableModel is the source of truth.

---

# Phase 10 - Grid Verification Engine

Before saving any cell:

Validate boundaries.

---

## Cell Validation

Check:

* Left Border
* Right Border
* Top Border
* Bottom Border

Formula:

```python
grid_score = (
    left +
    right +
    top +
    bottom
) / 4
```

Example:

```text
0.95 = Good Cell
0.40 = Bad Cell
```

Reject weak cells.

---

# Phase 11 - Cell Extraction

Cells should be generated from:

```text
TableModel
```

Never directly from image lines.

---

## Handwriting Rule

If handwriting crosses into another cell:

Ignore handwriting overflow.

Rule:

```text
Grid Wins

Text Loses
```

Crop:

```python
cell_image =
image[y:y+h, x:x+w]
```

using only cell boundaries.

---

# Phase 12 - Metadata First Design

Images are temporary.

Metadata is the source of truth.

Generate:

```text
table_manifest.json
column_manifest.json
cell_manifest.json
table_model.json
```

These files will later drive:

* OCR
* Clustering
* Learning
* Searchable PDF Generation
* Document Reconstruction

---

# Debug Mode

Command:

```bash
piply-opdf debug-layout file.pdf
```

Generate:

```text
debug/

01_deskew.png
02_threshold.png
03_table_regions.png
04_repaired_lines.png
05_columns.png
06_rows.png
07_table_model.png
08_cells.png
09_grid_confidence.png
```

Purpose:

* Validate algorithms
* Compare intermediate stages
* Troubleshoot difficult PDFs

---

# Future Extensibility

Current focus:

```text
Document
 ↓
Table
 ↓
Column
 ↓
Cell
```

Future modules:

```text
Paragraph
Title
Signature
KeyValue
Image
Stamp
```

must plug into the same architecture.

Keep every detector independent.

Avoid coupling table logic with OCR or other layout components.

---

# Success Criteria

The implementation should:

* Detect multiple tables on a page.
* Prevent entire pages from being treated as tables.
* Correct skewed tables before extraction.
* Export table images.
* Export column images.
* Build a metadata-driven TableModel.
* Handle broken borders.
* Handle faint borders.
* Handle wrapped text.
* Handle variable row heights.
* Produce deterministic cell extraction.
* Remain lightweight and CPU-only.
* Avoid AI, ML, and OCR dependencies.

The primary goal is not OCR.

The primary goal is creating a reliable, reusable, metadata-driven TableModel that becomes the foundation for all future Piply OPDF capabilities.

And finally keep cleaning the non-related or non-functional code so our codebase exists clean & light

Primary focus: Light, accurate & Fast
