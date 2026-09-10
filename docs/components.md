# Component Vocabulary and Decision Rules

The complete set of types the system recognises, how they relate, and — most
importantly — the **decision rules that separate types which look alike**.

A classification boundary is a *definition*, not a discovery. Where two types
share every measurable property, the answer is not a cleverer classifier; it is
a rule that says where the line sits. This document records those rules.

---

## The vocabulary

### Containers

Hold other components. Their children are found by running the detector suite
again, scoped to the container's interior.

| Type | Definition |
|------|------------|
| `TABLE` | A bordered grid with **two or more cells** |
| `BORDERLESS_TABLE` | Tabular alignment without ruled borders |
| `PANEL` | A closed frame with **no internal division** — one cell |

### Textual

Carry recognisable text and segment down to words.

| Type | Definition |
|------|------------|
| `TITLE` | The main document or section title — see **Rule 4** |
| `HEADING` | A major section heading |
| `SUBHEADING` | A subsection heading, nested under a heading |
| `HEADER` | Text in the top band of the page |
| `FOOTER` | Text in the bottom band |
| `PARAGRAPH` | A multi-line run of prose |
| `SENTENCE` | A single-line run of prose |
| `LIST_ITEM` | A line opening with a repeated marker glyph |
| `KEY_VALUE` | A label/value pair with a separator |
| `ROW`, `COLUMN`, `CELL` | Table structure |
| `WORD` | Terminal unit |

### Graphic

Pictorial. No text units, no OCR by default.

| Type | Definition |
|------|------------|
| `SIGNATURE` | A handwritten mark of **one or two word-groups** |
| `HANDWRITING` | Handwritten text of **three or more word-groups** |
| `STAMP` | An inked seal — **single ink colour** |
| `LOGO` | A designed mark — **multiple colours** |
| `IMAGE` | A photograph |
| `SEPARATOR` | A ruled line — divider, box edge, underline |
| `UNKNOWN` | **Everything else** |

