# Manifest Specification

**Status: design. Not yet implemented — backlog B1, B2, B6, B7, B8.**

The manifest is the authoritative record of a document. Everything downstream —
HTML reconstruction, review UI, exports, reprocessing — reads the manifest and
nothing else. If a fact about the page is not in the manifest, it does not
exist as far as the system is concerned.

Two consequences drive the design:

1. **Nothing may be left out.** Every region of every page is accounted
   for, including content no detector could classify.
2. **It must be sufficient to rebuild from.** Enough geometry, ordering and
   style to produce HTML without re-reading the source.

---

## Structure

A single file does not scale: a 24-page scan segmented to word level produces
tens of thousands of nodes — slow to write incrementally, impossible to load
partially, and requiring a full rewrite whenever one page is reprocessed.

The split is **not** a retreat from "one bible". The master manifest remains
the single entry point; it is a lazy-loading index.

```
<document>_piply/
├── master_manifest.json          ← entry point, refers to everything
├── pages/
│   ├── page_001.json
│   └── page_002.json
└── layouts/
    ├── table_001_001.json
    └── panel_001_002.json
```

**Every layout gets its own file.** Not just containers — each table,
paragraph, panel, header, key-value and graphic is written to `layouts/`.
Components below layout level stay inside their layout's file.

Three reasons:

- reprocessing one page rewrites only that page's files, not the whole document
- a reader wanting page 4's titles loads one small file, not the lot
- a single layout can be handed to another system on its own

A reader that wants the whole tree follows the references and gets it.

---

## Master manifest

```jsonc
{
  "schema_version": "1.0",

  "document": {
    "source_path": "uploads/sample10.pdf",
    "source_sha256": "9f2c…",
    "page_count": 24,
    "created_at": "2026-08-17T10:14:03Z",
    "producer": { "name": "piply-opdf", "version": "0.4.0" }
  },

  "processing": {
    "render_dpi": 300,
    "ocr_engine": "paddleocr",
    "stages": ["assess", "enhance", "deskew", "detect", "segment", "ocr"],
    "completed_pages": 24,
    "status": "complete"              // pending | partial | complete | error
  },

  "pages": [
    {
      "page": 1,
      "manifest": "pages/page_001.json",
      "sha256": "1a7b…",
      "size_px": [2550, 3300],
      "size_pt": [612.0, 792.0],
      "render_dpi": 300,

      "orientation": 0,               // 0 | 90 | 180 | 270, applied
      "skew_correction": -2.4,        // degrees applied
      "enhancements": ["denoise", "contrast"],

      "quality": { "blur": 142.7, "noise": 0.011, "contrast": 61.2, "rating": "good" },

      "component_count": 187,
      "coverage": { "ink_accounted": 0.997, "unclassified_regions": 2 }
    }
  ],

  "index": {
    "by_type": { "TABLE": ["table_001_001"], "PANEL": ["panel_001_002"] },
    "by_page": { "1": ["title_001_001", "panel_001_002"] }
  },

  "reading_order": ["p1:title_001_001", "p1:panel_001_002", "p2:…"]
}
```

`coverage.ink_accounted` makes the completeness invariant measurable: the
fraction of page ink inside some component, expected ~1.0. A drop is a
detection regression, visible without inspecting anything.

---

## Page manifest

```jsonc
{
  "schema_version": "1.0",
  "page": 1,
  "size_px": [2550, 3300],
  "reading_order": ["title_001_001", "panel_001_002", "paragraph_001_001"],
  "columns": [ { "index": 1, "bbox": [120, 400, 1100, 2600] } ],
  "components": [ /* nodes, nested */ ]
}
```

---

## Component node

One recursive shape, used everywhere.

