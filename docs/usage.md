# Usage

## Python API

```python
from piply_opdf import Document

doc = Document("invoice.pdf")

doc.assess()            # blur, noise, contrast, skew per page
doc.enhance()           # applies only what the assessment flagged
doc.process_layout()    # deskew, detect, segment

print(len(doc.tables), len(doc.key_values), len(doc.paragraphs))
print(len(doc.graphics))    # signatures, logos, images, unknown regions

doc.generate_master_manifest()
```

Work is written to `<name>_piply/` beside the source.

## CLI

Verified against `piply_opdf/cli.py`. Commands not listed here do not exist.

| Command | Purpose |
|---------|---------|
| `piply-opdf run <file>` | Full pipeline — recommended entry point |
| `piply-opdf assess <file>` | Quality measurement; `--json` for stdout |
| `piply-opdf enhance <file>` | Selective enhancement; `--no-assess` to force |
| `piply-opdf detect-tables <file>` | Bordered tables |
| `piply-opdf detect-borderless-tables <file>` | Text-layer only — nothing on scans |
| `piply-opdf detect-headers <file>` | Headers |
| `piply-opdf detect-footers <file>` | Footers |
| `piply-opdf layout-kb stats` | What the layout knowledge base holds |
| `piply-opdf layout-kb export <file>` | Write records and action log to JSON |
| `piply-opdf layout-kb import <file>` | Read a knowledge file into the store |
| `piply-opdf version` | Version |

Global options: `--config <yaml>`, `--work-dir <path>`, `--help`.
`layout-kb` takes `--store <db>`, defaulting to
`knowledge/piply_opdf_layout-001.db`.

`layout-kb match <page>` is in the plan but **not built** — matching a live page
against stored knowledge needs the LayoutPredictor, which is Phase T. A command
that printed a guess without one would be the failure this project exists to
avoid.

## Layout knowledge

What kind of region is this? Answered from what people have confirmed, never
from what a detector proposed.

```python
from piply_opdf.knowledge import (
    LayoutAction, LayoutFeedback, LayoutKnowledgeStore, Provenance,
    describe_page, tally,
)

# Describe every region on a page as ratios and relationships.
# Returns (component, features) pairs — storing a record needs both.
described = describe_page(components, page_size=(2480, 3508))

with LayoutKnowledgeStore("knowledge/piply_opdf_layout-001.db") as store:
    for component, features in described:
        store.remember(
            features,
            Provenance(source_document="sample.pdf", source_page=1,
                       detector_name=component.metadata.get("detector", "unknown"),
                       detector_version="2"),
            source="human",          # "detector" is refused
        )

    store.record(LayoutFeedback(
        action=LayoutAction.CORRECTED,
        document_id="sample.pdf", page_no=1,
        provenance=Provenance("sample.pdf", 1, "paragraph", "2"),
        detected_type="PARAGRAPH", human_type="HEADING",
    ))

    for name, score in tally(store.feedback()).items():
        print(name, score.type_accuracy, score.detection_recall)
```

Two things it will not do, both on purpose:

- `remember(..., source="detector")` raises. Only `human` and `manual_import`
  get in, so a wrong classification cannot teach itself.
- `candidates()` never returns records built by a different feature version.
  Ask for them with `include_stale=True` when exporting; never when matching.

Scores from `tally()` describe **the review queue, not the page**. A real
accuracy figure needs the gold corpus.

Schema: [database.md](database.md).

## Web application

The web parts are an optional extra, because the library does not need them:

```bash
pip install -e ".[api]"
```

```bash
conda activate py313_piply_opdf
uvicorn app.main:app --reload
```

<http://127.0.0.1:8000> — dashboard, OCR review, reconstruction, knowledge base.

The web app is a demonstration and review surface. The package is the product.

### The review screen

Built for a data entry operator working through a document, so the layout
follows what that job actually needs.

**The counts come first.** Above the list: how many components have been
checked, how many there are, and how many the system is unsure about. The last
number is the one that decides what to do next, so it is the one picked out in
colour. A bar underneath shows progress.

**Rows lead with the value, not the identifier.** A row shows the text being
verified in the largest type on the row; the component type, page and child
count sit under it in small caps. Rows the system is unsure about carry a
coloured left edge, so they can be found by scanning the margin rather than
reading every confidence badge.

