# Getting to Maximum Accuracy

Two ideas were put forward: **treat the page as an image and look at it like a
person does**, and **use surrounding context to repair words OCR cannot read**.

The first is already the architecture. The second is right for prose and
**dangerous for the documents you actually process** — and that distinction is
the most important thing in this document.

---

## 1. Native vision processing — you already have this

The idea: treat each page as an image, and see layout, fonts, spacing and
graphics the way a person does.

This is what the library already does. Every detector is built on the raster:

- The page is rendered to an image at 300 DPI and **all** measurements come
  from pixels — ink density, stroke width, baseline alignment, colour clusters,
  connected components.
- The PDF text layer is treated as an *optimisation*, not the source of truth.
  When a page has one, a text strategy runs; when it does not, a computer
  vision strategy takes over automatically. Digital and scanned pages go through
  the same detectors and are asserted to produce the same answer.
- Spatial relationships are already first-class: panels contain components,
  tables contain rows contain cells, and detection re-runs *inside* a container.

So the foundation matches the mental model. What it does **not** have is a
single model that reasons about layout and text together.

### What a vision-language model would add, and what it would cost

| | |
|---|---|
| **Would add** | Joint reasoning over picture and words: "this number is under the *Debit* heading, therefore it is a debit" |
| **Costs — offline** | Rules out every hosted model. Your rule is no network at inference |
| **Costs — weight** | A useful local multimodal model is gigabytes of weights and wants a GPU. Your rules say CPU only and "make my library maximum light" |
| **Costs — trust** | It generates. See section 2 |

A local VLM is not impossible, but it contradicts three stated constraints at
once. Before spending that, the cheaper wins in section 3 are worth more —
several of them use data you are already collecting and throwing away.

---

## 2. Context-aware OCR — right idea, wrong documents

The idea: if a word is smudged, use the surrounding sentence to work out what
it must be.

**For prose this is genuinely powerful.** "The quick brown f?x" is obviously
"fox", and a language model gets that right nearly always.

**For your documents it is a serious risk.** Look at what is actually on the
pages in your corpus:

```
AOKPN4722Q          a PAN number
CPAFUMVDG6          a bank reference
TT18338ZVNM         a transaction reference
0000662635492305    an account number
₹ 57,550.00         an amount
SBIN0014319         an IFSC code
```

**None of these has context.** They are random strings by design. A language
model asked to "predict what the word should be" has nothing to reason from,
so it produces something that *looks* like a PAN number and is confidently
wrong. On a tax challan or a bank statement, a plausible wrong account number is
far worse than a blank marked "needs a human" — because nobody will catch it.

This is not a hypothetical objection. It is your own rule:

> "i don't want any lose/poor functionality... no haluccination"

and the design rule already written into the system: *no component carries text
that was not read from a real source* — `text_layer`, `ocr`, `knowledge` or
`human`, never inferred.

### The safe form of the same idea: constrain, do not generate

Context should be used to **check** a reading, never to invent one:

| Field | Constraint | On failure |
|---|---|---|
| PAN | `[A-Z]{5}[0-9]{4}[A-Z]` | flag, do not correct |
| IFSC | `[A-Z]{4}0[A-Z0-9]{6}` | flag |
| Date | must parse as a real date | flag |
| Amount column | rows must sum to the stated total | flag the row that breaks it |
| Any field | matches the pattern this key held on previous documents | flag |

This gets most of the benefit — a smudged `0` read as `8` in an amount column
is caught because the column no longer adds up — **and it cannot hallucinate**,
because it never writes a value. It only ever says "this looks wrong, a person
should look".

The sum check is the strongest one available and needs no model at all.

---

## 3. What actually gets maximum accuracy here

Ranked by accuracy gained per unit of effort, using evidence from your own
system.

### a. The knowledge base already beats OCR — feed it properly

Look at the OCR Review screen on `sample.pdf` today. Every cell reads:

```
CONFIDENCE   100% · KB match
```

Those values did not come from OCR. They came from matching the cell image
against something a person already verified. **That is a 100% accurate path,
and it gets better every time somebody reviews a document.** You have 1,656
entries, 747 of them human-verified.

