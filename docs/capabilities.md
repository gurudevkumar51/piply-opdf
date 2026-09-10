# Capabilities and Limits

What the system can do today, what it cannot, and what is guaranteed regardless.

Written to be trusted rather than to impress: a limit you know about is
manageable, a limit you discover on a customer document is not. Anything not
listed under **Can do** should be assumed absent.

---

## Guarantees

Two properties hold by construction, not by tuning, and cannot silently
degrade.

### 1. Nothing is lost

> Every region of ink on every page becomes some component.

A residual sweep runs last, with every prior detection as exclusions. Whatever
ink remains is captured — classified if possible, `UNKNOWN` if not — cropped,
indexed and reviewable.

A photograph of a person, a diagram, a torn edge, a coffee ring: all become
components. None are discarded.

*Measured as `coverage.ink_accounted` per page. Target ≥ 0.995. Not yet
computed — backlog H3.*

### 2. Nothing is fabricated

> No component carries text that was not read from a real source.

Every component with text records `text_source`, one of: `text_layer`, `ocr`,
`knowledge`, `human`. There is no code path that synthesises, autocompletes or
infers text. A component whose text could not be obtained carries `""` and
`needs_ocr: true` — never a plausible guess.

No component is emitted for a region containing no ink.

---

## Can do

### Input

- PDF, both digital (with a text layer) and scanned (image-only)
- Image files — PNG, JPG
- Multi-page documents
- Any page geometry; verified A5 → Legal, portrait and landscape
- Any render resolution; verified 150 → 600 DPI

### Quality handling

- Measure blur, noise, contrast and skew per page; rate `good`/`acceptable`/`poor`
- Enhance selectively — deskew, denoise, CLAHE contrast, unsharp mask, border
  repair, applied only where the assessment flags a need
- **Correct skew automatically** on scanned pages: 0.00° measured error across
  ±8°, ~40 ms/page, with detection output identical at every angle tested
- **Notice a sideways page** and flag it rather than turning it on a guess
- **Carry each page as three images** — an untouched `original`, a `structural`
  copy corrected only for orientation and skew, and a `working` copy enhanced
  for OCR. Detection reads `structural`; only OCR reads `working`
- **Discard enhancement that destroys structure.** Measured on `sample.pdf`,
  enhancing cost a 171-cell table at 0.05° of rotation where the unenhanced page
  survived 2°, so the enhanced copy is kept only if the page still has
  comparable line structure

### Detection

Every detector works on **both** digital and scanned input, choosing a
text-layer or computer-vision strategy per page:

| Component | Digital | Scanned |
|-----------|---------|---------|
| Table (bordered) | ✅ | ✅ |
| Header, Footer | ✅ | ✅ |
| Title | ✅ | ✅ |
| Key-value, including multi-column form rows | ✅ | ✅ |
| Paragraph, Sentence | ✅ | ✅ |
| List item | ✅ | ✅ |
| Panel — a closed frame, decomposed inside | ✅ | ✅ |
| Signature, Handwriting, Logo, Stamp, Image | ✅ | ✅ |
| Separator — a ruled line | ✅ | ✅ |
| Unknown / residual | ✅ | ✅ |

A document and its rasterised twin produce **identical** component counts —
the strongest available evidence that the two paths agree.

**Optionally, a trained layout model as well.** `process_layout(use_baseline=True)`
runs PP-DocLayout alongside the rules and fuses the two. They are complementary
rather than competing — measured across the corpus, the model finds headings and
borderless-table regions the rules miss, while the rules find key-values, panels
and marks the model has no concept of. Where both claim a region and name it
differently, the component is **flagged for review** carrying both opinions,
never resolved silently. Off by default: it costs several seconds a page.

### Recognition and learning

- OCR on region crops, never whole pages — PaddleOCR primary, Tesseract fallback
- Exact perceptual-hash match bypasses OCR entirely for previously verified content
- Human corrections become a portable knowledge base, reusable across documents
  and machines
- Confidence is halved when a text box touches a crop edge, flagging possible
  truncation

### Segmentation

- Paragraph → sentence → word
- Header / footer / title / list item → word
- Key-value → key / separator / value
- Table → row / column → cell

---

## Cannot do

### Not implemented

| Gap | Consequence | Backlog |
|-----|-------------|---------|
| **Borderless table *structure*** | The trained model finds the region; nothing builds its rows and cells, so a bank statement returns values without the columns they belong to | F7, F11 |
| **Which way up a sideways page goes** | Detected and flagged, but the quarter turn needs a person | I17 |
| **Page column detection** | A two-column article is processed as single-column | B3 |
| **Reading order** | The manifest is an unordered set of boxes | B3 |
| **HTML reconstruction** | Exports are JSON / CSV only | D1 |
| **ML prediction** | Stub; blocked on training data | G1–G3 |
| **Character-level confidence** | Correction is whole-word only | G4 |
| **Merged table cells** | rowspan / colspan not represented | F9 |
| **`SUBHEADING`** | In the vocabulary; nothing produces it yet | I11 |
| **Calibrated confidence** | Every value is a literal in the code, so "review the doubtful ones" selects everything | I22 |

Implemented since an earlier version of this table said otherwise: `PANEL`
(F1), recursive detection inside containers (F2), `STAMP` (F3), `SEPARATOR`,
`HEADING`, and a configurable OCR engine.

### Incomplete