**Tabs carry counts** — `KEY VALUE 14`, `LIST ITEM 66` — so it is clear how
much sits behind each before clicking.

**Least sure first** sorts the list by confidence ascending, so work starts
where the system is weakest instead of at the top of an alphabetical list.

**The keyboard drives it**, because reaching for the mouse a hundred times a
document is the difference between a tool someone can use all day and one they
cannot:

| Key | Action |
|-----|--------|
| `↑` / `↓`, or `k` / `j` | Move between components |
| `Enter` | Open the selected component |
| `A` | Accept the current suggestion |

Keys are ignored while a text field has focus, so they never interrupt someone
typing a correction.

## The baseline layout model

Optional. A trained document-layout model runs alongside the rules and the two
are fused:

```python
doc.process_layout(use_baseline=True)
```

**Off by default** — it costs several seconds a page, and it changes what is
detected, so it should be a deliberate choice you can measure either side of:

```bash
python tools/corpus_snapshot.py "path/to/documents" before.json
# change something
python tools/corpus_snapshot.py "path/to/documents" after.json
python tools/compare_snapshots.py before.json after.json
```

The two detectors are complementary rather than competing. The model finds
headings and borderless-table regions the rules miss; the rules find key-value
pairs, panels and marks the model has no concept of. Where both claim a region
and name it differently, the component is **flagged for review** carrying both
opinions — never resolved silently.

Results land on the document:

```python
doc.baseline_regions     # regions only the model found
doc.fusion_reports       # one summary per page
```

## OCR engines

PaddleOCR is the primary engine. Others sit behind the same interface, so
switching is a configuration change rather than a code change:

```yaml
ocr:
  engine: paddleocr           # primary
  fallback_engine: tesseract  # used only when the primary cannot run
  lang: en
```

```python
from piply_opdf.ocr import read_text, available_engines

available_engines()          # only the ones that can actually run
result = read_text(crop)     # uses the configured engine
result.text, result.confidence, result.engine
```

**Fallback is for unavailability, not for disagreement.** The second engine runs
when the first *cannot run at all* — its library is missing or its model will
not load. It does not run because the first returned a poor result: that would
double the slowest stage in the pipeline for pages that were never in doubt, and
turn "two readings agreed" into "we kept asking until we liked the answer".

Cross-checking two engines to *earn* confidence is a separate, deliberate call:

```python
from piply_opdf.ocr import read_with_agreement

primary, secondary, agreed = read_with_agreement(crop)
```

Use it where it pays — a value that failed a field constraint, or a high-stakes
field such as an amount or an identifier.

### Adding an engine

A file and a decorator. Nothing else changes:

```python
from piply_opdf.ocr import OCREngine, OCRResult, register

@register("myengine")
class MyEngine(OCREngine):
    def is_available(self) -> bool: ...
    def read(self, image, *, salt=False) -> OCRResult: ...
```

Then `ocr.engine: myengine` selects it.

## Output layout

```
<name>_piply/
├── pages/                  pages rendered to PNG
├── pages_enhanced/         enhanced renders, when enhancement ran
├── layouts/                cropped regions by type
├── debug/                  detection overlays
├── assessment.json
└── master_manifest.json
```

> `master_manifest.json` is currently incomplete — titles, list items and
> graphic/unknown regions are detected but not written. See
> [capabilities.md](capabilities.md#incomplete) and backlog B1.

## REST endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/upload` | Upload a PDF or image |
| `GET` | `/documents` | List documents |
| `GET` | `/documents/{id}` | Document metadata |
| `DELETE` | `/documents/{id}` | Delete document and artefacts |
| `POST` | `/process/{id}` | Run the pipeline in the background |
| `GET` | `/components/{id}` | Components with predictions |
| `GET` | `/cell-image/{component_id}` | Cropped region PNG |
| `POST` | `/ocr-cell/{component_id}` | OCR one region |
| `POST` | `/feedback/{prediction_id}` | Submit a correction |
| `POST` | `/feedback/bulk` | Accept several at once |
| `GET` | `/api/knowledge` | Search the knowledge base |
| `GET` | `/download-manifest/{id}` | Master manifest JSON |
