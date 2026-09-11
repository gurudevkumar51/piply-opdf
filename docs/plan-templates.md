# Implementation Plan — Intelligent Scanned-PDF Parser

**This is the only implementation plan.** The older `plan.md` has been retired;
what was still useful from it lives in [Beyond the parser](#beyond-the-parser),
[Rules for every step](#rules-for-every-step) and
[What I need from you](#what-i-need-from-you).

**Status: Phase Q and Phase B are built. Phases K and C are part built — the
layout knowledge store exists and is empty; confidence is derived from evidence
but not yet calibrated or wired in. Everything else is plan.**
See [Progress](#progress) for the line-by-line position.

*Fifth revision. Confidence becomes an evidence score. Nothing is trusted
silently. The structural image pipeline comes before labelling. Borderless
tables are rebuilt around continuation, not row lines.
See [what changed](#what-changed-in-this-revision).*

---

## The goal

> **A package that turns a scanned PDF into structured, verified, digital
> content — and gets better every time somebody corrects it.**

The **package** is the product. The web application and the CLI are consumers.

---

## The governing principle

> **Never silently trust a classification.**

The failure this exists to prevent:

```
   Wrong classification
          +
   High confidence
          +
   No review
          =
   A silently bad document
```

Nobody catches that later. It is worse than a blank marked "needs a human",
because a blank is visible and a confident error is not.

So **every component carries its reasoning, not just its answer**:

```
component
  predicted_type          what it is
  evidence                the signals behind that, itemised
  confidence              derived from the evidence, calibrated
  source_detector         who proposed it
  knowledge_match         what the layout knowledge base said, if anything
  review_status           unreviewed | confirmed | corrected | rejected
```

Two rules follow, and neither may be relaxed:

1. **Insufficient confidence means human review.** Not a guess with a shrug.
2. **A template match can never override geometry verification.** If the
   verifier says the ink is not where the template expects it, the match loses —
   however high its score.

---

## The pipeline

```
   PDF arrives
        │
   1.  QUALITY CHECK           blur, noise, contrast, skew, orientation
        │
   2.  THREE IMAGES            original / structural_reference / working
        │
   3.  BASELINE DETECTION      trained layout model
        │
   4.  PIPLY DETECTION         rules and CV, where the model is not enough
        │
   5.  LAYOUT FUSION           combine the two, disagreement is a signal
        │
   6.  TEMPLATE & LAYOUT INTELLIGENCE
        │   FingerprintMatcher → TemplateMatcher → LayoutPredictor
        │
   7.  GEOMETRY VERIFIER       does the expectation match the actual page?
        │
   8.  CONFIDENCE              a measured number, per component
        │
   9.  HUMAN REVIEW            only what is doubtful
        │
   10. LEARN                   corrections recorded by kind
        │
   11. OUTPUT                  structured, searchable document
```

---

## Three images

**Revised.** An earlier version had layout detection reading the *working*
image. It reads the **structural** image instead — the branch matters, and the
measurements support it.

```
                        ORIGINAL
                   immutable source of truth
                            │
                  orientation + safe deskew
                            │
                     STRUCTURAL IMAGE
                geometry only — no sharpening,
                  no thresholding, no denoise
                            │
             ┌──────────────┴──────────────┐
             ↓                             ↓
   Layout detection                enhancement, when it helps
   Table detection                          ↓
   Fingerprinting                   OCR WORKING IMAGE
   Geometry verification                    ↓
                                           OCR
```

| Image | Purpose | Who reads it |
|---|---|---|
| `original` | Immutable source | Reconstruction, export, audit |
| `structural` | Orientation + safe deskew **only** | Layout, tables, fingerprints, geometry |
| `working` | Denoise, contrast, sharpen | OCR |

**One change from the diagram as given:** `working` is derived from
`structural`, not from `original`. OCR on a page that is still rotated 2° is
worse than OCR on a straightened one, so the enhancement branch should inherit
the orientation and deskew rather than start again from the raw scan.

**Why layout reads `structural`.** Measured on `sample.pdf`: the enhanced page
lost a 171-cell table at 0.05° of rotation where the unenhanced page survived
2°. Sharpening for legibility thins the hairline rules table detection depends
on. Layout and OCR want opposite things from the image.

**The guard.** Even on the OCR branch, enhancement is accepted only if it does
not destroy structure:

```
   if structure_evidence(enhanced) < structure_evidence(structural) * 0.9:
       working = structural
```

`structure_evidence` = long rule count plus the edge-projection signature. When
the assessment says no enhancement is needed, `working` *is* `structural`.

---

## Layer separation

```
   piply_opdf/                    THE PACKAGE
        ├── quality/              assess, enhance, orientation
        ├── detectors/            Piply's own rules and CV
        ├── baseline/             adapter for the trained layout model
        ├── fusion/               combining detector outputs
        ├── knowledge/            text, layout and template stores
        └── intelligence/         Template & Layout Intelligence
              ├── fingerprint.py    FingerprintMatcher
              ├── template.py       TemplateMatcher
              ├── predictor.py      LayoutPredictor
              └── verifier.py       GeometryVerifier

   piply_opdf_cli/                thin shell over the package
   app/                           screens, ownership, review
```

The CLI moves out of the package: today it forces the library to depend on
`typer` and `rich` for code no library user needs.

---

## Phase E — The gold corpus and the metrics

**The biggest missing engineering item.** It comes second, not first: the
structural image pipeline (Phase Q) has to be settled before anything is
labelled, or the labels describe pages the system will never see again.

### The corpus

```
tests/fixtures/
    documents/          the PDFs and images
    expected/           one JSON per page
```

```json
{
  "source": "Sbizhub_C2219080509040.pdf",
  "page": 1,
  "regions": [
    { "component_type": "table",  "bbox": [100, 200, 1500, 900] },
    { "component_type": "header", "bbox": [80, 60, 2300, 120] }
  ]
}
```

### What gets measured

| Metric | Why |
|---|---|
| Detection precision / recall, per type | Which types are weak |
| IoU | Whether boxes are in the right place, not just present |
| Table accuracy | Whole-table correctness |
| Row / column accuracy | Structure, not just the outer box |
| OCR accuracy | Character and field level |
| Template match precision | Does a claimed match hold |
| **False template match rate** | **Critical safety metric** |

### False template matches are the dangerous failure

A system that says `unknown` is safe. A system that says **95% match** and is
wrong silently applies the wrong layout to a real document, and nobody looks
again. This metric gates whether template matching may ever be switched on.

### Status

The **harness already exists** — `piply_opdf/quality/accuracy.py`, with IoU
matching, per-type precision/recall/F1 and a documented label format, tested
against synthetic labels. It has never had real labels to run on.

So Phase E is mostly **labelling**, not building.

### CLI

```
piply-opdf eval run                 score the corpus
piply-opdf eval report --baseline   compare against the last run
```

---

## Phase Q — Quality, orientation, three images

**✅ Done.**

Assessment (blur, noise, contrast, skew) and enhancement (deskew, denoise,
CLAHE, sharpen, border repair) already existed.

Added: **orientation detection**, the three-image pipeline wired through
`document.py`, and a working, configurable OCR engine.

One honest limit. Orientation reports **upright or sideways**; it does not
report *which way up*. Four separate measurements were tried and each failed on
real pages — the strongest scored 2 of 8 — so a sideways page is flagged for a
person rather than silently rotated the wrong way. Written up in
[backlog.md](backlog.md) as I17.

```
piply-opdf assess <pdf>
piply-opdf enhance <pdf> --out <dir>
```

---

## Phase B — Baseline detector, with Piply's rules on top

**✅ Done.**

Built as an adapter (`piply_opdf/baseline/`) with PP-StructureV3 behind it, and
fusion (`piply_opdf/fusion/`) on top. It is **off by default**: the package runs
unchanged without it.

Tested on its own behaviour, **not yet scored against a corpus** — see
[Progress](#progress).

### The recommendation, adopted

Stop building every generic layout detector by hand. Use a trained document
layout model as the **baseline**, and keep Piply's rules for what the model does
not do.

```
                      ┌── Baseline model (PP-DocLayout / PP-Structure)
                      │
   Working image ─────┼── Piply detectors (rules + OpenCV)
                      │
                      └── Layout knowledge
                                ↓
                         LAYOUT FUSION
                                ↓
                          Verification
                                ↓
                          Final layout
```

**Baseline handles the generic:** title, text, table, figure, list,
header/footer, reading order — and would immediately address open defects that
Piply's rules handle badly: rotated text, large display text, reading order.

**Piply specialises where the generic model is not enough:** borderless tables,
key-value pairs, nested regions, organisation-specific layouts, template
knowledge, geometry validation, human feedback.

### What this costs — stated plainly

`paddleocr` is **not currently installed**. Verified:

| | State |
|---|---|
| `paddlepaddle` | installed (3.3.1) |
| `paddleocr` | **not installed** — declared only as an optional extra |
| `pytesseract` | installed |
| `tesseract` binary | **not installed** |

So today **neither OCR nor any baseline model can run.** Adopting PP-Structure
makes `paddleocr` a required dependency of the parser, plus its model weights.
That is real weight, and it pulls against the "maximum light" rule and against
backlog E1–E3, which is about *removing* dependencies.

The counter-argument, which I think wins: OCR needs Paddle anyway, the weights
download once and then run offline, and the alternative is hand-building
detectors a trained model already does better.

### The sequencing point that matters

**Phase E must come first.** Swapping an unmeasured detector for another
unmeasured detector is not progress. With the evaluation corpus in place the
question becomes answerable per type:

```
   for each component type:
       baseline precision/recall   vs   Piply precision/recall
       → whichever wins, wins
```

Fusion then has evidence behind it rather than a guess about which to trust.

### Fusion rules

| Baseline | Piply | Result |
|---|---|---|
| TABLE | TABLE | agree — high confidence |
| TABLE | *nothing* | take baseline, moderate confidence |
| *nothing* | BORDERLESS_TABLE | take Piply — its speciality |
| TEXT | KEY_VALUE | take Piply — more specific |
| TABLE | PARAGRAPH | **disagreement → flag for review** |

Disagreement is not a problem to be resolved silently. It is the strongest
available signal that a human should look.

### Adapter, not hard dependency

`piply_opdf/baseline/` is an **adapter**. The package keeps working with the
baseline absent — it falls back to Piply detectors alone. This keeps the library
usable without the heavy extra, and keeps the tests runnable.

```
piply-opdf detect <pdf> --baseline paddle|none
```

---

## Phase K — Knowledge architecture

**🔨 Part built.** The layout store and the action taxonomy exist and are
tested; nothing writes to them from the running system yet, and template
knowledge is still Phase T.

**Three separate stores**, each its own file so other applications can use them.

| Store | Answers | Today |
|---|---|---|
| Text knowledge | "What does this say?" | ✅ 1,656 entries |
| **Layout knowledge** | "What kind of region is this?" | 🔨 built and empty |
| **Template knowledge** | "What does a page of this family look like?" | ❌ nothing |

*Built and empty* is the honest description: `LayoutKnowledgeStore` works, the
schema is in [database.md](database.md), the CLI reads and moves it — but the
review screen does not call `remember()` yet, so no human decision has reached
it. That wiring is K5 in [backlog.md](backlog.md), and it waits on the review
work in Phase U.

One feature extractor in the package feeds all three, so they cannot drift.

### Versioning — required on every record  ✅

Detectors and models will change. Without versions, old knowledge becomes
impossible to interpret and silently poisons new results.

Delivered in `piply_opdf/knowledge/provenance.py`, and enforced rather than
documented: `candidates()` filters on the current `FEATURE_VERSION`, and
`stats()` reports stale records separately so a store that looks full but
answers nothing is visible instead of confusing.

```
  feature_version        the extractor that produced the features
  detector_name          which detector proposed it
  detector_version
  model_version          baseline model, when one was involved
  source_document
  source_page
  created_at
```

**The same applies to template fingerprints.** A fingerprint built by feature
extractor v1 cannot be compared with one built by v2 — matching must either
refuse across versions or re-derive the older one.

### Layout knowledge — geometry and relationships  ✅

```
layout_knowledge
  id, component_type, source, confidence
  <versioning block above>

  -- appearance
  region_phash, hog_features, hu_moments,
  ink_ratio, stroke_width_cv, component_density,
  baseline_scatter, colour_clusters, aspect_ratio

  -- geometry, normalised so page size and DPI do not matter
  rel_x, rel_y, rel_w, rel_h, page_band

  -- relationships
  parent_type, above_type, below_type, left_type, right_type,
  aligns_left_with, aligns_right_with
```

Relationships are what make this reusable: a logo is a colourful blob *in a
corner, above a heading*; a header row is text *above rows sharing its column
edges*.

### Human actions, recorded by kind  ✅

Not `agreed` / `disagreed`. Five distinct actions, because they mean different
things:

| Action | Meaning |
|---|---|
| `CONFIRMED` | Detector said table, human said table |
| `CORRECTED` | Detector said paragraph, human said heading |
| `ADDED` | Human drew a region the system missed entirely |
| `DELETED` | Human removed a region the system invented |
| `REJECTED` | Human rejected an applied template outright |

```
layout_feedback
  id, layout_knowledge_id, document_id, page_no,
  action, detected_type, human_type,
  bbox_before, bbox_after,
  user_id, created_at,
  <versioning block>
```

This is what makes detector performance measurable: `CORRECTED` counts against
a detector's accuracy, `ADDED` against recall, `DELETED` against precision.
Collapsing them into one counter throws that away.

### CLI

```
piply-opdf layout-kb stats | export <file> | import <file>     ✅ built
piply-opdf layout-kb match <page>                              ⬜ needs Phase T
piply-opdf template  list  | show <name>  | export | import    ⬜ Phase T
```

`match` is deliberately absent rather than stubbed. Matching a live page
against stored knowledge is the LayoutPredictor, and a command that printed a
guess without one would be precisely the failure the governing principle names.

---

## Phase C — Confidence as an evidence score

**🔨 Part built.** The evidence model, the six signals and the review queue
exist (`piply_opdf/confidence/`, 43 tests), and the pipeline and review screen
both use them: "need a look" on `sample.pdf` went from 167 to 25, and an
operator can open the case for any score.

Two things are not done. The **calibration** — the weights are argued rather
than fitted, so the score is a ranking and `Confidence.calibrated` is `False`
everywhere; that waits on Phase E. And **table cells are not scored**, which is
200 of 202 components on that page (I26 in [backlog.md](backlog.md)).

Not "confidence has to be earned", which is vague. The rule:

> **Confidence must be derived from measurable evidence and calibrated against
> human-labelled results.**

### The evidence

Confidence is a combination of signals, each of which can be pointed at:

```
confidence = f(
    detector_evidence,        how strongly the rule or model fired
    geometry_evidence,        does the shape agree with the claimed type
    knowledge_agreement,      does the layout knowledge base concur
    structural_evidence,      ink, rules and alignment support the type
    historical_reliability,   how often this detector was right for this type
    model_confidence          the baseline model's own score, when present
)
```

**Historical reliability is one input, not the whole thing.** A detector that
has been right 90% of the time is not therefore right about *this* region — the
other five signals are about the region in front of it.

### Calibration  ⬜ *waiting on Phase E*

`f` is not invented. It is **fitted against the labelled corpus from Phase E**,
so that a component reported at 0.90 is right about 90% of the time. Until that
fitting has been done, the score is a ranking, not a probability, and must be
described that way.

Re-fitted whenever a detector changes — which is what the `detector_version`
field in Phase K is for.

### What it replaces

Today every value is a **literal in the code** — a paragraph is always 0.70, a
logo always 0.85. They mean "this rule fired". Consequence: "review the doubtful
ones" selects everything.

Confirmed by running the app: on `sample.pdf` the review screen reports
**167 of 202 components as "need a look"**. A list that long is a list nobody
works through, so in practice nothing is reviewed.

Being precise about the cause, because it is not quite the obvious one: those
202 components carry 45 distinct confidences between 0.25 and 1.0, so they do
*not* all sit in one band. 199 of them are cells, rows and columns numbered by
the grid builder; only three are detector-level regions carrying literals. The
flood comes from cutting all of them at 0.95 — one threshold across numbers
that were never on the same scale. So both halves matter: evidence gives the
detector-level scores a meaning, and capacity replaces the threshold that was
never going to work across mixed scales.

The measured difference on a synthetic page with three deliberately misplaced
regions:

| | Score range | Spread | Usable as a ranking |
|---|---|---|---|
| Literals | 0.70 everywhere | 0.000 | No |
| Evidence | 0.43 – 0.91 | 0.137 | Yes — the three bad regions sort to the front |

**Capacity, not threshold.** While the score is a ranking, "the worst twenty"
is answerable and "everything probably wrong" is not, so
`review_queue(..., capacity=N)` is the primary control. `spread()` reports when
scores bunch too closely to rank at all, which is the failure being replaced,
stated as something the system can notice about itself.

### Evidence is stored, not just the number

Per the governing principle, the itemised evidence is kept on the component. An
operator asking *"why is this only 0.55?"* gets an answer:

```
  detector_evidence      0.70   text-layer key-value rule
  geometry_evidence      0.40   separator column is unusually wide
  knowledge_agreement    ——     nothing similar seen
  structural_evidence    0.65   aligned, but only two rows
  historical_reliability 0.88   this rule is usually right
  model_confidence       ——     baseline did not run
```

That is also what makes a bad calibration debuggable rather than mysterious.

### A second OCR engine, selectively

*Not* on every region — that doubles the slowest stage for pages never in doubt.
Only where the first engine is unsure, where a value fails a field constraint
(a date that will not parse, a column that will not sum), or on high-stakes
fields such as amounts and identifiers.

---

## Phase R — Borderless tables, rebuilt around continuation

The single biggest structural gap for the documents this system targets. A bank
statement, a remittance advice, an invoice — few or no ruled lines, and the
whole value is in the relationship between columns.

### Why "columns → rows → cells" is not enough

The obvious approach — find persistent vertical gaps, then horizontal ones, then
cells at the intersections — **fails on exactly these documents**:

```
   Date       Description
              continuation of long description
              another continuation
   05/01      Payment                      500
```

Lines two and three are **not new rows**. They are the same row, wrapped. A row
detector driven by horizontal whitespace produces three rows where there is one,
and every column after `Description` is then misaligned against the wrong row.

### The pipeline

```
   Text blocks
        ↓
   candidate columns              persistent vertical gaps
        ↓
   horizontal alignment           which blocks share a column
        ↓
   baseline clustering            which blocks share a writing line
        ↓
   multi-line continuation        is this a new row, or a wrap of the last?
        ↓
   row candidates
        ↓
   row confidence                 how strongly is this a row boundary
        ↓
   cells
```

### The rule that makes it work

> **No single column may be the mandatory row anchor.**

A row is not "wherever the date column has a value". Some rows have no date;
some have a value only in the last column; a total line may have only two cells
filled. Anchoring on one column bakes in an assumption about the document that
will be wrong on the next one.

Instead, a row boundary is evidence-weighted like everything else: a new value
in *any* column that normally starts a row, a baseline gap larger than the
within-row line spacing, a change in indentation, a horizontal rule if one
happens to exist.

### Continuation, concretely

A block is a **continuation** of the row above rather than a new row when:

- it sits in the same column, and
- no other column has a new value on its baseline, and
- it is indented to the column's text start rather than to a new row's start,
  and
- the vertical gap matches within-paragraph line spacing rather than row
  spacing.

Each of those is a measurement, and each contributes to `row_confidence` —
which flows into Phase C like any other evidence.

### Where it plugs in

This is **Piply's speciality**, not the baseline model's. A trained layout model
will report one `table` region; assembling its rows and cells correctly on a
borderless statement is exactly the specialised work Piply keeps.

### Measured against Phase E

Row and column accuracy are already in the metric list. This phase is the reason
they are there — an outer box in the right place with the rows wrong scores well
on IoU and is still useless.

### CLI

```
piply-opdf detect <pdf> --borderless-debug    dump column and row candidates
```

---

## Phase N — Nested layouts

| Nesting | State |
|---|---|
| Table → Row → Cell | ✅ |
| Panel → anything | ✅ |
| **Cell → Sentence / Paragraph** | ❌ a cell is terminal |
| **List item → Sentence / Paragraph** | ❌ marker and body are separate |
| Key-value → Key / Separator / Value | ✅ |

`Moda.pdf` p1 splits lettered clauses into a 96×35 px marker plus an unrelated
paragraph; a table cell holding a sentence cannot be reviewed as a sentence.

The leaf-level review rule still holds: a person is asked about the smallest
unit, never about both a cell and the sentence inside it.

---

## Phase T — Template & Layout Intelligence

The subsystem name, because it is broader than "template matching": it does
**page-family recognition, layout prediction and geometry verification**.

```
   intelligence/
     FingerprintMatcher     builds and compares fingerprint bundles
     TemplateMatcher        decides which page family a page belongs to
     LayoutPredictor        proposes the expected layout for that family
     GeometryVerifier       checks the expectation against the actual page
```

### FingerprintMatcher — six signals, layered

| # | Signal | Captures | Survives |
|---|---|---|---|
| 1 | Perceptual hash | Overall appearance | Exact repeats |
| 2 | Edge projection | Where rules and columns sit | Different values |
| 3 | Component distribution | How many pieces, what size, where | Scanner differences |
| 4 | Major region geometry | Big blocks and their arrangement | Content changes |
| 5 | Ink density grid | 32 × 32, page normalised | Size, DPI, skew |
| 6 | Layout structure | Detected types and arrangement | Appearance entirely |

```
   Page → pHash → geometry signature → layout signature → fingerprint bundle
```

Cheapest first, so matching can stop early. Signals 1–5 need no detection, so a
template is useful the moment it is uploaded. Stored as a **bundle**, never
merged into one number, so a weak signal can be ignored rather than polluting a
hash. Every bundle carries its `feature_version`.

### TemplateMatcher — hierarchical  🧪 experimental, off by default

```
   New page
      ↓  Exact fingerprint?         pHash distance ~0
      ↓  Near fingerprint?          weighted signals 1-5
      ↓  Structural layout match?   signal 6 only — ignores appearance
      ↓  Generic detection
```

| Score | Meaning | Action |
|---|---|---|
| 95–100% | Strong | Apply, verify, report |
| 90–95% | Likely | Apply, verify, mark for a glance |
| 80–90% | Uncertain | **Ask the user to confirm** |
| < 80% | Unknown | Generic detection; offer "save as new template" |

All thresholds in configuration, and **marked as unmeasured guesses**:

```yaml
template_matching:
  enabled: false            # until false-match rate is measured
  exact_phash_distance: 2
  bands: { strong: 0.95, likely: 0.90, confirm: 0.80 }
  signal_weights:
    phash: 0.15
    edge_projection: 0.25
    component_spread: 0.15
    region_geometry: 0.20
    ink_density: 0.15
    layout_structure: 0.10
```

**Built configurable, shipped switched off.** Enabled only once Phase E can
report a false-match rate. Agreed sequence:

```
   Layout knowledge → human corrections → accumulate examples
                   → template matching → tune against real data
```

The examples arrive from ordinary use; nothing has to be collected specially.

### GeometryVerifier

```
   Known template → Expected layout → Structural reference → Verification
```

Reading the **structural reference**, not the raw original and not the enhanced
image, so rotation does not create false mismatch.

For each expected region: is there ink where ink is expected; does the shape
agree; has it moved further than its `tolerance`; are all `required` regions
present.

| Outcome | Action |
|---|---|
| All required present and in place | Accept, high confidence |
| Moved within tolerance | Accept, snap each to the nearest real ink |
| A required region missing | **Reject the match**, fall back to detection |
| Many small disagreements | Accept, flag the page |

This is what stops a wrong template silently corrupting a document, and it feeds
the false-match metric in Phase E.

---

## Phase U — Review, correction and UI

### Layout type list

| Group | Types |
|---|---|
| Containers | Table, Borderless table, Panel |
| Headings | Title, **Heading**, **Subheading** |
| Text | Paragraph, Sentence, List item, Key-value |
| Table parts | Row, Column, Cell |
| Marks | Signature, Handwriting, Stamp, Logo, Image, Separator |
| Other | Unknown / not detectable |

### Rule 4 — Title, Heading, Subheading (confirmed)

| Type | Definition |
|---|---|
| **Title** | Main document or page-section title. Largest or most prominent, normally **once** per document or section. |
| **Heading** | Major section heading introducing a significant section. |
| **Subheading** | Nested under a heading; introduces a smaller subsection. |

Judged **relatively, never by absolute font size**, in this priority: position
and hierarchy; size relative to surrounding text; weight; whitespace before and
after; alignment; numbering pattern (`1.`, `1.1`, `A.`); repetition across pages.

**When ambiguous, do not force it:** `heading_type = "unknown"`, confidence
below threshold, send to review. Consistent with "decide, don't defer" rather
than an exception to it — the region is still confidently a heading *of some
kind*, with the three levels carried as candidates so review is one click. Only
the **level** is deferred.

A subheading wrongly promoted to a title corrupts the document outline, and an
outline error is invisible in the text.

### UI

**The page is the interface.** Regions drawn, clicked and corrected on the page
itself; nesting as a tree; confidence as colour, not a number. Already moving
that way: toasts, dark mode, keyboard navigation, row grouping, review progress.

---

## Phase A — Users and login (deferred)

`users`, `sessions`, `hashlib.scrypt` from the standard library. A user owns
their PDFs and templates; **all knowledge is shared**.

Ownership *columns* go in now, nullable, so adding login later is not a
migration.

---

## Rules for every step

These govern delivery, not design. They are the reason a finished step stays
finished.

1. **Nothing is "done" without tests.** A step ends when its own tests pass
   *and* the whole suite still passes.
2. **No step breaks an earlier one.** The full suite runs at the end of every
   step, not at the end of the phase.
3. **Docs are updated in the same step**, not afterwards (R4). A step that
   changes behaviour and leaves the docs describing the old behaviour is not
   finished.
4. **One step at a time**, each small enough to review and, if wrong, undo.

---

## Order of work

The sequence, with the reason each step sits where it does:

```
   1. Structural image pipeline      stable images to label against
   2. Gold-labelled dataset          the permanent corpus
   3. Run existing detectors         against the corpus
   4. Measure errors                 per type, per detector
   5. Build confidence               fitted to those measurements
   6. Fix borderless tables          the biggest structural gap
   7. Re-measure                     "87.2% → 91.6%", not "it looks better"
```

| # | Phase | Why here |
|---|---|---|
| 1 | **Q — three images, orientation, working OCR** | Labels must describe the images the system will actually read |
| 2 | **E — gold corpus and metrics** | Permanent. Every later change is scored against it |
| 3 | **E — measure the current detectors** | The baseline number, before anything changes |
| 4 | **B — baseline model + fusion** | Now answerable per type: does the model beat the rules? |
| 5 | **K — knowledge architecture** | Versioned, with the action taxonomy |
| 6 | **C — confidence as an evidence score** | Fitted against the corpus from step 2 |
| 7 | **R — borderless tables** | The biggest structural gap |
| 8 | **E — re-measure** | Proves steps 4-7 helped, and by how much |
| 9 | **N — nested layouts** | Independent |
| 10 | **T — fingerprint + verifier** | Verifier before matcher, deliberately |
| 11 | **T — template matcher** 🧪 | Built off; enabled when false-match rate is known |
| 12 | **U — review UI and redesign** | Once the data shape is settled |
| 13 | **A — users and login** | Deferred |

**Steps 3 and 8 are the same command.** That is the point: every future change
answers *"before 87.2%, after 91.6%"* rather than *"it looks better"*.

CLI commands ship **with** each phase.

---

## Beyond the parser

The thirteen steps above take a scanned page apart. They stop there. The work
below turns that into a product: writing it down, storing it, showing it, and
giving it back as a document. It is sequenced after the parser because every
part of it reads the parser's output — fixing the output once fixes all of them
together.

> **A note on letters.** The phase letters here (Q, B, E, C, R, N, T, U, A) are
> this document's own. The item IDs below — `B1`, `C4`, `E5` — belong to
> [backlog.md](backlog.md), which uses the same letters for different phases.
> Follow the ID to the backlog, not to a heading in this file.

### 1. The manifest — `B1, B2, B6, B7, B8, B9`

Master file → one file per page → one file per layout. Every detected item is
in it, nested as a tree, with levels, review-unit flags, checksums, versions and
original-frame coordinates.

**Proves:** nothing detected is missing from disk; reprocessing one page
rewrites only that page; a manifest reads back into the same tree.

Specification: [manifest.md](manifest.md).

### 2. Trust markers on every value — `B10, B11, B12`

Every item carries a score and the source it came from. Each half of a
key-value carries its own. Values are marked `verified` or `assumed`, and
**only `verified` reaches the knowledge base**.

**Proves:** an assumed value never becomes learned truth, so one unchecked
mistake cannot spread through everything learned afterwards.

This is the delivery mechanism for the
[governing principle](#the-governing-principle), and it depends on
[Phase C](#phase-c--confidence-as-an-evidence-score) — a trust marker is only
worth having once the score behind it means something.

### 3. Persistence — `B5, C4`

Store every unit — titles, graphics, and the children of headers, footers and
key-values — with per-document numbering rather than database keys, so a
reference in a manifest survives a reimport.

**Proves:** what the pipeline detects is what the database holds.

### 4. Page-by-page processing — `C1`

Write and expose each page as it finishes, so review can start on page 1 while
page 24 is still running.

### 5. Library boundary — `E5, E6`

The public API is exported from `piply_opdf/__init__.py` and the app uses only
that. A test processes a document **with `app/` absent**, so the build fails if
the boundary is broken rather than the breakage being found months later.

This sits immediately before the UI work in
[Phase U](#phase-u--review-correction-and-ui), so the new screens are built
against the public API from the first day instead of being retrofitted onto it.

### 6. Reading order and style — `B3, B4`

The order a person would read the page in, and the style hints needed to
rebuild it. Both are prerequisites for output that resembles the original.

### 7. HTML output — `D1, D2, D3, D4`

The reconstructed document. Reads the manifest, nothing else.

### 8. Privacy and audit — `J1, J2, J3`

Who changed what, when, and what was redacted. Required before real documents
with real patient data go through the system at any volume.

### 9. Scanned-page extras — `A2, A3, A4`

Multi-page scan handling beyond the single-page case.

### 10. Learning — `G1, G2, G3, G4`

The corrections feed back. This is last on purpose: a system that learns from
unverified output learns its own mistakes, so it cannot start before item 2.

---

## The flow chart

`docs/images/system_flow.png` is the one-page picture of the system, for
presenting.

```bash
python tools/make_flowchart.py
```

To change it, edit the `DATA` block at the top of `tools/make_flowchart.py` —
stage names, the bullet lines under each, and the status of each stage
(`done` / `part` / `plan`). Nothing else needs touching. Re-run and the PNG is
rebuilt.

**Keep it in step with this plan.** When a phase finishes, change that stage's
status and re-run, so the picture never claims more than the plan does.

---

## What I need from you

| When | What |
|------|------|
| Phase E | 5–10 real scanned documents, hand-labelled, ideally with known problems |
| Phase E | Confirmation of the accuracy targets in [quality.md](quality.md) |
| Phase T | 3–5 copies of the *same* form, to tune matching and measure false matches |
| Phase U | A look at the first screen before I build the rest |

The first row is the gate. Generated pages cannot imitate bleed-through,
staples or real handwriting, and the detector cannot grade itself — so until
those labels exist, precision and recall are unmeasured, not merely low.

---

## Progress

| # | Phase | Status |
|---|-------|--------|
| 1 | Q — three images, orientation, working OCR | ✅ done |
| 2 | E — gold corpus and metrics | 🔴 blocked — harness built, no labels |
| 3 | E — measure the current detectors | ⬜ waiting on 2 |
| 4 | B — baseline model + fusion | ✅ done |
| 5 | K — knowledge architecture | 🔨 layout store built, nothing writes to it |
| 6 | C — confidence as an evidence score | 🔨 built and wired; calibration waits on 2 |
| 7 | R — borderless tables | ⬜ |
| 8 | E — re-measure | ⬜ waiting on 2 |
| 9 | N — nested layouts | ⬜ |
| 10 | T — fingerprint + verifier | ⬜ |
| 11 | T — template matcher 🧪 | ⬜ off until the false-match rate is known |
| 12 | U — review UI and redesign | ⬜ |
| 13 | A — users and login | ⬜ deferred |
| — | [Beyond the parser](#beyond-the-parser) 1–10 | ⬜ |

Step 4 landed before steps 2 and 3, which is out of order. The baseline and
fusion were built and tested on their own behaviour rather than scored against
a corpus, so what exists is *working fusion of unmeasured detectors*. Steps 2
and 3 still have to happen before any accuracy claim is made.

Detection-side items already delivered — panels, recursive detection inside
containers, stamps, and rules 1–3 — are recorded in
[backlog.md](backlog.md) under Phase X.

---

## Honest challenges

### 1. Adopting a baseline model has a real cost

`paddleocr` becomes required, with model weights. Heavy, and against the
"maximum light" rule. Mitigated by an adapter that lets the package run without
it, and by the fact that OCR needs Paddle anyway — but it is a genuine trade,
not a free win.

### 2. One OCR engine runs, not two — *resolved in part*

`paddleocr` 3.6.0 is installed in the `py313_piply_opdf` environment and works;
it is the default engine. The `tesseract` binary is still missing, so the
cross-check in [Phase C](#a-second-ocr-engine-selectively) — read a doubtful
region twice and compare — cannot run yet. One engine is enough to proceed; two
are needed before agreement can be used as evidence.

### 3. Fusion needs a policy for every disagreement

Two detectors will disagree often. The table above covers the common cases; the
long tail needs the evaluation corpus to settle — another reason Phase E is
first.

### 4. Labelling is human time, and it is the gate

Phase E is mostly labelling. It cannot be automated: using the detector to grade
itself proves nothing. A few hundred regions across 5–10 real scans is the
realistic minimum.

### 5. No knowledge base has a backup

They are the compounding assets and cannot be regenerated. The application
database has already lost data once.

---

## What changed in this revision

| Change | Where |
|---|---|
| **Evaluation corpus moved to the first phase** | Phase E |
| False template match named a critical safety metric | Phase E |
| Trained baseline detector adopted, Piply layered on top | Phase B |
| Fusion rules, with disagreement as a review signal | Phase B |
| Baseline is an adapter — the package still runs without it | Phase B |
| Three images: original / structural_reference / working | [Three images](#three-images) |
| Verification reads the structural reference | Phase T — GeometryVerifier |
| Versioning required on knowledge records and fingerprints | Phase K |
| Human actions recorded as CONFIRMED / CORRECTED / ADDED / DELETED / REJECTED | Phase K |
| Confidence moved after baseline + knowledge | Phase C |
| Second OCR engine only where it earns its cost | Phase C |
| Subsystem renamed **Template & Layout Intelligence**, four named parts | Phase T |
| Corrected: neither OCR engine is currently installed | Challenge 2 |

### Fifth revision

| Change | Where |
|---|---|
| **Never silently trust a classification** as a governing principle | [Governing principle](#the-governing-principle) |
| Every component carries evidence, source, knowledge match, review status | [Governing principle](#the-governing-principle) |
| A template match can never override geometry verification | [Governing principle](#the-governing-principle) |
| Confidence is an **evidence score**, calibrated against labelled data | Phase C |
| Historical reliability is one input, not the whole score | Phase C |
| Layout reads the **structural** image; OCR reads the working one | [Three images](#three-images) |
| `working` derives from `structural`, so OCR inherits deskew | [Three images](#three-images) |
| **Borderless tables rebuilt around continuation analysis** | Phase R |
| No single column may be the mandatory row anchor | Phase R |
| Structural pipeline before labelling; measure, change, re-measure | [Order of work](#order-of-work) |
