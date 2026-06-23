# Project Roadmap

The Piply OPDF roadmap is focused on the transition from a traditional "OCR System" into a "Self-Learning Document Intelligence Platform".

## Phase 1: Core Layout & Baseline OCR ✅
- Develop `piply_opdf` core package for extracting Tables, Title, Key value pair, Paragraphs, Headers, and Footers.
- Build the web interface (FastAPI + Vanilla JS/HTML).
- Integrate Level 1 (Exact Match) Knowledge Base and Level 4 (PaddleOCR) fallback.
- Implement Level 5 (Human Review) bulk review and feedback looping.
- Develop the layout reconstruction and comparison engine.

## Phase 2: Similarity Learning (Level 2) 🟡 *Next*
- Integrate feature extraction pipelines (pHash, dHash, aHash, Edge Density, Histogram Similarity).
- Build the `Similarity Engine` module to resolve slightly degraded or translated matches without falling back to OCR.
- Expand the Knowledge Base schema to store image features.

## Phase 3: Lightweight ML Prediction (Level 3) 📅
- Aggregate sufficient labeled training data generated via the Human Feedback Loop.
- Train and integrate CPU-friendly, offline ML models (KNN, Random Forest, SVM) into the `ML Prediction Engine` module.
- Fine-tune ML prediction thresholds so it acts as a reliable bridge between similarity matching and raw OCR.

## Phase 4: Granular Segmentation & Optimization 📅
- Refine OCR units (e.g., segmenting Paragraphs into Sentences, then Words) to increase caching granularity and reuse.
- Introduce advanced UI workflows for reviewing smaller segments (like individual words) inside larger blocks.
- Performance profiling and multithreaded processing optimization across all modules.