| Gap | Consequence | Backlog |
|-----|-------------|---------|
| **Manifest omits content** | Titles, list items and all graphic/unknown regions are detected then dropped before reaching disk | B1 |
| **Units not persisted** | Titles, graphics and the children of header/footer/key-value never reach the database, so they cannot be reviewed | B5 |
| **Whole-document processing** | A 24-page PDF yields nothing until the last page completes | C1 |
| **Enhancement is document-wide** | One poor page causes all 24 to be enhanced | A3 |

### Will not do

Deliberate scope boundaries, not gaps.

- **No network calls at inference time.** No cloud OCR, no remote models, no
  webfonts. The system runs fully offline.
- **No GPU requirement.** CPU only.
- **No large ML models.** Classical CV and mathematics are preferred; anything
  heavier must justify itself against an analytic alternative.
- **No automatic acceptance of uncertain values.** Only an exact hash match
  against human-verified content bypasses review. Visually similar crops can
  contain different text, so similarity never auto-fills.

---

## Known limits

Honest boundaries within features that do work.

**Skew beyond ±10°** is not searched. Larger rotation is an orientation
problem, and orientation is handled separately — see below.

**A sideways page is detected but not turned.** Whether a page's text runs
across or down it is answered reliably: measured over 11 sample documents, each
tested both ways, **22 checks with 0 wrong** and 4 honest "undecided". *Which*
quarter turn is needed cannot be decided from ink alone — four measurements were
tried and the best managed 2 correct out of 8, worse than chance. So the page is
flagged with both candidates and a person chooses. Resolving it needs character
recognition, which is what Tesseract's separate orientation mode does.

**Classifier calibrated on synthetic data.** Thresholds separating signature,
handwriting, logo and photograph were derived from generated samples. Real
signatures, stamps and scanned photographs vary more widely. Reading all 88
sample pages showed how far that can go wrong — see [audit.md](audit.md). Where
a boundary has since been reset from real measurements, the code says so.

**Rotated text is not recognised as text.** Rule 0 leans on glyphs sitting on a
ruled baseline, which assumes the text is horizontal. Text turned 90° — a
vertical margin label, a chart axis — fails it and is typed as a graphic. The
text is captured, so nothing is lost, but the type is wrong (backlog F20).

**Large display text is not recognised as text.** Big glyphs mean fewer pieces
per megapixel, so a headline can fall under the text density floor while its
stroke variation reads as pen-like. The density measure is not scale-free with
respect to font size (backlog F21).

**Borderless tables are not assembled.** Their contents are found and typed
correctly, but as loose text rather than as rows and cells. A scanned bank
statement comes back as its values, not as a table (backlog F7, F11).

**Logo adjacent to a title on a scanned page.** Line-merging can join them, so
neither is cleanly separated. Real logos usually sit in a corner, where this
does not arise.

**Character segmentation for cursive.** Planned character-level correction
(G4) is reliable for printed, separated glyphs and unreliable for joined
script — exactly the handwriting where confidence is lowest. Intended
behaviour is to offer character correction only when segmentation is
confident, falling back to whole-word.

**Detection accuracy is unmeasured.** The suite proves *consistency* — digital
and scanned agree, behaviour is stable across sizes and DPIs, known bugs do not
recur. It measures no precision or recall against ground truth, and runs almost
entirely on synthetic pages. **Any claim about accuracy on real documents,
favourable or otherwise, is currently unsupported.** See
[quality.md](quality.md).

The nearest thing to a measurement is [audit.md](audit.md): every page of the
16 sample documents read against what the system produced. It is a person
looking at pictures, not a number — but it found nine defects while the suite
was green and coverage read 0.9943.

---

## How uncertainty is handled

Two distinct situations, handled differently.

**Near-tie between candidates.** The evidence narrows to a small set but cannot
choose — a monochrome logo that might be a stamp. The system emits the most
likely type with **low confidence** and records the alternatives. The operator
sees a one-click choice rather than an open question, and their answer becomes
the source of truth and enters the knowledge base.

**Genuine non-recognition.** Nothing matches — a photograph of a person, a
diagram, a coffee stain. The region becomes `UNKNOWN`: still captured, cropped,
indexed and reviewable, but carrying no claim about what it is. A candidate
list here would be dishonest.

Both surface for review; neither is silently accepted. What differs is how the
question is put to the human.

Underlying both: **under-claim rather than over-claim.** A low-confidence or
unknown component is seen and resolved. A confidently mistyped one is parsed
with the wrong rules and propagates silently into the manifest and any
reconstruction.

---

## Summary

| Property | Status |
|----------|--------|
| Nothing lost | ✅ Guaranteed by construction |
| Nothing fabricated | ✅ Guaranteed by construction |
| Works on scanned documents | ✅ Every detector, both paths |
| Works at any page size and DPI | ✅ Verified A5→Legal, 150→600 DPI |
| Skew corrected automatically | ✅ 0.00° error across ±8° |
| Boxed regions understood | ✅ `PANEL`, with detection re-run inside |
| Page fed sideways is noticed | 🟡 detected and flagged; the direction needs a person |
| OCR engine swappable | ✅ PaddleOCR primary, chosen in configuration |
| Trained layout model available | ✅ Optional baseline, fused with the rules |
| Manifest complete | ❌ Discards titles, lists, graphics |
| Reading order | ❌ Not implemented |
| HTML output | ❌ Not implemented |
| **Accuracy measured** | ❌ **No ground truth yet — the largest gap** |
