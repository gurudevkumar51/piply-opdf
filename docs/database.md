# Database Schema

Verified against live databases, 2026-08-17.

Two SQLite databases, and the distinction matters:

| Database | Tables | Scope | Purpose |
|----------|--------|-------|---------|
| `piply_opdf.db` | `documents`, `components`, `ocr_predictions`, `ocr_feedback` | Per installation | Working state |
| `knowledge/piply_opdf_knowledge-*.db` | `ocr_knowledge_base`, `ocr_cluster` (view) | **Global, portable** | Verified knowledge |

The working database is disposable — delete it and reprocess. The knowledge
database is the asset: it accumulates human-verified truth and is what lets the
system improve. Keeping it separate is what allows learning to move between
projects and machines.

## Known gaps

- `components` has no per-document ordinal, so the UI displays primary keys
  (`COLUMN 2` is simply the row with `id=2`). Backlog C4.
- TITLE, graphic and unknown components are **not persisted at all**, nor are
  the segmented children of header, footer, title and key-value. They exist in
  memory and are lost at the database boundary. Backlog B5.
- `component_type` in the knowledge DB is NULL for 1,549 of 1,647 rows, which
  blocks per-type model training. Backlog G1.

---

# Working database

## `documents`

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `filename` | String | Stored name under `uploads/` |
| `file_type` | String | Extension |
| `uploaded_at` | DateTime | |
| `page_count` | Integer | |
| `status` | String | `uploaded`, `processing`, `completed`, `error` |
| `ocr_engine` | String | `paddle` or `tesseract` |

## `components`

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `document_id` | Integer (FK) | |
| `component_type` | String | See [components.md](components.md) |
| `page_no` | Integer | 1-based |
| `bbox` | String (JSON) | `[x0, y0, x1, y1]` px at render DPI |
| `confidence` | Float | |
| `manifest_path` | String | Path to the cropped image |
| `parent_id` | Integer (FK) | Self-referential: Cell → Row → Table |
| `phash` | String | Perceptual hash of the crop |
| `cluster_id` | Integer | Links to a knowledge cluster |
| `quality_score`, `rotation_angle`, `foreground_ratio`, `entropy`, `skeleton_length` | Float/Int | Quality metrics |
| `features_json` | Text | Full feature vector, transferred to knowledge on verification |

## `ocr_predictions`

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `component_id` | Integer (FK) | |
| `predicted_text` | Text | |
| `confidence` | Float | 0–1 |
| `source` | String | `ocr`, `paddle`, `tesseract`, `exact_match`, `near_match`, `ml_*` |
| `created_at` | DateTime | |

## `ocr_feedback`

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `prediction_id` | Integer (FK) | |
| `user_value` | Text | Final human-corrected value |
| `is_accepted` | Boolean | |
| `reviewed_at` | DateTime | |
| `source` | String | `human`, `knowledge_base`, `hash_match` |

---

# Knowledge database

## `ocr_knowledge_base`

One row per verified image hash. The portable asset.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `phash` | String (unique) | Perceptual hash — the lookup key |
| `cluster_id` | Integer | Groups similar entries (pHash Hamming ≤ 8) |
| `component_type` | String | **NULL for 94% of rows** |
| `text_value` | Text | The verified truth |
| `confidence` | Float | 1.0 when human-verified |
| `source` | String | `human`, `manual_import` |
| `created_at` | DateTime | |
| `quality_score`, `rotation_angle`, `foreground_ratio`, `entropy`, `skeleton_length` | Float/Int | Quality |
| `dhash`, `ahash` | String | Additional hashes |
| `width`, `height`, `aspect_ratio` | Int/Float | Geometry |
| `edge_density`, `stroke_density`, `connected_components` | Float/Int | Texture |
| `histogram_features`, `projection_profiles`, `hu_moments`, `hog_features` | Text (JSON) | Feature vectors for ML |

## `ocr_cluster` (view)

Aggregates by `cluster_id`, exposing `text_value`, `representative_phash`,
`status` and `sample_size`. Backs the Knowledge Base UI.

## Notes

- Feature columns exist so ML training can read straight from the knowledge
  base without recomputing anything.
- `cluster_id` is assigned by **image similarity, not text equality** —
  visually near-identical crops group together even when OCR read them
  differently, which is what makes a cluster useful as training data.