```jsonc
{
  "id": "panel_001_002",                 // <type>_<page>_<ordinal>
  "type": "PANEL",
  "index": 2,                            // ordinal within type, per page
  "page": 1,
  "level": 1,                            // 0 = page, 1 = layout, 2+ = component
  "is_review_unit": false,               // true only on the last level

  "bbox": [180, 2400, 2100, 620],        // [x, y, w, h] px at render_dpi
  "bbox_source": [175, 2388, 2104, 631], // same region in the ORIGINAL frame,
                                         // before deskew/rotation

  "confidence": 0.82,
  "candidates": [                        // present only for near-ties
    { "type": "LOGO",  "confidence": 0.55 },
    { "type": "STAMP", "confidence": 0.45 }
  ],
  "provenance": {
    "detector": "panel",
    "strategy": "cv-frame",
    "needs_ocr": true,
    "verified_by": "human|null",         // set once an operator confirms
    "verified_at": "2026-08-17T11:02:00Z"
  },

  "text": "",
  "text_source": "ocr|text_layer|knowledge|human",
  "image_path": "layouts/panel/panel_001_002.png",

  "style": {                             // omitted when unknown
    "relative_size": 1.8,                // vs page median line height
    "emphasis": "bold",
    "alignment": "center"
  },

  "children": [ /* nested */ ],
  "manifest": "layouts/panel_001_002.json"   // when externalised
}
```

**`children` and `manifest` are mutually exclusive.** A node either inlines its
children or points at a file, never both.

### Identifiers

`<type>_<page:03d>_<ordinal:03d>` — e.g. `panel_001_002`. Ordinals are per page
per type, 1-based, gap-free.

They are deliberately **not** database keys: the manifest must be reproducible
from the source alone, and identifiers must survive reprocessing so human
feedback stays attached to the right region.

---

## Levels and reading order

Everything is a unit, and units sit inside other units:

```
Level 0   PAGE          the whole page
Level 1   LAYOUT        table, paragraph, panel, header…
Level 2   COMPONENT     row, column, sentence…
Level 3   COMPONENT     cell, word…
Last      REVIEW UNIT   what a person checks in the UI
```

`reading_order` is decided **level by level**. Inside any unit, its children are
ordered top to bottom, then left to right. A panel is therefore one item in the
page order, and its contents are ordered inside it — they never mix with text
outside the panel.

`is_review_unit` marks the last level. The UI shows these to an operator; units
above them are structure, not something to check directly.

---

## Containers

`PANEL`, `TABLE` and `BORDERLESS_TABLE` hold children of any type, discovered
by running detection again scoped to the interior.

This is what makes a boxed region tractable. A framed block holding a
signature, a stamp, two key-value pairs and a caption is not a special case
needing its own parser — it is a `PANEL` whose children come from the detectors
that already exist.

```jsonc
{
  "id": "panel_001_003", "type": "PANEL",
  "children": [
    { "id": "signature_001_001", "type": "SIGNATURE" },
    { "id": "stamp_001_001",     "type": "STAMP" },
    { "id": "key_value_001_004", "type": "KEY_VALUE",
      "children": [
        { "id": "key_value_001_004_key",       "type": "WORD", "metadata": { "role": "key" } },
        { "id": "key_value_001_004_separator", "type": "WORD", "metadata": { "role": "separator" } },
        { "id": "key_value_001_004_value",     "type": "WORD", "metadata": { "role": "value" } }
      ]
    }
  ]
}
```

---

## Completeness

Every page satisfies:

> Every connected region of ink belongs to exactly one leaf component.

Enforced by the residual sweep, which runs last with all prior detections as
exclusions. Whatever remains becomes `UNKNOWN` — captured, cropped, indexed and
reviewable, never dropped.

This is the achievable part of "100% perfect": **100% of content is captured.**
Classification accuracy is separate and measured — see [quality.md](quality.md).

---

## Integrity and versioning

- `schema_version` on every file; readers reject unknown majors
- `sha256` per referenced child — a stale or hand-edited file is detectable
- `source_sha256` — reprocessing a changed source is detectable
- All paths relative to the work directory, so the folder is portable

## Incremental writing

`processing.status` is `partial` while pages are still being written, and a
page appears in `pages[]` only once its own manifest is complete and
checksummed. A reader can therefore consume page 1 while page 24 is still
processing — what makes page-by-page review possible (backlog C1).

---

## Open questions

1. **Style fidelity depth** — relative size and emphasis, or full font
   matching? *Proposal: relative only. Absolute font identification needs
   matching that conflicts with the lightweight constraint.*
2. **Word-level nodes** — a 24-page document split down to words is large.
   *Proposal: always externalise below sentence level; make word emission
   configurable.*
