# Piply OPDF Deployment

## Local development setup

Recommended environment:

```bash
conda create -n py313_piply_opdf python=3.13 -y
conda activate py313_piply_opdf
pip install -e ".[dev]"
```

Optional extras:

```bash
pip install -e ".[paddle]"
pip install -e ".[tesseract]"
pip install -e ".[api]"
pip install -e ".[all]"
```

## Running the CLI

```bash
piply-opdf version
piply-opdf run sample.pdf
```

## Running the FastAPI app

The API dependencies are optional, so install them first:

```bash
pip install -e ".[api]"
```

Then run:

```bash
uvicorn app.main:app --reload
```

The application serves:

- HTML pages from `app/templates/`
- static assets from `app/static/`
- uploaded files from `uploads/`
- generated output artifacts mounted under `/outputs`

## Database

Current app database setup uses SQLite:

- connection string in `app/database.py`
- default file: `piply_opdf.db`

The web app creates tables on startup through SQLAlchemy metadata.

## Deployment considerations

- Prefer local or small-server deployments first because the project is CPU-oriented.
- Ensure OCR dependencies are installed consistently on the target host.
- If using Tesseract, the system binary must be installed and on `PATH`.
- Output folders can grow quickly because page renders, crops, and debug images are persisted.
- SQLite is fine for local and single-user workflows, but multi-user production deployment will likely need a stronger database and job queue.

## Recommended near-term deployment shape

- CLI for engineering and batch validation
- FastAPI app for review workflows
- local filesystem for artifacts
- SQLite for metadata

This is the most natural fit for the project’s current maturity level.
