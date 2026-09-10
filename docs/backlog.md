# Backlog

**The single tracking document.** Every issue, task and requirement raised
lives here with a status. New items are appended to their phase, never dropped.

Ideas not yet approved live in [suggestions.md](suggestions.md). Once you
approve one it moves here and gets an ID.

For the scanned-PDF goal specifically — the stages, where each stands, and the
challenges ranked — see [scanned-documents.md](scanned-documents.md).

*Last updated: 2026-09-10 · 438 tests passing, 0 failing.*

| Mark | Meaning |
|------|---------|
| ✅ | Done, verified by tests |
| 🔄 | Partially landed |
| ⬜ | Not started |
| 🔁 | Standing policy |

---

## Standing requirements

| ID | Requirement |
|----|-------------|
| R1 | **Mathematics over heavy libraries.** OpenCV, NumPy, PyMuPDF. Anything heavier justifies itself against an analytic alternative first. |
| R2 | **Package is the product; the UI must expose all of it.** End users are data-entry operators — every low-confidence layout, component, word and character must be verifiable and correctable in the UI. No capability may be package-only. |
| R3 | **Keep the library light.** Remove dead code and dependencies continuously. |
| R4 | **Update and clean all docs on every change.** |
| R5 | **Scale-free thresholds.** Ratios, or points converted via DPI — never fixed pixels. Must hold A5→A3, 150→600 DPI. |
| R6 | **Offline.** No network at inference time. |
| R7 | **Nothing is lost.** Unclassifiable content is captured as `UNKNOWN`, never discarded. |
| R8 | **Standard practices.** OOP, SOLID, strategy/factory/registry, type hints, tests. |
| R9 | **No partial functionality.** Complete and verified, or marked ❌. Never ✅-with-caveats. |
| R10 | **No fabrication.** Text only from text layer, OCR, knowledge base or human. Unreadable stays empty. |
| R11 | **Tests strong enough for every component type.** Accuracy measured, not asserted. |
| R12 | **Where two types look alike, we set the rule.** Where two types share every measurable property, a rule states where the line sits. |
| R13 | **Decide, don't defer.** Torn between candidates → emit the most likely with low confidence and record alternatives, so the operator answers a closed question. `UNKNOWN` only for genuine non-recognition. |
| R14 | **Human correction is the source of truth.** Any operator decision — text, type, or structure — enters the knowledge base and resolves the same case automatically next time. |
| R15 | **Everything is a unit, in levels.** Page → layout → component → … → review unit. Order is decided level by level. The last level is always what a person checks in the UI. |
| R16 | **Every detected item carries a confidence score.** No exceptions — layouts, components, words, characters. Low scores are what the operator screen sorts by. |
| R17 | **No correction means accepted — for the document only.** If nobody changes a value it stands as that document's answer. But **only human-reviewed content ever enters the knowledge base** as truth. Assumed values are never learned from, so one unchecked mistake cannot spread. |
| R18 | **The library never depends on the UI.** `piply_opdf` must be usable on its own in any other project. The app depends on the library, never the reverse. |

---

## Summary

| Phase | Theme | Done | Total | Priority |
|-------|-------|------|-------|----------|
| F | Complete detection (`PANEL`, `STAMP`, rules) | 6 | 12 | 🔴 blocking |
| H | Quality and test strength | 0 | 6 | 🔴 blocking |
| B | Complete the record (manifest) | 0 | 12 | 🔴 blocking |
| A | Foundation for scanned input | 1 | 4 | 🟠 |
| C | Operator workbench (UI) | 0 | 19 | 🟠 |
| D | HTML reconstruction | 0 | 4 | 🟠 |
| I | Template intelligence | 0 | 24 | 🟠 |
| J | Compliance and provenance | 0 | 3 | 🟠 |
| E | Package shape and weight | 0 | 6 | 🟢 anytime |
| G | Learning | 0 | 4 | 🔵 later |
| X | Delivered | 12 | 12 | ✅ |
| | **Outstanding** | **7** | **74** | |

**Recommended order: F → H → B → C → D → I → J.** E runs at any point.

F first because the component vocabulary must be final before ground truth is
labelled — labelling before `PANEL` and `STAMP` exist means relabelling.
H next because the manifest should be filled from detection that is measured.
B makes the record complete, C makes it correctable, D consumes it.

I and J come after C deliberately: template intelligence learns from confirmed
operator corrections, and PII classification is most reliable once field names
are known. Both are far cheaper once the workbench exists.

---

## Phase F — Complete detection 🔴

The last structural gap. Until `PANEL` lands, a boxed region is misread as a
table and its contents are lost, so no manifest built on top can be correct.

| ID | Item | Status |
|----|------|--------|
| F1 | `PANEL` — boxed / framed region detector | ✅ |
| F2 | Recursive detection inside containers | ✅ |
| F3 | `STAMP` component type | ✅ |
| F4 | Rule 1 — table requires ≥2 cells | ✅ |
| F5 | Rule 2 — stamp vs logo by colour count | ✅ |
| F6 | Rule 3 — signature vs handwriting by word-group count | ✅ |
| F7 | `borderless_table` strategy conversion | ⬜ |
| F8 | Table segmentation behind the Segmenter contract | ⬜ |
| F9 | Merged cells (rowspan / colspan) | ⬜ |
| F10 | Table header-row detection | ⬜ |
| F11 | Borderless table should build its own cells | ⬜ |
| F12 | Separate a 3-column key-value block from a real table | ⬜ |
| F13 | Rule 0 — ask "is it text?" before asking about colour | ✅ |
| F14 | `SEPARATOR` type for ruled lines | ✅ |
| F15 | Residual sweep reports missed text as text, not `UNKNOWN` | ✅ |
| F16 | Logo on a coloured background reads as `IMAGE` | ⬜ |
| F17 | A mid-page row is sometimes typed `TITLE` | ⬜ |
| F18 | Text in a dashed box is not recognised as text | ⬜ |
| F19 | A page-sized region must not be typed as a mark | ✅ |
| F20 | Rotated text is not recognised as text | ⬜ |
| F21 | Large display text is not recognised as text | ⬜ |
| F22 | Numbered list items read as key-value pairs | ⬜ |
| F23 | Interior detection is weak on skewed scans | ⬜ |
| F24 | A ruled grid that is really a key-value list | ✅ |
| F25 | Multi-line numbered/lettered list items are truncated | ⬜ |
| F26 | Key above value (vertical key-value) | ⬜ |
| F27 | A negligible skew angle must not be corrected | ✅ |

