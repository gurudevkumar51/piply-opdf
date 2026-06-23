# AI Tasks

## Current priorities

1. Stabilize the detector-oriented layout architecture.
2. Complete the standalone bordered and borderless table detector organization.
3. Keep `Document`, CLI commands, tests, and docs aligned.
4. Strengthen metadata and artifact generation around tables, columns, rows, and cells.
5. Reduce stale or duplicate code paths created during refactoring.

## Active implementation tasks

- establish the intended `piply_opdf/detectors/` structure cleanly
- migrate or consolidate table detection logic into the correct detector modules
- improve borderless table detection using PyMuPDF text blocks plus CV projection logic
- maintain strict P1 -> P2 -> P3 -> P4 processing order
- ensure work-dir outputs remain consistent and inspectable
- close the gap between legacy phase docs and the current runtime API

## Quality tasks

- add coverage for the current `process_layout()` path
- review legacy tests that reference missing source modules
- remove ambiguity around supported CLI commands

## Longer-term tasks

- confidence analysis
- doubt detection
- knowledge learning
- lightweight ML assistance
- document rebuilding
