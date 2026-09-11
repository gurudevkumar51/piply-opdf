# Database Schema

Verified against live databases, 2026-08-17.

Three SQLite databases, and the distinctions matter:

| Database | Tables | Scope | Purpose |
|----------|--------|-------|---------|
| `piply_opdf.db` | `documents`, `components`, `ocr_predictions`, `ocr_feedback` | Per installation | Working state |
| `knowledge/piply_opdf_knowledge-*.db` | `ocr_knowledge_base`, `ocr_cluster` (view) | **Global, portable** | Verified text knowledge |
| `knowledge/piply_opdf_layout-*.db` | `layout_knowledge`, `layout_feedback` | **Global, portable** | Verified layout knowledge |

The two knowledge databases answer different questions and are kept in separate
files on purpose, so one can be shared without the other:

| Store | Answers |
|-------|---------|
| Text knowledge | "What does this say?" |
| Layout knowledge | "What kind of region is this?" |

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
- `component_type` in the text knowledge DB is NULL for 1,549 of 1,647 rows,
  which blocks per-type model training. Backlog G1.
- `layout_knowledge` declares `region_phash`, `hog_features` and `hu_moments`
  but **nothing populates them yet** — the columns exist so adding them is not
  a migration. Backlog K3.
- `ocr_knowledge_base` has **no version columns**. A row written by an older
  feature extractor is indistinguishable from a current one, which is the
  problem `layout_knowledge` was built not to have. Backlog K4.

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
| `evidence_json` | Text | The itemised evidence behind `confidence`. Present for 202 of 202 components on `sample.pdf` |
| `layout_features_json` | Text | The region as ratios and relationships, ready to become layout knowledge the moment a person confirms it. Computed during processing, because relationships need the component tree |

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

---

# Layout knowledge database

`knowledge/piply_opdf_layout-*.db`. Plain SQLite, no ORM, so anything can read
it. Written by `piply_opdf.knowledge.LayoutKnowledgeStore`.

## `layout_knowledge`

One row per region a person confirmed. Everything in it is a **ratio or a
relationship** — nothing measured in pixels, because a pixel means a different
thing at every scanner setting.

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `component_type` | String | See [components.md](components.md) |
| `source` | String | `human` or `manual_import` — **nothing else is accepted** |
| `confidence` | Float | |
| `user_id` | String | Nullable, so adding login later is not a migration |

### The versioning block

Required on every record. Without it, old knowledge silently answers with
numbers that no longer mean what they meant.

| Column | Type | Description |
|--------|------|-------------|
| `feature_version` | String | The extractor that produced the features |
| `detector_name` | String | Who proposed the region |
| `detector_version` | String | |
| `model_version` | String | The baseline model, when one was involved |
| `source_document` | String | |
| `source_page` | Integer | |
| `created_at` | String (ISO) | UTC |

### Geometry — normalised, so DPI does not matter

| Column | Type | Description |
|--------|------|-------------|
| `rel_x`, `rel_y`, `rel_w`, `rel_h` | Float | Fractions of page width / height |
| `page_band` | String | `top`, `upper`, `middle`, `lower`, `bottom` — from the region's **centre** |
| `aspect_ratio` | Float | width / height of the box |

### Relationships — what makes a record reusable

| Column | Type | Description |
|--------|------|-------------|
| `parent_type` | String | The container it sits in, if any |
| `above_type`, `below_type`, `left_type`, `right_type` | String | Nearest neighbour in each direction |
| `aligns_left_with`, `aligns_right_with` | Integer | How many siblings share that edge |

A neighbour must cover at least 20% of **the region asking**, measured against
the asker rather than the smaller box. That asymmetry is deliberate: a page
number in the margin covers 2% of a full-width table, so the table does not
call it a neighbour, while the table covers all of the page number, so the page
number does.

### Appearance — from `classification.measure`

The same function the classifier uses, so a stored record and a live region are
always measured the same way.

| Column | Type | Description |
|--------|------|-------------|
| `ink_ratio`, `stroke_width_cv`, `component_density`, `baseline_scatter` | Float | Nullable |
| `colour_clusters` | Integer | Nullable |
| `region_phash`, `hog_features`, `hu_moments` | Text | **Declared, not yet populated** |

All of these are `NULL` when the record was described from geometry alone —
absent is stored as absent, not as zero, because "no ink" and "nobody measured
it" are different facts.

## `layout_feedback`

One row per human action. Five kinds, kept apart because they mean different
things:

| Action | Meaning | What it measures |
|--------|---------|------------------|
| `confirmed` | Detector said table, human said table | In favour |
| `corrected` | Detector said paragraph, human said heading | Type accuracy |
| `added` | Human drew a region the system missed | Recall |
| `deleted` | Human removed a region the system invented | Precision |
| `rejected` | Human rejected an applied template | Template safety, not a detector |

| Column | Type | Description |
|--------|------|-------------|
| `id` | Integer (PK) | |
| `layout_knowledge_id` | Integer | The record this action was about, if any |
| `document_id`, `page_no` | String / Integer | |
| `action` | String | One of the five above |
| `detected_type`, `human_type` | String | |
| `bbox_before`, `bbox_after` | Text (JSON) | `[x, y, w, h]` |
| `user_id` | String | Nullable |
| `created_at` | String (ISO) | When the **action** happened |
| *versioning block* | | Minus `created_at`, which the action owns |

Counts derived from this log describe **the review queue, not the page** — a
person normally reviews the doubtful end of the pile. A real accuracy number
needs the gold corpus (Phase E), where the sample is chosen rather than
self-selected.

## Notes

- Feature columns exist so ML training can read straight from the knowledge
  base without recomputing anything.
- `cluster_id` is assigned by **image similarity, not text equality** —
  visually near-identical crops group together even when OCR read them
  differently, which is what makes a cluster useful as training data.