Two things are holding it back, both fixable without any new library:

1. **Only the hashes are used for matching.** Every entry also stores HOG
   features, Hu moments, colour histograms and projection profiles — all 1,656
   rows populated — and the matcher looks at `phash` and `dhash` only. pHash is
   one 64-bit signature and is brittle to scale and small rotation. The richer
   features are collected and ignored.
2. **`component_type` is set on 107 of 1,656 entries.** A model trained per
   type today sees 6% of the data.

This is the highest-value work available, and it compounds.

### b. Two images, two purposes — stop preprocessing for both

The "before and after preprocessing" picture is right about OCR and wrong about
layout, and I have the measurements.

Preprocessing sharpens and thresholds to make glyphs legible. In doing so it
thins the hairline rules that table detection depends on. Measured on
`sample.pdf`:

| Rotation applied | Tables found — original | Tables found — enhanced |
|---|---|---|
| 0.00° | 1 | 1 |
| 0.05° | 1 | **0** |
| 2.00° | 1 | **0** |

The original page survives a two-degree rotation. The cleaned page dies at
one-twentieth of a degree. Preprocessing made the page better for OCR and so
fragile for layout that it lost a 171-cell table.

**Run layout detection on the original raster and OCR on the cleaned one.** They
want opposite things from the image. This is a small change and removes a whole
class of failure.

### c. Read the smallest unit, never the page

You already crop each cell and OCR it on its own. This is the real
"layout-aware" advantage and it is worth stating plainly: a cell carries
constraints a page does not. `Debit` column, row 4 — the answer is a number.
Feeding a whole page to an OCR engine throws that away.

Keep doing this, and extend it: pass the *expected shape* of a field to the OCR
call where it is known (digits only, uppercase only), which most engines accept
and which measurably cuts errors.

### d. A second engine, but only where it earns its cost

**Correction to an earlier version of this document.** It said "you already have
PaddleOCR and Tesseract installed". That was wrong. Checked:

| | State |
|---|---|
| `paddlepaddle` | installed (3.3.1) |
| `paddleocr` | **not installed** — an optional extra |
| `pytesseract` | installed |
| `tesseract` binary | **not installed** |

So **neither OCR engine can run today**. That has to be fixed before anything
here is meaningful.

Once one works, a second engine is still valuable — but **not on every region**.
Running two everywhere doubles the slowest stage in the pipeline for pages that
were never in doubt.

Run the second engine only where it pays:

| Situation | Second engine? |
|---|---|
| Knowledge base returned an exact match | **No** — already verified |
| First engine confident and the value passes its field constraint | **No** |
| First engine below the confidence band | **Yes** |
| Value fails a constraint (a date that will not parse, a column that will not sum) | **Yes** |
| Field marked high-stakes — amounts, identifiers | **Yes** |

Agreement between two engines is then strong evidence on exactly the regions
where evidence was missing, and costs nothing on the ones already settled. It turns "the rule said
0.70" into "two independent readers agreed", which is real evidence.

### e. Then calibrate confidence

Covered in [scanned-documents.md](scanned-documents.md), and it stays the
biggest blocker: confidence values are literals written into the code, so
"review everything under 95%" currently selects **everything**. Engine
agreement (d) and human agreement rates give you the numbers to replace them.

---

## The order

1. **Layout on the original, OCR on the cleaned image** — small, removes a
   whole class of fragility.
2. **Two engines, compare, route disagreements** — free calibrated confidence
   from software you already have.
3. **Use the features already stored in the knowledge base**, and backfill
   `component_type`.
4. **Constraint checks per field type** — regex, date parsing, column sums.
   Catches real errors and cannot invent.
5. **Calibrate confidence** from the agreement data (2) and (3) produce.
6. *Only then* consider a local vision-language model — by which point you will
   have the labelled data to prove whether it actually beats what you have.

---

## The short answer

**Maximum accuracy here does not come from a bigger model.** It comes from
never reading the same thing twice — the knowledge base — from letting two
readers check each other, from not destroying the page before you look at it,
and from checking answers against constraints rather than guessing them.

A vision-language model is a real option later. Today it would break three of
your constraints, and the work above would beat it on the documents you have.
