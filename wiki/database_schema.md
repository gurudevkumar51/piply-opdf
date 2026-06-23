# Piply OPDF Database Schema

The web application (FastAPI) utilizes a SQLite database (via SQLAlchemy) to store document states, component layouts, extracted images, OCR predictions, and a knowledge base of verified records.

Below is the exhaustive list of tables, columns, and their purposes.

---

## 1. `documents`
**Purpose**: Tracks uploaded documents, their overall metadata, and processing status.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique document identifier. |
| `filename` | String | Original filename of the uploaded file. |
| `file_type` | String | Extension of the file (e.g., "pdf", "png"). |
| `uploaded_at` | DateTime | Timestamp of when the document was uploaded. |
| `page_count` | Integer | Number of pages detected in the document. |
| `status` | String | Current processing phase (`uploaded`, `processing`, `completed`, `error`). |

---

## 2. `components`
**Purpose**: Stores a hierarchical mapping of detected layout components (tables, rows, cells, headers, footers).

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique component identifier. |
| `document_id` | Integer (FK) | Reference to the parent document. |
| `component_type`| String | The semantic type of component (`TABLE`, `ROW`, `CELL`, `BORDERLESS_TABLE`, `HEADER`, `FOOTER`, etc.). |
| `page_no` | Integer | The 1-based index of the page where the component exists. |
| `bbox` | String | A JSON representation of the bounding box coordinates `[x, y, w, h]` or `[x1, y1, x2, y2]`. |
| `confidence` | Float | Confidence score from the layout detection engine. |
| `manifest_path` | String | The path on disk where the extracted image component (or sub-manifest) is saved. |
| `parent_id` | Integer (FK) | Self-referential ID denoting the hierarchical parent (e.g., Cell -> Row -> Table). |

---

## 3. `ocr_predictions`
**Purpose**: Stores the raw output returned by the OCR engine (PaddleOCR/Tesseract) for each individual cell/component.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique OCR prediction identifier. |
| `component_id` | Integer (FK) | Reference to the specific `components` record this prediction belongs to. |
| `predicted_text`| Text | The raw text predicted by the OCR engine. |
| `confidence` | Float | The OCR engine's confidence score in the text (normalized between 0 and 1). |
| `created_at` | DateTime | When the prediction was generated. |

---

## 4. `ocr_feedback`
**Purpose**: Stores human interactions, edits, and confirmations regarding the OCR predictions.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique feedback identifier. |
| `prediction_id` | Integer (FK) | Reference to the raw `ocr_predictions` record. |
| `user_value` | Text | The final, human-corrected text value for the cell. |
| `is_accepted` | Boolean | True if the human explicitly approved or saved this value. |
| `reviewed_at` | DateTime | When the user confirmed the value. |

---

## 5. `image_features`
**Purpose**: Stores perceptual hashing (pHash) and visual metadata to enable fuzzy-matching, deduplication, and cross-referencing between identical cells across different documents.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique feature identifier. |
| `component_id` | Integer (FK) | Reference to the cropped `components` record. |
| `phash` | String | Perceptual Hash for visually identifying similar structure. |
| `dhash` | String | Difference Hash. |
| `ahash` | String | Average Hash. |
| `width` | Integer | Pixel width of the component image crop. |
| `height` | Integer | Pixel height of the component image crop. |
| `aspect_ratio` | Float | Width/height ratio of the component. |
| `edge_density` | Float | Measurement of edges/pixel complexity inside the crop. |
| `histogram_features`| Text | JSON array representing color/grayscale histogram data. |

---

## 6. `ocr_knowledge_base`
**Purpose**: A global registry of "known" cell images mapped to their correct text. Whenever a cell is approved, its pHash is stored here. Subsequent documents can instantly look up a pHash in this table to auto-fill the human-approved text without needing manual review.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Unique Knowledge Base identifier. |
| `image_hash` | String | The perceptual hash (pHash) representing the exact visual layout of the crop. |
| `text_value` | Text | The "source of truth" text associated with this hash. |
| `confidence` | Float | The confidence (often `1.0` if manually entered by a human). |
| `source` | String | Tracks whether the value originated from `human` (user edit) or `paddle` / `tesseract` / `voted`. |
| `created_at` | DateTime | When this knowledge record was established. |

---

## 7. `knowledge_base` (Legacy/Alias)
**Purpose**: An older or simplified variant of `ocr_knowledge_base` storing `image_hash` mapping to `text_value`.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | Identifier. |
| `image_hash` | String | pHash. |
| `text_value` | Text | Truth text. |
| `source` | String | Source tracking (`user_feedback`, `manual`). |
| `confidence` | Float | Truth confidence. |
| `created_at` | DateTime | Timestamp. |
