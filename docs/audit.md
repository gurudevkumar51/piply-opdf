# Detection Audit — Reading Every Sample Against What the System Produced

Counts and coverage cannot tell you whether a paragraph was really a paragraph.
This audit does the only thing that can: renders every detected box onto the
page, reads the original, and compares them by eye.

**It found nine defects that no number in the project had surfaced.** Four are fixed; five are logged with their measurements. Coverage
across the same 88 pages was 0.9943 before the audit and 0.9943 after the fixes
— because coverage asks *"was anything lost?"*, never *"was it understood?"*.

Reproduce with:

```bash
python tools/draw_overlay.py "path/to/documents" --out=_overlay_out
```

---

## Method

| | |
|---|---|
| Documents | 16 (10 digital, 4 scanned, 2 images) |
| Pages | 88 |
| Compared | Original page vs. every detected box, labelled and coloured by type |
| Judged on | **Layout** (is the region right?) and **component** (is the type right?) |

Boxes are coloured by family — containers cool, text warm, graphics vivid — so
a wrong type shows up without reading the label.

---

## What was wrong

Nine defects, in the order they cost the most. Four fixed, five open —
each open one carries the measurements that will be needed to close it.

### 1. Colour was asked about before text ✅ fixed

The colour rules ran before anything asked whether a region was *writing*.
Consequences seen on real pages:

| Document | Content | Was | Should be |
|---|---|---|---|
| `Sbizhub` p1–2 | The entire bank statement | `HANDWRITING` | text |
| `Sbizhub` p1 | Column headings on a yellow band | `LOGO` | text |
| `sample11` p1 | Blue hyperlink text | `STAMP` | text |

A scanned statement of typed figures was being handed to an operator as if
someone had filled it in by hand.

