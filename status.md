# Piply OPDF - Status

## Current Goal
Implement the modular architecture for layout detection, strictly following the Priority Order. Develop the `BorderlessTableDetector` as a standalone module leveraging PyMuPDF and OpenCV, and test it against `sample5.pdf`.

## Active Tasks
- [x] Create `technical_architecture.md` and `status.md`
- [ ] Establish `detectors/` folder structure (`table_detector`, `borderless_table_detector`, `header_detector`, `footer_detector`).
- [ ] Migrate existing OpenCV-based bordered table detection into `detectors/table_detector/`.
- [ ] Implement `borderless_table_detector` using text blocks (PyMuPDF) and OpenCV projection profiling.
- [ ] Hook up detectors in `document.py` execution pipeline according to P1 -> P2 -> P3 -> P4 priority.
- [ ] Implement CLI commands (`detect-tables`, `detect-borderless-tables`, etc.).

## Known Issues / Blockers
- None at this time.

## Recent Changes
- User reverted the previous monolithic `TableDetector` logic. We are transitioning to a highly independent, metadata-first plugin architecture for each layout component.