**F13–F15 came out of reading every page of all 16 sample documents against
what the system produced.** They were not visible in any count or coverage
figure — only in the pictures. See [audit.md](audit.md).

**F13** ✅ The colour rules ran before anything asked whether a region was
writing, so blue hyperlinks came back `STAMP`, headings on a yellow band came
back `LOGO`, and a whole scanned bank statement came back `HANDWRITING`. Text is
now recognised first, using baseline alignment as well as stroke width — stroke
width alone cannot survive a scan. Rule 0 in
[components.md](components.md#rule-0--is-it-text-at-all).

**F14** ✅ A 2386×27 divider satisfied every signature condition, so documents
reported signatures they did not contain. Ruled lines now have a name.

**F15** ✅ The residual sweep rewrote any text verdict to `UNKNOWN`, which put
every value on a scanned bank statement into the "nobody knows what this is"
bin. Missed text is now reported as a `SENTENCE` needing OCR.

**F16** ⬜ The LIC logo on `PolicyStatus_885472060_.pdf` reads as `IMAGE`: it is
dense and colour-rich, so the photograph rule claims it before Rule 2. Both are
graphics, so nothing is lost — but the type is wrong.

**F17** ⬜ On `PolicyStatus_885472060_.pdf` a row in the middle of the page is
typed `TITLE`. The title detector's prominence test is not anchored to position.

**F18** ⬜ On `OD330106520353075100.pdf` the invoice number sits in a dashed
box; the dashes break the baseline measurement and the region is not recognised
as text.

**F19** ✅ A signature, a stamp and a logo are marks — small things. Nothing
enforced it, so a whole revenue chart came back `SIGNATURE` and a whole
transaction table came back `HANDWRITING`. Measured across all 198 marks on the
corpus: genuine ones run 0.5–2.3% of a page, the wrong ones 6–45%. Capped at 5%.

**F20** ⬜ Baseline alignment assumes horizontal text, so rotated text fails
Rule 0. The whole vertical left margin of `PublicWaterMassMailing.pdf` p4 and
the axis labels on `sample-img1.png` are mis-typed. Needs the text angle
estimated per region before the baseline is measured.

**F21** ⬜ Large display text fails Rule 0 from both directions. The HDFC
tagline on `sample5.pdf` measures density 138–215 (under the 400 floor, because
big glyphs are fewer per megapixel) and stroke variation 0.475–0.501 (*above*
handwriting's 0.43). Compounded by the residual sweep splitting the line into
one region per word, leaving each too small to measure a baseline from. The
density floor is not scale-free with respect to font size — that is the real
defect.

**F22** ⬜ `Moda.pdf` p27: in a 25-item county list, `1.` + `Benton` reads as
key + separator + value, so most items come back `KEY_VALUE` and a few come
back `LIST_ITEM` — inconsistently, inside one list. A leading integer followed
by a full stop, repeating down a column, is a list marker, not a key.

**F24** ✅ `ChallanReceipt.pdf` reported a six-column table for what is one
label and one value per row: label / spacer / colon / value / spacer / spacer.
Decided by counting **glyphs** per column, not ink — the drawn rules cross every
column, so a spacer still measures 0.02–0.08 of the table's ink and never looks
empty. A column carrying under half a glyph per row is a spacer. Measured: the
challan's spacers hold 0, 0, 0 and 4 glyphs over 18 rows, while the sparsest
real column on the `DOC-20250901-WA0021.pdf` packing list holds 31 over 25.

**F25** ⬜ `Moda.pdf` p1: lettered clauses `A.`, `B.`, `C.` with multi-line
bodies. The marker is detected as a `LIST_ITEM` of its own (96×35 px — just the
letter) and the body as a separate `PARAGRAPH`; through the app path the pair
came back as a `KEY_VALUE` holding only the first line. A list item should span
its marker **and** its whole body, to the next marker.

**F26** ⬜ Key above, value below — a column heading with its value beneath it,
rather than `key : value` on one line. The key-value detector only ever looks
along a line, so this shape is invisible to it. Needs a vertical pairing pass:
a short label with a value directly below, sharing a left edge and column width,
with no other content between.

**F27** ✅ Deskew was correcting 0.20° on an already-straight page, which took
`sample.pdf` from one table of 171 cells to none. Minimum correction raised from
0.15° to 0.5°.

**F23** ⬜ `sample10.pdf` p21 (lowest coverage on the corpus, 0.9477): the
panel is found but most printed text inside it is never claimed. The page is
skewed and low contrast.

**F1 — `PANEL`** ✅
Closed frames found from horizontal and vertical rules, kept when they
approximate a four-sided axis-aligned rectangle of reasonable size. Runs
**before** table detection. 35 tests.
*Raised: "content are written inside a square or rounded box… which is actually
not a table."*

**F2 — Recursive containment** ✅
Container children come from running the **existing detector suite scoped to
the interior**, not a bespoke parser. `PageContext.sub_context()` hands a
detector a cropped view it cannot tell from a page — including a text layer
filtered and moved into the crop's own coordinates — so no detector needed
changing.

Guards: `PANEL` is not searched inside a panel (it would find its own frame
forever); `HEADER`, `FOOTER` and `TITLE` are excluded because they mean
position on a *page*; residual regions that restate content already recognised
are dropped. 32 tests.
*Raised: "later that component can be splitted & parse into title, header,
paragraph, sentence, list-items, key-value, signature, stamp, logo etc.. or
non-detectable component."*

**F3 — `STAMP`** ✅
Added to the vocabulary, the classifier and the test corpus. Recognised 12/12
on generated seals.

**F4 — Rule 1: cell count** ✅
> Table requires ≥2 cells. A single-cell frame is a `PANEL`.

Cells are counted from internal rules that span most of the interior. Two
guards were needed, both found by testing:

- **Thickness cap.** A divider must be thin. Without this, dense content — a
  photograph, a block of colour — spans the full width on every row and reads
  as a divider, so a framed picture counted as a table.
- **Classifier check.** On a *scanned* photo, render artefacts still produced
  thin streaks that passed the thickness cap. Asking the classifier what the
  interior actually is settles it: a confident picture means one cell,
  whatever the geometry suggests.

*Raised: "one cell table we can always treat as boxed layout, we can consider
table only if more than 1 cells."*

**F5 — Rule 2: colour count** ✅
> 1 dominant chroma cluster → `STAMP`. 2+ → `LOGO`.

Two guards were needed, both found by testing:

- **An ink floor.** A stamp or logo is a *dense mark*. Without a floor, sparse
  coloured line-work — a table ruled in blue ink — satisfied "one colour" and
  came back as a logo.
- **A confidence floor on rejection.** The table gate discards a region when the
  classifier calls it a picture, but it was doing so on a *near-tie*. A real
  50-cell table was dropped on a 0.55 verdict. Only a confident verdict
  (≥0.70) may throw a table away — discarding on a maybe is destructive.

Hue is binned in 15° steps over pixels above a saturation floor, and a cluster
must hold 12% of the coloured pixels to count — without that floor,
anti-aliasing fringes make every logo look polychrome. Measured cleanly:
stamps 1 cluster, logos 2.

For one colour, a seal is told from a solid logo by fragmentation: a stamp is
applied by hand so its edges break up (density ~213) while a printed logo stays
solid (~25).

Quantise hue over saturated pixels, count area-weighted clusters. Tie-break for
a monochrome logo: stamps overlap existing content and have broken edges from
uneven pressure; logos occupy reserved space with clean edges. **Failing both,
emit `LOGO` with low confidence and record `STAMP` as an alternative** (R13) —
the operator resolves it in one click and that becomes truth.
*Raised: "stamp always in single color & maximum logo contains multicolor or
differentiate with the help of color expansions."*

**F6 — Rule 3: word-group count** ✅
> 1–2 word-groups → `SIGNATURE`. 3+ → `HANDWRITING`. Uncertain → `HANDWRITING`.

Groups are runs of ink separated by more than a quarter of the region's height,
so the rule holds at any size. Component density backs the count up, because
words written close together merge into one group — a signature is a few long
strokes (~18), handwriting many short ones (~704). Without that backup, tightly
spaced handwriting would read as a signature.

A word-group is a run of connected ink separated by more than the intra-word
gap — the same measurement segmentation already uses. Fallback direction is
deliberate: a signature mislabelled as handwriting gets OCR'd and reviewed
(recoverable); handwriting mislabelled as a signature is never read (silent
loss).
*Raised: "Signature can be just 1 or 2 words but cursive sentence contains
multi words… fallback treat that as handwritting i am fine with that."*

**F7 — `borderless_table`** ⬜
Last detector on the old API, text-layer only, returns nothing on scans. CV
strategy should infer columns from vertical alignment of detected text lines.

**F8 — Table segmentation behind the contract** ⬜
Table → row/column → cell still sits in `layout/`, driven directly by
`Document.process_layout()`. Works, but is the one unit path that cannot be
swapped, tested or extended like the others.

**F9 — Merged cells** ⬜
Required for faithful HTML tables.

**F11 — Borderless tables build no cells** ⬜
`BorderlessTableDetector.detect_tables()` returns rows and columns but never
cells. They are built ~200 lines later in `document.py`, as rows × columns,
while crops are being written.

Found by testing on real documents: a filter checking "does this table have
cells" removed every borderless table on every file, because at detection time
none of them do. Detection should produce a complete component, not one the
pipeline finishes off later. Folds into F7.

**F12 — Three-column key-value blocks** ⬜
A borderless table now needs 3+ columns, which separates real tables from
two-column form blocks. But a glossary laid out in three columns
(`alc = Account`, `adj = Adjustment`, …) is still claimed as a table, and its
key-values drop from 39 to 2 on `sample9.pdf`.

A rule in the same spirit as the others would settle it: **if most rows contain
a separator, it is a key-value block, not a table.** Needs deciding, not
guessing.

**F10 — Header-row detection** ⬜
Identify *which* row is the header — turns a table from a grid of strings into
named columns. Required for meaningful `<th>` in HTML and for structured field
export (I4). Signals: typographic emphasis, background fill, position, and the
type contrast between a header row (text) and body rows (often numeric).

---

## Phase H — Quality and test strength 🔴

The suite proves **consistency**; it measures **no accuracy**. Until this
lands, any claim about accuracy on real documents is unsupported.
See [quality.md](quality.md).

| ID | Item | Status |
|----|------|--------|
| H1 | Ground-truth corpus (synthetic + real + regression) | 🔄 |
| H2 | Precision/recall harness per component type | 🔄 |
| H8 | Configurable OCR engine, PaddleOCR primary | ✅ |
| H3 | `ink_accounted` coverage invariant | ✅ |
| H4 | CI gates on every metric | 🔄 |
| H5 | Per-type suites for untested detectors | ⬜ |
| H6 | Bad-scan suite | ⬜ |
| H7 | Tests for the OCR layer | ✅ |

**H1** 🔄 — `tests/corpus/{synthetic,real,regression}/`. Synthetic gives volume
and exact labels; real gives bleed-through, staples, uneven lighting, genuine
handwriting; regression captures every document that has exposed a bug.

*Partly there:* 16 real documents (86 pages — 10 digital, 4 scanned, 2 images)
now run through `tools/run_corpus.py`. All 16 process without error. Still
missing: hand-labelled ground truth, so this measures *behaviour*, not accuracy.

**H2** 🔄 — IoU-based matching of detected against labelled components,
reported per type. Turns "detection is good" into a number that moves.

*The harness is built* — `piply_opdf/quality/accuracy.py`, with `score_page()`,
per-type precision/recall/F1, and a JSON label format. It is tested against
synthetic labels (11 cases). **It has never been run against real labels,
because none exist yet.** That is H1's remaining half.

**H3** ✅ — `piply_opdf/quality/coverage.py`. Measures the share of page ink
that falls inside some detected component, and reports the largest unclaimed
regions so a loss can be found rather than merely counted. Run it with
`tools/check_coverage.py`. Asserted in `tests/unit/test_quality.py` (8 cases).

Result on the 16 real documents, 88 pages:

| | |
|---|---|
| mean coverage | **0.9945** |
| worst page | **0.9477** (sample10.pdf page 21) |
| pages at or above the 0.995 target | 65 / 88 |
| pages below target | **23 / 88** |

So the target is met on average but not per page. The failures cluster — most
of the 23 are `sample10.pdf` and `Sbizhub_C2219080509040.pdf`. See
[quality.md](quality.md#where-ink-is-being-lost) for what is being lost.

**H4** 🔄 — Every metric asserted, so improving paragraphs while degrading
tables fails the build. Coverage is measurable now, so it can be gated; accuracy
cannot be gated until labels exist. Gating coverage today would pin the build to
0.9477, which locks in the current losses rather than fixing them — so the gate
waits until the clustered failures above are dealt with.

**H5** — `borderless_table`, table row/column/cell, `PANEL`, `STAMP`,
orientation. Each needs what header/footer already has: sizes, DPIs,
digital/scanned, presence and absence, geometry, exclusions, ordinals.

**H6** — Blur, noise, low contrast, JPEG artefacts, bleed-through, torn edges,
skew plus noise. Checks the output gets less confident rather than wrong — and that quality gating engages.

**H7** ✅ Replaced by `piply_opdf/ocr/` — a registry, a contract and two
engines, with 15 tests. Most need no engine installed, so the suite stays fast
and still passes on a machine with no OCR.

Three defects were found and fixed while writing it:

- **`det=False` was dead code.** PaddleOCR 3.x rejects it with `TypeError`, so
  every call silently fell through to full detection. Recognition-only via
  `TextRecognition` was then measured against full detection on eight realistic
  crops: **both scored 7/8**, failing on the same case. Equal accuracy, so the
  single simpler path stays.
- **The edge penalty fired on everything.** It tested PaddleOCR's detected boxes
  against the padding, but the detection model adds its own 11-15 px margin, so
  every crop looked clipped and every confidence was halved. Now measured on the
  crop itself: ink reaching its own border. Verified — a crop sliced through a
  glyph reads `43438` as `13438` at confidence 1.0, and is marked down to 0.50.
- **Tesseract returned a fabricated 0.85** whenever any text came back. It now
  reports Tesseract's own per-word confidence.

---

## Phase B — Complete the record 🔴

The manifest is the contract every consumer reads. It currently discards
detected content. Design: [manifest.md](manifest.md).

| ID | Item | Status |
|----|------|--------|
| B1 | Manifest covers every detected component | ⬜ |
| B2 | Nested unit tree | ⬜ |
| B3 | Page column detection → reading order | ⬜ |
| B4 | Style hints (size, emphasis, alignment) | ⬜ |
| B5 | Persist every unit to the database | ⬜ |
| B6 | Master + per-layout manifest split | ⬜ |
| B7 | Integrity and versioning | ⬜ |
| B8 | Coordinates in the original frame | ⬜ |
| B9 | Level and review-unit flags | ⬜ |
| B10 | Confidence per part, not per component | ⬜ |
| B11 | Confidence on every detected item | ⬜ |
| B12 | Only human-reviewed content enters the knowledge base | ⬜ |

**B1** — `generate_master_manifest()` writes tables, borderless tables,
headers, footers, key-values, paragraphs, sentences — and drops `titles`,
`list_items` and all `graphics` including `UNKNOWN`. The residual sweep does
its job during detection and the manifest undoes it, violating R7.
*Raised: "Manifest file should be bible of any pdf or image… including all
component & content of pdf, even detectable or non-detectable."*

**B5** — `app/services.py` never stores TITLE, graphics, or the children of
header/footer/title/key-value. Units exist in memory and are lost at the
database boundary — this is why they cannot appear in review.

**B6 — Manifest per layout** ⬜
Master as entry point → `pages/page_NNN.json` per page → `layouts/<id>.json`
for **every layout**, not only containers. Each table, paragraph, panel,
header, key-value and graphic gets its own file.

So a 24-page document never loads as one blob, and reprocessing one page
rewrites only that page's files. It also means a single layout can be handed to
another system on its own.
*Raised: "Even first level every layout can have their own manifest."*

**B8** — `bbox_source` alongside `bbox`, so overlays draw on the untouched scan.

**B9 — Levels** ⬜
Each unit records `level` (0 = page, 1 = layout, 2+ = component) and
`is_review_unit` (true only on the last level). Reading order is worked out
level by level: inside any unit, children go top to bottom then left to right.
This tells the UI exactly what to show an operator, and tells the HTML writer
what order to write things in.
*Raised: "first treat a full page as one unit then every layout as a separate
unit then inside layout every component would be a micro level unit… last level
Unit should reviewable unit by end user via UI."*

**B10 — Confidence per part** ⬜
A key-value where the key came from a solid knowledge-base match but the value
came from a shaky OCR read currently gets one blended score. Each part should
carry its own confidence, and the parent should show the weakest.

Why it matters: on forms the keys repeat and the values do not. Sending an
operator to the value alone, instead of the whole pair, roughly halves the
checking work. Feeds C10.

**B11 — Confidence on everything** ⬜
Every detected item carries a score — layout, component, word, character — and
records where the score came from (detector, OCR, knowledge match, or a
person). No item may be stored without one, because the operator screen sorts
the whole queue by it.

Also records whether a person actually looked: `verified` when someone
confirmed or corrected it, `assumed` when the system's answer was accepted by
default (R17).
*Raised: "every detected item should have their confidence score… if user is
not correcting or updating any detection or value then by default system
assumption can be consider as truth."*

**B12 — Guard the knowledge base** ⬜
Every value is marked `verified` (a person confirmed or corrected it) or
`assumed` (accepted by default because nobody looked). **Only `verified`
values are written to the knowledge base.**

Why this matters: knowledge is stored by image hash, and a stored value fills
itself in next time *and skips review*. Without this guard one unchecked OCR
mistake would quietly spread into every future document, looking confident the
whole way.

The document still exports the same either way — this only controls what the
system is willing to learn.
*Approved suggestion S1.*

---

## Phase A — Foundation for scanned input 🟠

| ID | Item | Status |
|----|------|--------|
| A1 | Page-level deskew | ✅ |
| A2 | Orientation detection (90/180/270) | ⬜ |
| A3 | Per-page conditional enhancement | ⬜ |
| A4 | Quality gate for unusable pages | ⬜ |

**A1 — Deskew** ✅
Projection-profile sharpness maximisation, coarse-to-fine on a downscaled copy.
0.00° error across ±8°, 0.00° residual, ~40 ms/page, detection identical at
every angle. Applied only to pages without a text layer. Page frame preserved.
*Raised: "there is chance of content skew".* 31 tests.

**A2 — Orientation** ⬜ Skew correction assumes a roughly upright page; a
sideways scan defeats it. Ink-mask aspect ratio plus horizontal/vertical
projection energy.

**A3 — Per-page enhancement** ⬜ Currently a whole-document pre-pass, so one
poor page causes all 24 to be enhanced.
*Raised: "if document is scanned & enhancement required then only do the
enhancement".*

**A4 — Quality gate** ⬜ Flag for rescan rather than emit confident nonsense.

---

## Phase C — Operator workbench 🟠

End users are **data-entry operators**. Every low-confidence layout, component,
word and character must be checkable and correctable here (R2). No capability
may stay package-only.

**A full redesign is approved.** The current screens grew around the old
component model and will not fit levels (R15), type correction (C9), region
correction (C11) or character correction (C12). Rebuilding around the operator
is cheaper than bending what exists.

The UI is a **client of the library**, never part of it (R18) — everything it
does goes through the library's public API (E5), so the same intelligence can
drive a different application later.

Depends on B5 — until units reach the database they cannot be shown.

| ID | Item | Status |
|----|------|--------|
| C1 | Page-by-page incremental processing | ⬜ |
| C2 | Every smallest unit in OCR Review | ⬜ |
| C3 | Surface the residual / `UNKNOWN` bucket | ⬜ |
| C4 | Component ordinals instead of DB keys | ⬜ |
| C5 | Administrator nav group | ⬜ |
| C6 | Pin nav to a fixed position | ⬜ |
| C7 | Remove OCR Review panel from dashboard | ⬜ |
| C8 | Knowledge Base page enhancements | ⬜ |
| C9 | Correct a component's **type**, not just its text | ⬜ |
| C10 | Prioritised low-confidence work queue | ⬜ |
| C11 | Layout review — verify regions on the page image | ⬜ |
| C12 | Character-level correction UI | ⬜ |
| C13 | Measure how much work operators do | ⬜ |
| C14 | Rebuild the UI around the operator | ⬜ |
| C15 | Keyboard-first operation | ⬜ |
| C16 | Spot-check instead of checking everything | ⬜ |
| C17 | Undo and correction history | ⬜ |
| C18 | Watch folder / batch processing | ⬜ |
| C19 | Per-user statistics panel | ⬜ |

**C1** *Raised: "we can process page by page instead of whole pdf at once…
Long processing time blocks user."*
**C2** *Raised: "only key-value images are coming. Every smallest unit put in
ocr review page."*
**C3** *Raised: "Non-detected components are not visible anywhere."*
**C4** UI shows the database primary key, so the first column reads `COLUMN 2`.
The package already computes `col_index`; `services.py` discards it.
**C5/C6** Administrator submenu; nav pinned to a fixed position.
**C7** `/review` is the dedicated page.
**C8** Sort by sample count, filter by `component_type` and `source`.

**C9 — Type correction** ⬜
Where a component carries `candidates` (R13), present them as one-click
choices — *logo or stamp?* — rather than a free-text field. Where it is
`UNKNOWN`, offer the full vocabulary. The choice enters the knowledge base
(R14) so the same mark resolves automatically next time.
*Raised: "if confusing between choosing anyone b/t two option then consider any
one & from UI user will decide what that is actually."*

**C10 — Prioritised queue** ⬜
Order review by expected value, not document order: lowest confidence first,
weighted by how often that image recurs across the corpus. Verifying one
frequently-repeated header is worth more than a hundred one-off cells.

**C11 — Layout review** ⬜
Verify and correct *regions* on the page image — merge two fragments, split one
region, adjust a boundary, delete a false positive. Today only text is
correctable, so a detection error has no path to being fixed by an operator.
Closes the loop for R11: operator corrections become ground-truth labels for
phase H.

**C12 — Character-level correction** ⬜
UI half of G4: when a word's confidence is low, show per-character confidence
and let the operator fix only the weak characters.
*Raised: "if confidence score is 100% then okay but if it is less, then we can
find confidence character by character wherever confidence will be less human
may enter actual value."*

**C13 — Measure operator work** ⬜
Record units checked per hour, how often each component type gets corrected,
and how much the knowledge base saves over time.

Without this there is no way to tell whether template matching (I2) is worth
what it costs, or which detector creates the most rework. That is exactly the
number that should decide what gets fixed next.

**C14 — Rebuild the UI** ⬜
Redesign around one job: an operator working through low-confidence items as
fast as possible.

- Navigate by level (R15) — page, then layout, then component, down to the
  review unit
- Work queue sorted by confidence, not document order (C10)
- The page image beside the item being checked, always
- Correct text, type (C9), region (C11) and characters (C12) from one screen
- Show clearly what a person has checked and what was accepted by default (R17)

*Raised: "I am okay if you completely redesign whole UI to meet my product
expectations."*

**C15 — Keyboard-first** ⬜
`Enter` accepts and moves on, `Tab`/arrows move between items, typing replaces
a value, number keys pick a type when choices are offered. A normal pass needs
no mouse. Operators work fast with a keyboard and slowly with a mouse — if
every check needs a click, the screen becomes the bottleneck, not the OCR.
*Approved suggestion S2.*

**C16 — Spot-check** ⬜
Show a sample of high-confidence items. If the operator confirms ~20 in a row
with no corrections, offer to accept the rest of that group. One correction
sends the whole group back to the full queue. Needs B10 and C10 first.
*Approved suggestion S3.*

**C17 — Undo and history** ⬜
Keep every correction as a row instead of overwriting — who, when, old value,
new value — and allow undo. Also supplies the data for C13 almost free.
*Approved suggestion S4.*

**C18 — Watch folder / batch** ⬜
A folder that is processed automatically, or a `process these 200 files`
command. For real volume this matters more than any screen feature.
*Approved suggestion S5.*

**C19 — User statistics** ⬜
A section per user showing their own work: how many low-confidence items they
reviewed, how many high-confidence values they corrected (the system was wrong
and confident — the most valuable signal there is), items per session, and
accuracy trend over time.

The high-confidence correction count is worth watching closely: it is the
number that tells you a detector or the OCR is confidently wrong, which is
exactly what C13 needs to decide what gets fixed next.
*Raised: "put a user section with statistics how many low confidence content
current user reviewed. or high confidence corrections."*

---

## Phase D — HTML reconstruction 🟠

| ID | Item | Status |
|----|------|--------|
| D1 | HTML writer | ⬜ |
| D2 | Fidelity pass | ⬜ |
| D3 | Round-trip verification | ⬜ |
| D4 | Export tables to Excel | ⬜ |

**Decided: semantic flow, searchable.** Not pixel-faithful absolute
positioning. The output is a real document — reflows, accessible, indexable,
selectable text — rather than a picture of one.

**D1** Manifest → semantic HTML: `<h*>` from titles, `<table>`/`<th>` from
grids, `<dl>` from key-values, `<ul>` from lists, `<p>` from paragraphs,
`<img>` for graphics and unknown regions, `<figure>`/`<section>` for panels.
Requires reading order (B3) and header rows (F10).
**D2** Apply B4 style hints — relative size, emphasis, alignment. Enough to
preserve the document's visual hierarchy without absolute positioning.
**D3** Compare reconstruction against source — component counts, text coverage,
ordering — as a measurable signal rather than a visual check.

**D4 — Excel export** ⬜
Tables already carry rows and columns; writing `.xlsx` alongside JSON and CSV
is small, and for lab reports and invoices it is usually the format people
actually want. Optional extra dependency, not core (R1).
*Approved suggestion S6.*

---

## Phase I — Template intelligence 🟠

Documents arrive in families. Once one lab report from a given provider is
processed, the next has an identical layout. Today only *cell values* are
reused, by hash. Reusing the **entire layout** is a much larger win.

| ID | Item | Status |
|----|------|--------|
| I1 | Page structure fingerprint | ⬜ |
| I2 | Template match → skip detection | ⬜ |
| I3 | Named field mapping | ⬜ |
| I4 | Structured field export | ⬜ |
| I5 | Users, roles and login | ⬜ |
| I6 | Templates as named, reviewable layouts | ⬜ |
| I7 | Correct a layout type by drawing on the page | ⬜ |
| I8 | Layout knowledge base — its own store, reusable by other applications | ⬜ |
| I9 | Move the CLI out of the library package | ⬜ |
| I10 | Nested layouts: cell → sentence, list item → paragraph | ⬜ |
| I11 | `HEADING` and `SUBHEADING` types — Rule 4 confirmed | 🔄 |
| I12 | Full UI redesign around page-level layout review | ⬜ |
| I13 | Six-signal template fingerprint bundle | ⬜ |
| I14 | Hierarchical template matching with configurable bands | ⬜ 🧪 |
| I15 | Geometry verification of an applied template | ⬜ |
| I16 | Three-image pipeline, wired into `document.py` | ✅ |
| I17 | Page orientation detection | 🔄 |
| I18 | Trained baseline layout detector + fusion with Piply's rules | ✅ |
| I19 | Versioning on knowledge records and fingerprints | ⬜ |
| I20 | Human actions recorded by kind, not agreed/disagreed | ⬜ |
| I21 | Third image: structural reference (orientation + deskew only) | ✅ |
| I22 | Confidence as a calibrated evidence score | ⬜ |
| I23 | Never silently trust: evidence, source and review status on every component | ⬜ |
| I24 | Borderless tables rebuilt around continuation analysis | ⬜ |

**I5–I7** come from the template-learning request. Planned in detail in
[plan-templates.md](plan-templates.md) — **plan only, nothing built**.

**I5** ⬜ There is no authentication of any kind today. Needed first because
every other item records who did the work, and retrofitting that is painful.

**I6** ⬜ A named layout family, reviewed page by page, kept as a reference
rather than consumed once. Per *page*, not per document: page 1 of a statement
is not page 2.

**I7** ⬜ Today a person can correct the *text* of a component but not its
*type*. Drawing a box and saying "this is a table, not a paragraph" is what
creates the training data everything else in Phase I depends on.

**I8** ⬜ The centre of the template plan, and separate from the text knowledge
base because it answers a different question: *what kind of thing is this?*
rather than *what does it say?*. Stores appearance **and position and
neighbours** — a logo is a colourful blob *in a corner*, a heading is large text
*with body text below it*. Its own database file so other applications can use
it, with export and import. Detection stays primary; where the store disagrees
with the detector, that is a signal to ask a person.

**I9** ⬜ `piply_opdf/cli.py` makes the library depend on `typer` and `rich` for
code no library user needs. Moving it to its own package keeps the library light
and matches the separation already applied to the web application.

**I10** ⬜ A cell is terminal today, so a sentence inside a table cannot be
reviewed as a sentence. A multi-line list item is split into a marker component
and a separate paragraph. Both should nest.

**I11** 🔄 `HEADING` and `SUBHEADING` are now in the vocabulary, and the
baseline model produces `HEADING` (from its own `paragraph_title` class) and
`TITLE` (from `doc_title`) — so Rule 4's first boundary is drawn by a trained
model rather than a font-size threshold.

Still to do: `SUBHEADING`. The model has no third level, so nothing produces it
yet; heading versus subheading needs the rule below, and a person where it
cannot be decided.

**Rule 4 is confirmed** and written in
[plan-templates.md](plan-templates.md#rule-4--title-heading-subheading-confirmed):
title once per document or page section, heading for a major section,
subheading nested under a heading.

Judged **relatively**, never by absolute font size, using position, size against
surrounding text, weight, whitespace, alignment, numbering pattern and
repetition across pages — in that priority.

Where the level is ambiguous the region is still reported as a heading, with the
level marked `unknown`, low confidence, and Title/Heading/Subheading carried as
candidates so review is one click. A subheading wrongly promoted to a title
corrupts the document outline, and outline errors are invisible in the text.

**I12** ⬜ The page becomes the main surface rather than a preview beside a
list, with regions drawn, clicked and corrected on it, and nesting shown as a
tree.

**I13** ⬜ One hash is not enough: a perceptual hash of a filled form differs
from the same form filled differently, while two different forms from one
company can hash close together. Six signals stored as a bundle — perceptual
hash, edge projection, connected-component spread, major region geometry, ink
density grid, detected layout structure — layered cheapest first. Signals 1-5
need no detection, so a template is useful the moment it is uploaded.

**I14** ⬜ 🧪 **Experimental — built configurable, shipped switched off.** Exact
fingerprint → near fingerprint → structural layout → generic detection, each
level more tolerant and more expensive. Bands at 95 / 90 / 80 percent decide
whether to apply, glance, confirm or ignore. All thresholds in configuration.

Enabled only once two or more examples of the same form exist to tune against.
Those examples come from ordinary use — every human correction in the review
screen adds one — so nothing has to be collected specially. Order agreed:
layout knowledge → human corrections → accumulate examples → matching → tune.

**I15** ⬜ The safety mechanism that stops a wrong template quietly corrupting a
document: after placing an expected layout, check there is ink where ink is
expected, that shapes agree, that nothing moved past its tolerance, and that
every required region is present. A missing required region rejects the match.

**I16** ✅ Three images per page — `piply_opdf/quality/images.py`, wired into
`document.py`.

`original` is never modified. `structural` is orientation and deskew only, and
is what **layout, tables and geometry read**. `working` is enhanced for OCR and
descends from `structural`, so OCR inherits the deskew. When no enhancement is
needed, `working` *is* `structural` — the same array, no copy.

Two guards, both from measurement:

- **Layout no longer reads the enhanced page.** `run_all()` enhances then
  detects; when layout read the enhanced PDF, `sample.pdf` went from one table
  of 171 cells to **none**. It now returns 171 cells, 19 rows, 9 columns.
- **Enhancement that destroys structure is discarded.** Rule counts are compared
  before and after; below 90% kept, the enhanced copy is dropped.

Verified behaviour-preserving: component counts across all 16 sample documents
are **identical before and after** the refactor (`tools/corpus_snapshot.py`,
`tools/compare_snapshots.py`) — only `run_all()` changed, and only for the
better.

**I17** 🔄 A page fed sideways fails every later stage at once and nothing
notices. Now detected — `piply_opdf/quality/orientation.py`.

**Reliably answers "is this page sideways?"** Coefficient of variation of the
row-ink profile: upright pages score 2.0-2.7 times the sideways version.
Verified across 11 sample documents, both ways round: **22 checks, 0 wrong**,
4 honest "undecided" (a full-page grid and one dense schedule, where the answer
genuinely is not there).

**Deliberately does not answer "which way up?"** Four measurements were tried
and rejected:

| Signal | Result |
|---|---|
| Ink mass above vs below each line's densest row | 2/8 — worse than chance |
| Baseline scatter of glyph bottoms | Identical both ways: a 180° turn negates the coordinates and the measure is invariant under negation |
| Top-edge vs bottom-edge raggedness | 1/10 — the spread quantises to zero at any working resolution |
| Long ruled lines | Made it worse: a tall table's column rules are longer than its row rules |

Distinguishing 0 from 180 needs character recognition — it is why Tesseract
ships a separate orientation-and-script mode. Guessing at 75% would turn one
page in four upside down. So a sideways page is reported **ambiguous with both
candidates** and goes to a person, which is the governing principle applied
honestly. Remaining work: resolve the direction once an OCR engine is
available.

**I18** ✅ `piply_opdf/baseline/` (adapter) and `piply_opdf/fusion/` (combine).
Off by default: `process_layout(use_baseline=True)`.

Measured across the corpus, the two are **complementary — neither is a superset
of the other**:

| Baseline finds, rules do not | Rules find, baseline does not |
|---|---|
| HEADING 9 pages | KEY_VALUE 11 pages |
| SENTENCE 6, PARAGRAPH 5 | HANDWRITING 10 |
| HEADER 2, TITLE 1 | FOOTER 6, LIST_ITEM 6 |
| **TABLE 1 — the borderless statement** | PANEL 5, LOGO 4, STAMP 4 |

The headline: on `Sbizhub_C2219080509040.pdf` the model finds two table regions
where the rules find **zero**. That is the F7/F11 gap, closed without writing a
borderless detector.

Fusion has three outcomes — agreement raises confidence, a lone finding is kept
at its finder's confidence, and **a disagreement is flagged rather than resolved
silently**, carrying both opinions as candidates.

One bug found by running it: a sentence *inside* a large table region overlaps
it completely, so the first small component swallowed the model's table and the
one finding worth having was reported as "already known". Matching now requires
comparable size as well as overlap — containment is nesting, not identity.

Original description: use a trained document layout model as the **baseline**
for the generic types — title, text, table, figure, list,
header/footer, reading order — and keep Piply's rules for what it does not do:
borderless tables, key-value, nested regions, template knowledge, geometry
validation. Where the two disagree, that is a review signal rather than
something to resolve silently.

Built as an **adapter**, so the package still runs with the baseline absent.

Costs stating plainly: `paddleocr` is **not currently installed** (nor is the
`tesseract` binary), so adopting this makes a heavy dependency required. It must
also be **measured against the existing detectors per type** using the Phase E
corpus — swapping one unmeasured detector for another is not progress.

**I19** ⬜ Detectors and models will change. Without `feature_version`,
`detector_name`, `detector_version`, `model_version`, `source_document` and
`source_page` on every knowledge record and fingerprint, old knowledge becomes
impossible to interpret and silently poisons new results.

**I20** ⬜ `CONFIRMED` / `CORRECTED` / `ADDED` / `DELETED` / `REJECTED` rather
than a single agreed/disagreed counter. They mean different things:
`CORRECTED` counts against a detector's accuracy, `ADDED` against recall,
`DELETED` against precision. Collapsing them throws that away.

**I21** ✅ Three images per page — `piply_opdf/quality/images.py`. Untouched `original`, `structural`
(orientation and deskew only), and `working` (enhanced, derived from
`structural`). **Layout, tables, fingerprinting and geometry read `structural`;
only OCR reads `working`.** Comparing template coordinates against a page
rotated 2 degrees creates mismatch that has nothing to do with layout, and
sharpening for legibility thins the rules table detection needs.

**I22** ⬜ Confidence must be **derived from measurable evidence and calibrated
against human-labelled results** — not declared, and not merely "earned".
Combines detector evidence, geometry evidence, knowledge agreement, structural
evidence, historical reliability and the baseline model's own score, then fitted
against the Phase E corpus so 0.90 means right about 90% of the time. Historical
agreement is one input, not the whole score. Re-fitted whenever a detector
version changes.

**I23** ⬜ The governing principle: *never silently trust a classification.*
Wrong classification + high confidence + no review = a silently bad document,
and nobody catches it later. Every component carries `predicted_type`,
itemised `evidence`, `confidence`, `source_detector`, `knowledge_match` and
`review_status`. Insufficient confidence means human review. **A template match
can never override geometry verification.**

**I24** ⬜ "Columns → rows → cells" fails on the documents this targets: a
wrapped description looks like new rows, so every column after it misaligns.
Rebuilt as text blocks → candidate columns → horizontal alignment → baseline
clustering → **continuation analysis** → row candidates → row confidence →
cells. **No single column may be the mandatory row anchor** — some rows have no
date, some only a total.

**I1 — Structure fingerprint** ⬜
A hash of page *structure* rather than pixels: component types, their relative
positions and sizes, normalised for page size. Robust to different values in
the same form.

**I2 — Template match** ⬜
On a fingerprint match, skip full detection and read known field positions
directly. Turns ~40 s into ~2 s and makes accuracy near-perfect for repeat
templates, because the layout is recalled rather than re-derived. Falls back to
full detection on mismatch, and on low match confidence detects and compares.

**I3 — Named fields** ⬜
Once an operator confirms `Req No` is a field on template *X*, that name binds
to that position for every future document of the family. Turns anonymous
key-values into a stable schema.

**I4 — Structured export** ⬜
For a form, HTML is not the most useful output — a field dictionary is:

```json
{ "Req No": "PHC262862", "Collected On": "2026-02-11T11:58", "Sample Type": "Plasma-R" }
```

The key/separator/value units already exist; this consumes them. JSON and CSV.

---

## Phase J — Compliance and provenance 🟠

The sample documents contain PAN cards, photographs, signatures and an HIV test
result. If this handles real patient or customer data, these belong in the
design rather than retrofitted.

| ID | Item | Status |
|----|------|--------|
| J1 | PII classification per component | ⬜ |
| J2 | Redaction in exports | ⬜ |
| J3 | Audit trail | ⬜ |

**J1 — PII classification** ⬜
Flag components holding personal data. Most of the signal already exists:
`SIGNATURE` and `IMAGE` types, plus key names matching known patterns (name,
DOB, ID number, address, phone, medical result). Recorded per component in the
manifest.

**J2 — Redaction** ⬜
Optional masking of PII-flagged components in HTML, JSON and CSV exports, so a
document can be shared for analysis without exposing identity.

**J3 — Audit trail** ⬜
Who verified what, and when — already sketched as `provenance.verified_by` /
`verified_at` in the manifest. Cheap now, painful to retrofit, and likely
required wherever medical or insurance records are handled.

---

## Phase E — Package shape and weight 🟢

| ID | Item | Status |
|----|------|--------|
| E1 | Remove dead dependencies | ⬜ |
| E2 | Remove dead code | 🔄 |
| E3 | Replace `imagehash` with NumPy | ⬜ |
| E4 | Split `document.py` | ⬜ |
| E5 | Define the library's public API | ⬜ |
| E6 | Prove the library stands alone | ⬜ |

**E1** `scipy` (declared, **zero** imports), `pandas` and `scikit-learn` (only
in the non-functional `random_forest.py`), `scikit-image` (one SSIM call — ~15
lines of NumPy). Pure subtraction.
**E2** 🔄 The three test modules importing `phases.phase3/4/5` are **deleted** —
they failed at collection and blocked the entire suite from running, so this
part could not wait. Still to go: 13 four-line stubs in `modules/`, and the
`phases/` package (now down to `phase1_assess` and `phase2_enhance`, both still
used and both still tested).
**E3** pHash is a DCT on an 8×8 reduction, ~30 lines. Also drops the Pillow
conversion it forces.
**E4** 710 lines orchestrating everything.

**E5 — Public API** ⬜
The library already has no dependency on the app — checked: no `import app`
anywhere in `piply_opdf`, and no FastAPI, Jinja or uvicorn. But the app reaches
into internal paths (`piply_opdf.modules.*`, `piply_opdf.database.*`), so the
boundary holds by accident rather than by design.

Fix: export a stated public surface from `piply_opdf/__init__.py` — `Document`,
the component types, the detector and segmenter registries, the manifest
reader, the knowledge base. Anything not exported is internal and may change.
The app then imports only the public surface.
*Raised: "Keep feature library & UI application separate… Library shouldn't be
depend on UI."*

**E6 — Prove it stands alone** ⬜
A test that imports `piply_opdf`, processes a document and reads the manifest
**without `app/` present at all**. Turns R18 from an intention into something
that fails the build if broken.

Also: no library code may import a web framework, and `pyproject.toml` must
keep shipping only `piply_opdf` so `pip install piply-opdf` gives the library
and nothing else.

---

## Phase G — Learning 🔵

| ID | Item | Status |
|----|------|--------|
| G1 | Backfill `component_type` | ⬜ |
| G2 | Rebuild `ml/random_forest.py` | ⬜ |
| G3 | Wire `run_specialized_model()` | ⬜ |
| G4 | Character-level confidence | ⬜ |

**G1** NULL for 1,549 of 1,647 knowledge rows — blocks all per-type training.
**G2** Non-functional: three undefined functions, wrong table name, wrong DB
path.
**G4** Split a word crop into characters by vertical ink projection; correct
only the weak characters.
*Raised: "if confidence score is 100% then okay but if it is less, then we can
find confidence character by character".*

> **Caveat.** Character segmentation is reliable for printed, separated glyphs
> and unreliable for joined script — exactly the handwriting where confidence
> is lowest. Offer character correction when segmentation is confident; fall
> back to whole-word otherwise.

---

## Phase X — Delivered ✅

| ID | Item |
|----|------|
| X1 | UI redesign — light, professional, classic premium |
| X2 | Fix undefined `renderComponents()` crash |
| X3 | Header/footer detection on scanned PDFs |
| X4 | `core/` contracts — types, detector, segmenter, registry, exceptions |
| X5 | Detector strategy pattern + CV fallbacks (5 detectors) |
| X6 | Segmentation layer — `Segmenter` + `segment_tree()` |
| X7 | Title detector |
| X8 | Graphic/residual detector + content classifier |
| X9 | Reject photos and ID cards detected as tables |
| X10 | Multi-column key-value form rows |
| X11 | Shared text-layer primitives (removed triplication) |
| X12 | Documentation rebuild |

**X3** Root cause: `sample.pdf` is scanned (8 JPEGs, **0 characters**), and 6
of 7 detectors read only the text layer.
**X8** One detector plus one classifier rather than four detectors — all need
the same measurements from the same crop. 60/60 on the calibration corpus.
*Raised: "keep a segment for non-detectable items… images of any person or
animal".*
**X9** *Raised: "TABLE 111 is actually a scanned image of a pan card"; "a human
image detected as table".* Gating with the classifier revealed a regression — a
real table classified as SIGNATURE because its grid forms one large component;
separated by `component_area_cv` (table ~7.8, signature ~0.0).
**X10** *Raised: "PARAGRAPH 2060 is actually… group of many key-value pairs".*
Four fixes, three latent bugs: baseline merging, separator anchoring, `11:58`
split as a field separator, `Ref. Dr.` rejected for ending in a full stop.
