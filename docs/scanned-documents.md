# Scanned Documents — The Goal, and What Stands in the Way

The stated goal, in one line:

> **A scanned PDF becomes a digital, readable document. The system finds every
> layout it can, and wherever it is unsure, a person checks and corrects it.**

This document takes that apart into stages, says honestly where each stage
stands today, and ranks the things blocking it. Every claim here is backed by a
measurement taken on the 16 sample documents, not by an opinion.

---

## The goal as a pipeline

```
   scanned page
        │
   1.   straighten and clean          fix skew, contrast, noise
        │
   2.   find layouts                  table, panel, header, footer,
        │                             paragraph, key-value, list, graphic
   3.   split to smallest units       rows, cells, sentences, words
        │
   4.   read them                     hash match → OCR → ML
        │
   5.   route by confidence           sure → keep, unsure → a person
        │
   6.   person reviews and corrects   the correction becomes truth
        │
   7.   truth to knowledge base       same mark recognised next time
        │
   8.   output                        semantic, searchable HTML
```

Stages 1–3 are the package's job and are what "identify maximum layout" means.
Stages 4–7 are the loop that makes the system improve. Stage 8 is the product.

> **Superseded in part.** This document diagnoses the problems. The plan for
> stages 2 and 3 has since changed: rather than hand-building every generic
> detector, a **trained layout model becomes the baseline** and Piply's rules
> specialise on top of it. See
> [plan-templates.md](plan-templates.md#phase-b--baseline-detector-with-piplys-rules-on-top).

---

## Where each stage stands

| Stage | State | Evidence |
|-------|-------|----------|
| 1. Straighten and clean | 🟡 works, but has fought stage 2 | A 0.20° correction destroyed a 171-cell table |
| 2. Find layouts | 🟡 strong on ruled documents, weak on scans | 9 defects found by reading all 88 pages |
| 3. Split to units | ✅ works | Tables → 171 cells; paragraphs → sentences → words |
| 4. Read them | 🟡 built, unmeasured | OCR engines have **no tests** (H7) |
| 5. Route by confidence | 🔴 **not real triage** | 106 of 106 components flagged "need a look" |
| 6. Human review | ✅ works | Review screen rebuilt; header/footer now reviewable |
| 7. Truth to knowledge | 🟡 flowing, but thin | 747 verified entries; type on only 107 of 1,656 |
| 8. Output | 🟡 preview only | Reconstruct now flows; HTML export not built (D1–D3) |

---

## The challenges, ranked

Ranked by **how much each one blocks the goal**, not by how hard it is.

### 1. Confidence is not a real number 🔴

This is the biggest one, and it sits exactly on the sentence *"wherever
confidence is low, allow the end user to review"*.

Today, confidence is a **fixed number written into the code**. A paragraph is
always 0.70. A logo is always 0.85. A near-tie is always 0.55:

```python
return Classification(ComponentType.PARAGRAPH, 0.70)
return Classification(ComponentType.LOGO, 0.85)
```

Almost every value in the library is a literal like this. Only the paragraph
detector computes anything from the content itself.

**Why it matters:** 0.70 does not mean "right about 70% of the time". It means
"this rule fired". So sorting by confidence does not sort by *how likely it is
to be wrong*, and a threshold does not separate safe from unsafe.

You can see the effect. On `sample11.pdf` the dashboard reports:

```
0 CHECKED    106 TOTAL    106 NEED A LOOK
```

Every single component is below the 95% line, because the rules that fired
happen to be written as 0.70 and 0.88. That is not triage — it is asking a
person to check everything, which is the thing the goal is trying to avoid.

**What closing it needs.** *Revised.* Not "earned" — that is too vague:

> **Confidence must be derived from measurable evidence and calibrated against
> human-labelled results.**

An evidence score, combining detector evidence, geometry evidence, knowledge
agreement, structural evidence, historical reliability and the baseline model's
own score — then **fitted against the labelled corpus** so that 0.90 means right
about 90% of the time. Historical agreement is one input, not the whole answer.

Full design in
[plan-templates.md](plan-templates.md#phase-c--confidence-as-an-evidence-score).

**Difficulty:** medium. **Blocking:** total — without it, stage 5 does not work.

### 2. Borderless tables are never assembled 🔴

Most scanned business documents — bank statements, invoices, remittance advices
— have few or no ruled lines. The system finds their content and now types it
correctly, but never builds it into a table.

`Sbizhub_C2219080509040.pdf` is a seven-column bank statement. After the recent
fixes, every heading and every value is correctly typed as text. But they arrive
as **loose sentences**, not as rows and cells:

```
Book Date | Reference | Description | Value Date | Debit | Credit | Closing Balance
```

…comes back as seven unrelated text blocks. Nothing records that
`43438` belongs under `Debit` on the same row as `TT18338ZVNM`.

**Why it matters:** the whole value of a statement is the relationship between
the columns. Text without that structure is not a digital document, it is a bag
of words. It also breaks stage 7: a cell can be recognised again by its column
name, a floating sentence cannot.

**What closing it needs.** *Revised — the first answer was too simple.* Finding
vertical gaps, then horizontal ones, then cells at the intersections **fails on
exactly these documents**, because a wrapped description looks like new rows:

```
   Date       Description
              continuation of long description
   05/01      Payment                      500
```

Lines two and three are one row, not three. The rebuilt approach runs
continuation analysis before deciding row boundaries, and lets **no single
column be the mandatory row anchor**. Full design in
[plan-templates.md](plan-templates.md#phase-r--borderless-tables-rebuilt-around-continuation).

The existing `BorderlessTableDetector` never builds cells, and on scans finds
nothing at all.

**Difficulty:** medium-high. **Blocking:** high for the document types you care
most about. Tracked as F7 and F11.

### 3. Cleaning the page damages what layout detection needs 🟠

Found this week, and it is an architectural conflict rather than a bug.

Enhancement exists to make text **readable for OCR**. It sharpens and thresholds,
and in doing so it thins the hairline rules that table detection depends on.
Measured on `sample.pdf`:

| Rotation applied | Tables found — original | Tables found — enhanced |
|---|---|---|
| 0.00° | 1 | 1 |
| 0.05° | 1 | **0** |
| 2.00° | 1 | **0** |

The original page survives a 2° rotation. The enhanced page dies at 0.05°. The
enhanced version is so fragile that a rotation too small to help anything
destroys the table.

The immediate trigger is fixed — deskew no longer applies corrections below
0.5°. But the underlying conflict remains: **stage 1 optimises for stage 4 and
harms stage 2.**

**What closing it needs.** *Revised — three images, not two.* The raw original
may itself be rotated, so layout must not read it directly either:

```
   original      immutable source
      ↓ orientation + safe deskew
   structural    layout, tables, fingerprints, geometry read this
      ↓ denoise, contrast, sharpen
   working       OCR reads this
```

Detail in [plan-templates.md](plan-templates.md#three-images).

**Difficulty:** low. **Blocking:** medium — but it is cheap, so it should be
early.

### 4. Nothing measures whether a layout was identified *correctly* 🟠

Coverage — the share of page ink that ended up inside some component — reads
**0.9943** across 88 pages. That sounds like the goal is nearly met. It is not.

Reading all 88 pages by eye found **nine defects**. Coverage before those fixes:
0.9943. After: 0.9943. It did not move, because every defect was a *type* error
— the content was captured, just described wrongly. An entire scanned bank
statement was labelled `HANDWRITING` and coverage was perfectly happy.

**Why it matters:** you cannot aim at "identify maximum layout" without a number
that goes up when you do. Right now the only check is a person looking at
pictures, which does not scale and cannot run in CI.

**What closing it needs.** Hand-labelled pages: a few hundred regions across
5–10 real scans, marked with their true type and box. The scoring harness is
already written and tested — it has never had real data to run on.

**Difficulty:** low technically, but it needs **your time**, not mine.
**Blocking:** high for confidence in any future change.

### 5. Scans break the page in ways not handled yet 🟠

Four specific, measured gaps, all on scanned pages:

| Gap | Evidence | Tracked |
|---|---|---|
| **Rotated text** unreadable as text | The whole vertical margin of `PublicWaterMassMailing` p4 typed as `LOGO`/`STAMP` | F20 |
| **Large display text** unreadable as text | HDFC tagline: 138–215 glyphs/megapixel (under the 400 floor) *and* stroke variation 0.475–0.501 (above handwriting's 0.43) | F21 |
| **Skewed, low-contrast interiors** | `sample10` p21, worst page at 0.9477 — panel found, most question text inside never claimed | F23 |
| **Page orientation** (90/180/270) | Not implemented at all. Only a `rotate_image` utility exists — nothing detects that a page is sideways | A2 |

Orientation is the one that will bite hardest in production: a batch scanner
that feeds one page sideways produces a page where *every* stage fails at once,
and nothing currently notices.

**Difficulty:** mixed — orientation is low, rotated text is medium.
**Blocking:** medium, rising with scan quality variation.

### 6. The verified-truth loop is thin, and unprotected 🟡

Stage 7 is what makes the system get better over time. Two problems:

- **`component_type` is set on only 107 of 1,656 knowledge entries.** The other
  1,549 predate the field and were never backfilled. Any per-type model trained
  now would see 6% of the data.
- **The knowledge base has no backup.** It holds 747 human-verified entries and
  is the one file in this project that cannot be regenerated. Last week the
  application database lost 236 feedback rows with no way to recover them. The
  same could happen to this file.

**What closing it needs.** A backfill pass over the existing entries, and a
scheduled copy of the knowledge database somewhere off the working tree.

**Difficulty:** low. **Blocking:** low now, high later — this is the compounding
asset.

### 7. There is no digital output yet 🟡

Stage 8. The Reconstruct page now lays components out in reading order, which is
a preview. But there is no export that produces a semantic, searchable HTML
document — headings as headings, tables as tables, key-values as definition
lists. Tracked as D1–D3.

**Difficulty:** medium. **Blocking:** it is the deliverable, but it depends on
stages 2 and 3 being right first. Building it now would mean rebuilding it.

---

## The order I would take these

1. **Run layout on the original, OCR on the enhanced** (challenge 3) — cheap,
   removes a whole class of fragility, unblocks everything downstream.
2. **Calibrate confidence from human agreement** (challenge 1) — turns the
   review queue from 100% into something a person can actually work through.
   This is the one that most directly serves the stated goal.
3. **Label 5–10 real scans** (challenge 4) — needs your time; without it every
   later change is unmeasured.
4. **Assemble borderless tables** (challenge 2) — the biggest single win for
   scanned business documents.
5. **Orientation, then rotated and display text** (challenge 5).
6. **Backfill and back up the knowledge base** (challenge 6) — small, and it
   protects the compounding asset.
7. **Semantic HTML export** (challenge 7) — last, once the structure beneath it
   is right.

---

## What I need from you

Only two things, and the first is the important one:

1. **Hand-labelled pages.** 5–10 real scanned documents with each region marked
   with its true type and box. This is the only thing that turns "I think
   detection improved" into a number. The format is documented in
   [quality.md](quality.md) and the harness already exists.

2. **A decision on the knowledge base backup.** It is 45 MB, tracked in git, and
   holds the only copy of 747 human verifications. Git is a poor home for it and
   there is no other copy.

---

## What this does not say

This document ranks what is in the way. It does not claim the goal is far off —
stages 3, 6 and much of 2 already work, and the failures found by reading the
pages were mostly type errors on content that had been correctly located.

But it also does not claim the goal is close. The honest summary is: **the
system finds content reliably and describes it unreliably, and it has no way to
tell the difference.** Challenges 1 and 4 are both about closing that gap — one
by making confidence mean something, the other by measuring correctness at all.
Neither needs a new library or a bigger model. Both need the loop that is
already half-built to be closed.
