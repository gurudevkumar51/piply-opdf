# Detection Quality — Targets, Measurement and Limits

The requirement is *"100% perfect layout detection, no hallucination, no poor
functionality"*. This document takes it seriously by splitting it into parts
that can be guaranteed absolutely, parts that can only be measured, and the
residue — because a target that cannot be verified is not a target.

---

## The three claims

| Claim | Achievable? | Enforced by |
|-------|-------------|-------------|
| **Nothing is lost** | ✅ absolutely | Residual sweep + `ink_accounted` measured per page (0.9945 mean, 23/88 pages below target) |
| **Nothing is fabricated** | ✅ absolutely | Structural — text only from text layer, OCR, knowledge, human |
| **Every component correctly typed** | ⚠️ near, not absolute | Definitional rules + measured precision/recall |

The first two are invariants: they hold by construction and a test proves it.

The third has improved substantially. It was previously unbounded, because the
boundaries between similar types were treated as something to infer from
pixels. They are now **defined** — see
[components.md](components.md#decision-rules):

| Pair | Rule |
|------|------|
| Table vs Panel | ≥2 cells → table; 1 cell → panel |
| Stamp vs Logo | 1 colour → stamp; 2+ → logo |
| Signature vs Handwriting | 1–2 word-groups → signature; 3+ → handwriting |

Each is decidable from a measurement, not a judgement. What remains is not
*definitional* ambiguity but **measurement error** — miscounting word-groups on
a blurred signature, colour bleeding in a JPEG-compressed stamp, a faint rule
missed inside a frame. That is a far better problem: it is bounded by scan
quality, it degrades predictably, and it is measurable.

So the honest target is **very high accuracy on legible input, degrading
predictably with scan quality** — not a guarantee of correctness on every
input, which no system can offer.

---

## Guarantees

### 1. Total capture

> Every connected region of ink belongs to exactly one leaf component.

Measured as `coverage.ink_accounted` per page; target **≥ 0.995**, the
remainder being speckle below the noise floor.

**Implemented** in `piply_opdf/quality/coverage.py` and measured on the real
corpus — see [Where ink is being lost](#where-ink-is-being-lost). It does not
fail the build yet; gating it today would freeze the current losses in place
rather than fix them (backlog H4).

### 2. No fabrication

> No component carries text that was not read from a real source.

`text_source` is mandatory and must be `text_layer`, `ocr`, `knowledge` or
`human`. No code path synthesises or infers text. Unreadable content stays
empty with `needs_ocr: true`.

### 3. Measured classification accuracy

Per type, against a labelled corpus. Provisional until the corpus exists; the
point is that each becomes a number in CI rather than an opinion.

| Type | Precision | Recall |
|------|-----------|--------|
| `TABLE` | ≥ 0.98 | ≥ 0.96 |
| `PANEL` | ≥ 0.97 | ≥ 0.95 |
| `HEADER` / `FOOTER` | ≥ 0.97 | ≥ 0.95 |
| `KEY_VALUE` | ≥ 0.95 | ≥ 0.92 |
| `PARAGRAPH` / `SENTENCE` | ≥ 0.95 | ≥ 0.95 |
| `LIST_ITEM` | ≥ 0.93 | ≥ 0.90 |
| `TITLE` | ≥ 0.92 | ≥ 0.90 |
| `SIGNATURE` | ≥ 0.90 | ≥ 0.88 |
| `HANDWRITING` | ≥ 0.90 | ≥ 0.92 |
| `STAMP` / `LOGO` | ≥ 0.90 | ≥ 0.88 |
| `UNKNOWN` | *(safety net — no target)* | |

Targets for table/panel and stamp/logo are higher than they would have been
before the decision rules, because those boundaries are now definitional.

`HANDWRITING` recall exceeds its precision deliberately: the agreed fallback
sends uncertain pen strokes to handwriting, so it absorbs ambiguity by design.

**Precision is prioritised over recall throughout.** A missed component becomes
`UNKNOWN` and a human sees it. A mistyped component is parsed with the wrong
rules and propagates silently into the manifest and the HTML. Under-claiming is
recoverable; over-claiming is not.

### 4. No silent regression

Every metric asserted in CI. A change improving paragraphs while degrading
tables fails the build rather than surfacing on a customer document.

---

## Ground-truth corpus

Accuracy claims need labelled data.

```
tests/corpus/
├── synthetic/     generated in-process — exact labels by construction
├── real/
│   ├── scans/     real scanned documents
│   └── labels/    hand-labelled boxes and types
└── regression/    documents that previously exposed a bug
```

**Synthetic** gives exact labels, unlimited volume, and control over page size,
DPI, skew and layout. It cannot reproduce real scanner artefacts.

**Real** covers what synthetic cannot: bleed-through, uneven lighting, staples,
genuine handwriting, compression artefacts. Labelling is manual, so it stays
small and targeted.

**Regression** is the highest-value set. Every bug found on a real document —
`sample10` page 1's PAN card read as a table, page 4's form block read as a
paragraph — becomes permanent. These are the cases known to be hard *for this
system specifically*.

---

## Where ink is being lost

> Coverage answers *"was anything lost?"*. For whether the answer was
> **right**, see [audit.md](audit.md) — reading every sample page against
> what the system produced found nine defects that coverage could not see.

Coverage is the one quality number available without anyone labelling
documents by hand, so it is the first real measurement this system has.

Run over the 16 sample documents (88 pages) with `tools/check_coverage.py`:

| | |
|---|---|
| mean coverage | **0.9945** |
| worst page | **0.9477** — `sample10.pdf` page 21 |
| pages meeting the 0.995 target | 65 / 88 |
| pages below target | **23 / 88** |

The mean clears the target; individual pages do not. The ten worst:

| Coverage | Page |
|---|---|
| 0.9477 | sample10.pdf p21 |
| 0.9539 | Sbizhub_C2219080509040.pdf p1 |
| 0.9621 | sample10.pdf p19 |
| 0.9708 | sample10.pdf p23 |
| 0.9735 | Sbizhub_C2219080509040.pdf p2 |
| 0.9751 | sample10.pdf p20 |
| 0.9821 | Moda.pdf p27 |
| 0.9833 | Moda.pdf p19 |
| 0.9836 | sample10.pdf p22 |
| 0.9837 | Moda.pdf p3 |

**The failures cluster rather than spread.** Three documents account for the
whole top ten, and `sample10.pdf` alone holds five. That is the useful finding:
this is a handful of specific problems, not a general weakness. A loss spread
thinly over all 88 pages would mean the detectors were broadly leaky; losses
concentrated on a few pages of a few documents means a few layouts are being
missed and can be found and fixed one at a time.

The largest unclaimed regions point straight at them — for example
`(1253, 2779, 1139×256)` on sample10 page 19 is a wide, short block, the shape
of a table row or a footer band that nothing claimed.

Two things this number cannot tell you:

- **It does not check the type.** A paragraph confidently mislabelled a table
  still counts as fully covered. Coverage answers "was anything lost?", never
  "was it read correctly?" — that needs H1/H2.
- **It does not check reading order or text.** A page can score 1.0000 with
  every component in the wrong sequence.

---

## Current state

Detection is verified by **482 tests**, but almost entirely on synthetic
corpora, asserting *behaviour* rather than *accuracy*:

- ✅ digital and scanned twins produce identical output
- ✅ behaviour stable across page sizes and 150–600 DPI
- ✅ specific past failures do not recur
- ✅ `ink_accounted` computed per page and measured on real documents
- ✅ 16 real documents (88 pages) process end to end without error
- 🔄 precision/recall harness written, but no labels to run it against
- ❌ no hand-labelled ground truth, so **accuracy is still unmeasured**

**Detection is well-tested for consistency, and now measured for completeness —
but still unmeasured for accuracy.** Coverage proves little is being dropped; it
proves nothing about whether what was kept was understood. Until labelled pages
exist, any claim about accuracy on real documents — including a favourable one —
remains unsupported.

---

## On "no poor functionality"

A feature is complete and verified, or it is marked ❌. The failure mode to
avoid is a half-working feature presented as working — `borderless_table`
returns results on digital PDFs and silently nothing on scans, so it is listed
❌ rather than ✅-with-caveats.

Genuine limits are documented at the point of use, not hidden: the classifier's
synthetic calibration, the cursive character-segmentation caveat, and
[capabilities.md](capabilities.md#known-limits).