**Fixed** by asking "is this text?" first — Rule 0 in
[components.md](components.md#rule-0--is-it-text-at-all). This needed a new
measurement: stroke uniformity cannot survive a scan (real scanned print
measures 0.34–0.40 against handwriting's 0.43), but **baseline alignment** can
— printing rests on a ruled line, a pen wanders.

### 2. Ruled lines had nowhere to go ✅ fixed

A 2386×27 divider satisfied every signature condition — sparse ink, few pieces,
one word-group — so `OD330106520353075100.pdf` reported five signatures it does
not contain, and `PolicyStatus` reported one for a horizontal rule.

**Fixed** by adding `SEPARATOR` to the vocabulary and testing for it after text
and before the pen rules.

### 3. Missed text was filed as "unknown" ✅ fixed

The residual sweep rewrote *any* text verdict to `UNKNOWN`. On `Sbizhub` that
put every value on the page into the "nobody knows what this is" bin. Reaching
the sweep means the text detectors missed a region, not that it stopped being
text.

**Fixed**: missed text is now a `SENTENCE` flagged `needs_ocr`, so it is read
and reviewed instead of parked.

### 4. Large regions were typed as small marks ✅ fixed

A signature, a stamp and a logo are all **marks** — small things. Nothing
enforced that, so:

| Document | Region | Was |
|---|---|---|
| `sample-img1` | The whole revenue chart | `SIGNATURE` |
| `sample.pdf` | An empty table column, a third of the page tall | `SIGNATURE` |
| `sample6` p10 | The whole transaction table | `HANDWRITING` |

Real marks measure ~0.5–2.3% of a page; these are 6–45%.

**Fixed** with a size cap in the residual sweep — a mark above 5% of the page
is reported `UNKNOWN` instead. The classifier cannot apply this itself: it only
ever sees the crop, never the page. Measuring all 198 marks across the corpus
put the boundary where it is; it is a sanity check, not a classifier.

Re-measured after the fix:

| Marks larger than | Before | After |
|---|---|---|
| 2% of the page | 49 | 23 |
| 4% | 37 | 11 |
| 6% | 22 | **0** |
| 8% | 13 | **0** |

Total marks fell from 198 to 172. The 26 that went were regions no larger than
a mark should ever be — the chart, the empty column, the transaction table.

### 5. Rotated text is not recognised ⬜ open

Baseline alignment assumes horizontal text. On `PublicWaterMassMailing` p4 the
entire vertical left margin — *"Missouri Department of Health & Senior
Services"* — is typed as `LOGO`, `LIST_ITEM` and `STAMP`. Chart axis labels on
`sample-img1` go the same way.

### 6. Large display text is not recognised ⬜ open

`sample5` p1: the HDFC tagline *"We understand your world"*. Big glyphs mean
**few components per megapixel** — 138–215, under the 400 text floor — and the
light face gives stroke variation of 0.475–0.501, *above* handwriting. Neither
signal helps.

Made worse because the sweep splits the line into one region per word, so each
is too small to measure a baseline from.

### 7. Numbered lists read as key-value pairs ⬜ open

`Moda` p27: a 25-item county list. `1.` + `Benton` looks like key + separator +
value, so most items came back `KEY_VALUE` while a few came back `LIST_ITEM` —
inconsistently, within one list.

### 8. Interior detection is weak on skewed scans ⬜ open

`sample10` p21 (lowest coverage on the corpus, 0.9477): the panel is found, but
most of the printed question text inside it is never claimed. The page is
visibly skewed and low contrast.

### 9. Smaller type errors ⬜ open

| Document | Region | Was | Should be |
|---|---|---|---|
| `PolicyStatus`, `sample5`, `sample6` | Company logo | `IMAGE` | `LOGO` |
| `PolicyStatus` | A row mid-page | `TITLE` | body text |
| `OD330106520353075100` | Invoice number in a dashed box | not text | text |
| `sample9` | Torn-page shadow | `STAMP` | `SEPARATOR` |
| `PublicWaterMassMailing` | Barcodes | `WORD` | `IMAGE` |

---

## What was right

Worth stating plainly, because the list above is all faults:

- **Bordered tables are found reliably**, with their cells — the 43-row packing
  list on `DOC-20250901-WA0021`, the two tables on the challan receipt, the
  nominee and billing tables on `PolicyStatus`, the summary and schedule tables
  on `sample5`.
- **Key-value extraction is strong** on forms: the `Technical Profile` block on
  `sample11`, the whole customer block on `sample6` p10, the challan receipt's
  18 rows.
- **Headers and footers** are correct on essentially every page, including
  scans — the failure that started this work.
- **Panels** correctly wrap boxed regions, and detection runs inside them.
- **Genuine stamps are found**: the round SBI seals on `sample9`.
- **Lists** are correct where items are bulleted rather than numbered.

---

## The structural gap

Separate from the type errors: **borderless tables are still not assembled.**

`Sbizhub` is a bank statement with seven columns. Every heading and every value
is now correctly typed as text — but as *loose sentences*, not as a table with
rows and cells. Same on the `sample5` repayment schedule, where the outer table
is found but no rows are built inside it.

Tracked as F7 and F11 in [backlog.md](backlog.md#phase-f--complete-detection-).

---

## After the fixes

| | Before | After |
|---|---|---|
| Tests | 352 | **354** |
| Coverage (mean of 88 pages) | 0.9943 | 0.9943 |
| Pages below the 0.995 target | 23 | 23 |
| Marks over 6% of a page | 22 | **0** |

**Coverage did not move, and that is the point.** Every defect this audit found
was a *type* error — content was being captured, just described wrongly. The
one number the project had was structurally blind to all of it.

---

## What this says about the tests

Every defect above was present while the suite was green and coverage read
0.9943. That is not a gap in the tests so much as a gap in what they could see:

- the suite proves **consistency** — the same input gives the same answer, and
  digital and scanned agree;
- coverage proves **completeness** — little is being dropped;
- **nothing measured whether the answer was right**, because that needs someone
  to have written down what the right answer is.

Each fixed defect is now a permanent test, built from the values measured on
the real page rather than from a drawing. But the general point stands and is
the argument for backlog H1: until pages are labelled, accuracy is unmeasured,
and reading the pictures is the only check available.