`SEPARATOR` exists because a ruled line is on the page and something has to own
it. Without a name for it, a 2386×27 divider matched every signature condition —
sparse ink, few pieces, one word-group — and documents reported signatures they
did not contain. See [Rule 0](#rule-0--is-it-text-at-all).

`UNKNOWN` is a first-class outcome, not a failure. See
[capabilities.md](capabilities.md#how-uncertainty-is-handled).

---

## Decision rules

Four groups of types are visually similar enough that measurement alone cannot
separate them. Each is resolved by definition. Before any of them runs, two
cheaper questions are asked first.

### Rule 0 — is it text at all?

> **Ask "is this writing?" before asking "what colour is it?"**

This ordering is the rule, not an implementation detail. Colour says nothing
about whether something is writing. Asking about colour first meant:

- blue hyperlink text came back `STAMP` (one ink colour)
- headings printed on a yellow band came back `LOGO` (two colours)
- an entire scanned bank statement came back `HANDWRITING`

**How text is recognised.** Text is many small pieces — 585–1916 per megapixel,
against 25 for a logo, 213 for a stamp, 284 for a photograph. That gap is what
makes it safe to ask first. A region qualifies as text when it is dense **and**
either of:

| Signal | Holds for |
|--------|-----------|
| Stroke width barely varies (< 0.20) | Digital text and clean scans |
| Glyph bottoms line up (< 0.15) **and** strokes < 0.41 | Ordinary office scans |

**Why two.** Stroke uniformity is what tells print from pen — on a clean page.
Scanning destroys it: real scanned print measures **0.34–0.40** and handwriting
**0.43**, which is no usable gap. What survives a scan is the **baseline** —
printing rests on a ruled line, a pen wanders. Measured on real scans: printed
text **0.019–0.131**, handwriting up to **0.89**.

Baseline spread is measured as median absolute deviation, not standard
deviation, because descenders (`p`, `j`, `q`) sit below the line and are a
minority. A standard deviation lets them dominate, which made ordinary prose
score worse than a line of digits.

### Rule 0b — is it a ruled line?

> **A line is far longer than it is thick, and its ink sits in a few rows.**

Asked after text — a single wide line of prose is also long and thin, and must
stay text — and before the pen rules, which used to swallow dividers.

Measured as aspect ratio ≥ 12 with row coverage ≤ 0.60. Real dividers measured
72 and 88; genuine marks sit far below (signature 2.4, logo 1.7, photo 1.0).

### Rule 1 — `TABLE` vs `PANEL`: cell count

> **A table has two or more cells. A single-cell frame is a `PANEL`.**

Both are closed rectangular frames; a one-cell table and a boxed paragraph are
pixel-identical. Cell count is decidable from the internal grid — count
intersections of horizontal and vertical rules inside the frame.

```
┌─────────────┬────────────┐
│  Name       │  Value     │   2+ cells        →  TABLE
├─────────────┼────────────┤
│  Age        │  42        │
└─────────────┴────────────┘

┌────────────────────────────┐
│  INTERPRETATION:           │   no internal rules
│  The available research…   │   1 cell         →  PANEL
└────────────────────────────┘
```

**Order matters:** `PANEL` detection runs *before* `TABLE` detection, so a
frame is examined for internal structure before anything claims it as tabular.
A frame promoted to `TABLE` must show at least one internal rule producing a
second cell.

**Consequence:** a real single-row, single-column table is reported as a
`PANEL`. This is correct by the definition above — and harmless, because both
are containers whose children are found the same way.

### Rule 2 — `STAMP` vs `LOGO`: colour count

> **A stamp is a single ink colour. A logo carries multiple colours.**

Both are saturated compact marks. The separator is chromatic distribution:
a rubber stamp deposits one ink; a designed logo is normally polychrome.

Measured by quantising the region's hue channel over sufficiently saturated
pixels and counting distinct clusters weighted by area:

- **1 dominant chroma cluster** → `STAMP`
- **2 or more** → `LOGO`

Hue is binned in 15° steps, because scanning shifts colour slightly and a
faded stamp must not split into two clusters. A cluster must hold 12% of the
coloured pixels to count — without that floor, anti-aliasing fringes make every
logo look polychrome.

**Tie-break for a monochrome mark.** Where the colour count is 1, the two are
told apart by **fragmentation**: a seal is applied by hand, so uneven pressure
breaks its edges into many pieces, while a printed logo stays solid. Measured
as components per megapixel — stamps ~213, logos ~25.

**A solid single-colour mark is a genuine tie**, so it is reported as `LOGO`
with low confidence and `STAMP` recorded as the alternative — not `UNKNOWN`.
See [When two types look alike](#when-two-types-look-alike).

Rule 2 applies only to a **dense** mark. Sparse coloured ink is line-work or
text — asking "logo or stamp?" about a table ruled in blue is meaningless, and
answering it cost a real table.

### Rule 3 — `SIGNATURE` vs `HANDWRITING`: word-group count

> **One or two word-groups is a `SIGNATURE`. Three or more is `HANDWRITING`.
> When uncertain, `HANDWRITING`.**

Both are pen strokes; they differ by intent, which is not visible. Extent is
visible: a signature is a name, so one or two groups; a handwritten note is a
sentence.

A "word-group" is a run of connected ink separated from its neighbours by more
than a quarter of the region's height, so the rule holds for a large signature
and a small one alike.

**Component density backs the count up.** Words written close together merge
into a single group, so the count alone is not enough. A signature is a few
long strokes (~18 components per megapixel); handwriting is many short ones
(~704). Without that backup, tightly spaced handwriting reads as a signature.

```
   Cursive mark, 1–2 groups          →  SIGNATURE
   Cursive text, 3+ groups           →  HANDWRITING
   Ambiguous / unmeasurable          →  HANDWRITING   (agreed fallback)
```

The fallback direction is deliberate. Mislabelling a signature as handwriting
sends it for OCR and human review — recoverable. Mislabelling handwriting as a
signature marks it as a graphic and it is never read — a silent loss.

### Rule 4 — `TITLE` vs `HEADING` vs `SUBHEADING`: relative prominence

> **Title once per document or section. Heading starts a section. Subheading
> starts a subsection under a heading.**

| Type | Definition |
|------|------------|
| `TITLE` | Main document or page-section title. Largest or most prominent, normally **once**. |
| `HEADING` | Major section heading, introducing a significant section. |
| `SUBHEADING` | Nested under a heading; introduces a smaller subsection. |

```
   Title
    └── Heading            major section
         └── Subheading    subsection under a heading
```

**Judged relatively, never by absolute font size.** A 14 pt line is a heading in
a document set in 9 pt and body text in one set in 16 pt. The decision uses, in
priority order:

1. Position and hierarchy — what comes before and after
2. Font size **relative to the surrounding text**
3. Weight
4. Whitespace before and after
5. Alignment
6. Numbering pattern — `1.`, `1.1`, `A.`
7. Repetition and structure across pages

**When the level is ambiguous, do not force it.** The region is still reported
as a heading, with the level marked unknown, low confidence, and all three
carried as candidates so review is one click. Only the *level* is deferred, not
the identification — so this is consistent with
[decide, don't defer](#when-two-types-look-alike) rather than an exception to it.

A subheading wrongly promoted to a title corrupts the document outline, and an
outline error is invisible in the text — nobody catches it downstream.

**Where the answer comes from today.** The baseline layout model distinguishes
`doc_title` from `paragraph_title`, so `TITLE` and `HEADING` are decided by a
trained model rather than a threshold. It has no third level, so `SUBHEADING`
is not yet produced by anything — see backlog I11.

---

## When two types look alike

> **Decide, don't defer.** When the evidence narrows to a small set of
> candidates but cannot choose between them, emit the most likely type with a
> **low confidence** and record the alternatives. Reserve `UNKNOWN` for content
> that matches nothing at all.

A component therefore carries not just a type but, where relevant, the
runners-up:

```jsonc
{
  "type": "LOGO",
  "confidence": 0.55,
  "candidates": [
    { "type": "LOGO",  "confidence": 0.55 },
    { "type": "STAMP", "confidence": 0.45 }
  ]
}
```

**Why this beats `UNKNOWN` for near-ties.** The operator reviewing this is a
data-entry user, not an engineer. `UNKNOWN` asks them an open question — *what
is this?* — with a free-text answer. A ranked pair asks a closed one — *logo or
stamp?* — answered with one click. Same human effort, far less cognitive load,
and the correction is structured data rather than a typed string.

The human's choice becomes the source of truth and enters the knowledge base,
so the same mark resolves automatically next time.

`UNKNOWN` remains for genuine non-recognition — a photograph of a person, a
diagram, a coffee stain. There, no candidate list would be honest.

**This does not weaken the under-claim principle.** A low-confidence guess is
still surfaced for review; it is not silently accepted. What changes is only
*how the question is asked*.

---

## Containment

`PANEL`, `TABLE` and `BORDERLESS_TABLE` hold children of **any** type,
discovered by the ordinary detector suite scoped to the interior. There is no
special parser for boxed content.

A signature box from a medical form decomposes as:

```
PANEL
├── SIGNATURE        (client's mark, 1 group)
├── KEY_VALUE        "Date: 11|02|2026"
│   ├── WORD  key        "Date"
│   ├── WORD  separator  ":"
│   └── WORD  value      "11|02|2026"
├── SENTENCE         "Signature of Life Assured/ Client"
├── SIGNATURE        (examiner's mark)
├── STAMP            (clinic seal)
├── PARAGRAPH        "Dr. A. Vanishri / MBBS DCP MD / APMC NO.90084"
├── KEY_VALUE        "Place: Vizag"
└── SENTENCE         "Signature & Seal of Medical Examiner"
```

Nesting depth is capped to prevent a container detecting itself as its own
child.

---

## Levels

Everything is a unit. Units sit inside other units, forming a tree.

```
Level 0   PAGE          the whole page is one unit
Level 1   LAYOUT        each table, paragraph, panel, header… is a unit
Level 2   COMPONENT     each row, column, sentence… is a unit
Level 3   COMPONENT     each cell, word… is a unit
   ⋮
Last      REVIEW UNIT   the smallest unit — this is what a person checks
```

Two examples:

```
PAGE  →  TABLE      →  ROW / COLUMN  →  CELL          ← person checks the cell
PAGE  →  PARAGRAPH  →  SENTENCE      →  WORD          ← person checks the word
```

A panel holds other layouts, so it simply adds a level:

```
PAGE  →  PANEL  →  KEY_VALUE  →  KEY / SEPARATOR / VALUE   ← person checks these
```

**The last level is always what a person reviews in the UI.** Nothing above it
is reviewed directly — if a cell is wrong, you fix the cell, not the table.

### What each layout splits into

| Layout | Splits into |
|--------|-------------|
| `TABLE` / `BORDERLESS_TABLE` | `ROW` / `COLUMN` → `CELL` |
| `PANEL` | *(any layout — found by running detection inside it)* |
| `PARAGRAPH` | `SENTENCE` → `WORD` |
| `SENTENCE` | `WORD` |
| `HEADER` / `FOOTER` / `TITLE` / `LIST_ITEM` | `WORD` |
| `KEY_VALUE` | `KEY` / `SEPARATOR` / `VALUE` |
| Graphic types | *(nothing — they are not text)* |

`CELL` and `WORD` do not split further. Graphic types are their own review unit:
a person confirms what the picture is, not what it says.

Splitting `KEY_VALUE` into three is the most useful decision in the design. A
key like `Invoice Number` appears on every document of the same kind and is
checked once. Its value is different every time.

### Reading order

Order is decided **level by level**, walking down the tree. Inside any unit,
its children are ordered top to bottom, then left to right.

So a panel is one unit in the page order, and its contents are ordered inside
it. Its children never mix with text outside the panel.

Page-level column layout (a two-column article) is handled separately, before
this — see backlog B3.

---

## Detection order

Order is significant — each stage passes its output as exclusions to the next,
and whichever runs first claims a contested region.

```
1.  PANEL              closed frames, no internal division
2.  TABLE              bordered grids, 2+ cells
3.  TITLE              before header: a heading sits in the top band
4.  HEADER
5.  FOOTER
6.  KEY_VALUE
7.  LIST_ITEM
8.  PARAGRAPH / SENTENCE
9.  BORDERLESS_TABLE
10. GRAPHIC            residual sweep — claims everything remaining
```

Rationale for the two non-obvious positions:

- **`PANEL` before `TABLE`** implements Rule 1: examine a frame for internal
  structure before anything claims it as tabular.
- **`TITLE` before `HEADER`** because a prominent heading lies inside the top
  band, so whichever runs first takes it. A large, short, typographically
  distinct line is a title; the running header is what remains.

---

## Implementation status

| Type | Status |
|------|--------|
| `TABLE`, `HEADER`, `FOOTER`, `TITLE`, `KEY_VALUE`, `PARAGRAPH`, `SENTENCE`, `LIST_ITEM`, `WORD` | ✅ implemented |
| `SIGNATURE`, `HANDWRITING`, `LOGO`, `IMAGE`, `UNKNOWN` | ✅ implemented |
| `SEPARATOR` | ✅ implemented |
| `HEADING` | ✅ implemented — from the baseline model |
| `SUBHEADING` | 🟡 in the vocabulary, nothing produces it yet |
| `PANEL` | ✅ implemented (F1, F4) |
| `STAMP` | ✅ implemented (F3) |
| Recursive containment | ✅ implemented (F2) |
| `BORDERLESS_TABLE` | 🟡 text layer only, nothing on scans |

Rules 0–4 are implemented, except the heading/subheading level. Colour clusters and word groups are measured for
every region, and near-ties carry their alternatives.
