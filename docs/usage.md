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
| `piply-opdf layout-kb backup [dir]` | Copy **both** knowledge bases and read each copy back |
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

### Keeping it

```bash
piply-opdf layout-kb backup knowledge/backups --keep 7
```

The knowledge bases are the only files here that cannot be rebuilt. This uses
SQLite's own backup API rather than a file copy — a copy of a live database can
catch a page mid-write — and reads every copy back before reporting success.
Older copies are pruned only *after* the new one verifies.

### Teaching it from the review screen

```
POST /layout-feedback/{component_id}?action=confirmed
POST /layout-feedback/{component_id}?action=corrected&human_type=HEADING
POST /layout-feedback/{component_id}?action=deleted
GET  /layout-knowledge/stats
```

`confirmed` and `corrected` write a knowledge record **under the type the
person chose**; `deleted` writes only a feedback row, because a region that
should not exist teaches the detector rather than the knowledge base.

### Reading it back

```python
from piply_opdf.intelligence import LayoutPredictor

with LayoutKnowledgeStore("knowledge/piply_opdf_layout-001.db") as store:
    predictor = LayoutPredictor(store)

    value, reason = predictor.verdict(features)
    # 0.98  "matches a confirmed HEADER (98%)"
    # 0.0   "people confirmed regions like this as HEADER, not PARAGRAPH"
    # None  "nothing has been confirmed yet"

    for match in predictor.match(features):
        print(match.why())
```

It **never changes a type** — the result becomes the `knowledge_agreement`
confidence signal, one of six inputs. And matching nothing returns `None`, not
a low score: with a sparse store, a non-match means the store is thin rather
than the region being odd.

## Borderless table structure

Rows and cells for a table nobody drew lines on. Takes boxes, not a text layer,
so the same code serves a digital PDF and a scan where OCR supplies them.

```python
from piply_opdf.structure import TextBlock, build_grid

grid = build_grid([TextBlock(bbox, text) for bbox, text in words])
print(grid.summary())        # 4 rows x 3 columns, 1 wrapped, 0 doubtful

for row in grid.rows:
    print(row.confidence, row.evidence, row.lines)
    print([grid.cell(row.index, c.index).text for c in grid.columns])
```

**Give it one table's blocks, not a whole page** — run on a whole invoice it
will find columns in the delivery address, because that is what it was asked.

A wrapped description is folded back into its row (`row.lines > 1`), and a row
with nothing in the first column is still a row: no column is the mandatory
anchor. `row.evidence` says why each boundary was drawn, so a wrong split can
be argued with.

## Confidence

A score derived from six named signals, and taken apart afterwards.

```python
from piply_opdf.confidence import assess, review_queue, spread

assessed = [(c, assess(c, page_size=(2480, 3508), crop=crops.get(c.id)))
            for c in components]

# Is the ranking worth sorting by at all?
print(spread([conf for _, conf in assessed]).summary())
# 8 components, 0.43-0.91, variation 0.137 - usable ranking

# The twenty worst, contradicted regions first
for item in review_queue(assessed, capacity=20):
    print(f"{item.score:.2f}  {item.component.type}")
    print(item.why())
```

`why()` prints the case for the score, including what nobody could measure:

```
0.43  (ranking, not a probability)
  detector_evidence      0.60   graphic_cv rule fired
  geometry_evidence      0.17   aspect 2.0:1 against 12:1 for a rule
  knowledge_agreement    --     no layout knowledge base attached
  structural_evidence    --     no crop available
  historical_reliability --     no review history yet
  model_confidence       --     baseline did not run on this region
```

Three things to know before using it:

- **The score is a ranking, not a probability.** `Confidence.calibrated` is
  `False` until the weights are fitted against the Phase E corpus. Prefer
  `capacity=N` over a threshold — "the worst twenty" is answerable from a
  ranking, "everything probably wrong" is not.
- **A signal nobody could measure is `None`, never 0.** Four of the six are
  often unmeasurable today; they turn on by themselves as data arrives.
- **`needs_review()` is separate from the score.** One contradicted signal
  sends a region to a person however comfortable the average.

`Document.process_layout()` runs this automatically. Each component's
`confidence` becomes its evidence score and `metadata['confidence']` carries
the reasoning, which the app stores in `components.evidence_json`.
`doc.confidence_reports[page]` says whether that page's scores separated enough
to rank.

Table cells, rows and columns are scored too, at stage 10 once the grid exists.
They are judged by **containment** rather than shape — a cell's proportions are
whatever the document makes them, but a cell outside its table is a broken
grid. Their ink is not classified: at cell scale the classifier over-calls
handwriting (I27 in [backlog.md](backlog.md)).

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
