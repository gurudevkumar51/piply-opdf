# Overview

## Goal

**A bad or scanned PDF becomes a perfectly readable, parsable HTML page.**

Piply OPDF is an offline, CPU-friendly document intelligence framework. It
understands layout, learns from human corrections, and reconstructs documents —
minimising OCR dependency through knowledge reuse.

## The pipeline

| # | Step | Status |
|---|------|--------|
| 1 | Upload document or image | ✅ |
| 2 | Assess, enhance only if needed | ✅ per page, and discarded if it harms structure |
| 3 | Detect layout components | ✅ rules, plus an optional trained model |
| 4 | Correct skew | ✅ |
| 4b | Notice a sideways page | 🟡 detected and flagged; direction needs a person |
| 5 | Split into smallest units | 🟡 table path outside the contract |
| 6 | Complete manifest | ❌ discards titles, lists, graphics |
| 7 | OCR each unit | 🟡 units not persisted |
| 8 | Human verification | ✅ |
| 9 | Confidence routing, hash match before OCR | ✅ |
| 10 | ML prediction | ❌ stub |
| 11 | Character-level correction | ❌ |
| — | HTML reconstruction | ❌ |

Full detail: [capabilities.md](capabilities.md). Plan: [backlog.md](backlog.md).

## Two stages

Detection asks *where are the regions*. Segmentation asks *what are the
smallest units*. Keeping them apart lets one detector serve both digital and
scanned input, and lets us change how finely things are split without touching detection.

See [architecture.md](architecture.md).

## Component vocabulary

Containers (`PANEL`, `TABLE`, `BORDERLESS_TABLE`), textual types
(`TITLE`, `HEADER`, `FOOTER`, `PARAGRAPH`, `SENTENCE`, `LIST_ITEM`,
`KEY_VALUE`, `CELL`, `WORD`), graphic types (`SIGNATURE`, `HANDWRITING`,
`STAMP`, `LOGO`, `IMAGE`) and `UNKNOWN`.

Boundaries between look-alike types are **defined, not inferred**:
cell count separates table from panel, colour count separates stamp from logo,
word-group count separates signature from handwriting.

See [components.md](components.md).

## Nothing is lost

A residual sweep runs last with every prior detection as exclusions. Whatever
ink remains — a photograph, a diagram, a stamp, a torn edge — is captured. What
cannot be classified becomes `UNKNOWN` rather than being discarded or
force-fitted, so a page never silently loses content.

## Constraints

Offline · CPU-only · classical mathematics over heavy libraries · thresholds as
ratios rather than pixels · under-claim rather than over-claim.

## Long-term direction

From an OCR system to a self-learning document intelligence platform that
improves through knowledge reuse, similarity detection, human feedback and
lightweight ML — while keeping every constraint above.
