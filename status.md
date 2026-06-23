# Piply OPDF - Status

## Current Goal
Evolve the platform from a standard OCR pipeline into a Self-Learning Document Intelligence Framework based on the 5-Layer Knowledge First Strategy. Create the interface-driven, modular architecture where features can be developed independently without breaking stable logic.

## Active Tasks
- `[x]` Establish the foundational Vision and Documentation (Wiki & AI contexts).
- `[x]` Clean up old monolithic tests, scratch scripts, and legacy documentation from the root directory.
- `[x]` Build the Base Interfaces (`ILayoutDetector`, `IKnowledgeMatcher`, etc.) following SOLID principles in `piply_opdf/core/`.
- `[x]` Create placeholders for the 15 Core Modules inside `piply_opdf/modules/`.
- `[ ]` Migrate existing Document execution logic into the `DocumentProcessor` and `LayoutExtractor` modules.
- `[ ]` Begin development on **Level 2: Similarity Learning** and **Feature Extraction**.

## Known Issues / Blockers
- None. Stable Table & Borderless Table extraction remains active and unchanged while new modules are structured around them.

## Recent Changes
- Overhauled the architecture plan to introduce the 5-Layer Knowledge Strategy, Human Feedback loops, and strict OOP Module separation.
- Purged outdated debug scripts from the root directory to maintain a clean structure.
