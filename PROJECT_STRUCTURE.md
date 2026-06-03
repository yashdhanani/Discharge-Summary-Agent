# Project Structure

This repository contains a local clinical AI agent that reads patient source-note PDFs and generates a safe, structured discharge-summary draft with traceable evidence, quality metrics, and clinician-review flags.

## Folder Layout

```text
Discharge-Summary-Agent/
|-- README.md
|-- PROJECT_STRUCTURE.md
|-- pyproject.toml
|-- requirements.txt
|-- task/
|   `-- patient_source_notes.pdf
|-- sample_patients/
|   |-- patient-a-clean/
|   |   |-- source_notes.txt
|   |   `-- source_notes.pdf
|   `-- patient-b-conflict-pending/
|       |-- source_notes.txt
|       `-- source_notes.pdf
|-- src/
|   `-- dscribe_agent/
|       |-- __init__.py
|       |-- agent.py
|       |-- cli.py
|       |-- extractors.py
|       |-- learning.py
|       |-- models.py
|       |-- pdf_ingest.py
|       |-- reporting.py
|       |-- tools.py
|       `-- web_app.py
|-- scripts/
|   |-- build_static_site.py
|   |-- make_synthetic_patients.py
|   `-- validate_project.py
|-- tests/
|   `-- test_agent_safety.py
|-- web/
|   |-- index.html
|   |-- app.js
|   |-- styles.css
|   `-- favicon.svg
|-- docs/
|   |-- index.html
|   |-- app.js
|   |-- styles.css
|   |-- favicon.svg
|   `-- data/
|-- outputs/
|-- outputs_samples/
`-- ocr_cache/
```

## Core Package

### `src/dscribe_agent/models.py`

Defines shared typed data structures:

- `Evidence`
- `Field`
- `Medication`
- `DocumentPage`
- `AgentState`

### `src/dscribe_agent/pdf_ingest.py`

Discovers PDFs and extracts page-level text.

Key behavior:

- Accepts a single PDF or a folder of PDFs.
- Uses `pypdf` for native text extraction.
- Detects sparse scanned PDFs.
- Reads from `ocr_cache/` when available.
- Falls back to local macOS Vision OCR when available.
- Handles corrupted, encrypted, empty, and unreadable PDFs safely.

### `src/dscribe_agent/extractors.py`

Contains deterministic extraction logic for:

- patient demographics
- admission and discharge dates
- principal and secondary diagnoses
- hospital course
- procedures
- allergies
- pending results
- follow-up instructions
- discharge condition
- admission/inpatient medications
- discharge medications
- medication reconciliation
- conflict detection

### `src/dscribe_agent/tools.py`

Contains mocked external-style tools:

- medication safety lookup
- clinician-review flag formatter

The tool layer keeps safety checks explicit without requiring external credentials.

### `src/dscribe_agent/agent.py`

Runs the bounded state-driven agent loop.

Agent actions:

1. `ingest_pdfs`
2. `extract_summary_fields`
3. `extract_pending_results`
4. `extract_medications`
5. `reconcile_medications`
6. `detect_conflicts`
7. `run_safety_tools`
8. `validate_no_fabrication`
9. `render_draft`

Each step records:

- reasoning
- tool/action
- inputs
- result
- next decision

### `src/dscribe_agent/reporting.py`

Builds machine-readable and human-readable reports:

- `structured_summary.json`
- `quality_report.json`
- `quality_report.md`

### `src/dscribe_agent/learning.py`

Generates a simulated edit-learning report. The learner compares rendering strategies using normalized edit burden and keeps learning isolated from clinical fact extraction.

### `src/dscribe_agent/cli.py`

Command-line interface for single-patient and batch processing.

### `src/dscribe_agent/web_app.py`

Local backend and static file server for the dashboard.

Endpoints:

```text
GET  /api/health
GET  /api/runs
GET  /api/artifact?run_id=<id>&artifact=<artifact>
POST /api/run
```

## Frontend

### `web/`

Local dashboard served by `web_app.py`.

Main views:

- run list
- summary metrics
- draft
- trace
- quality report
- learning report
- structured JSON

### `docs/`

Static GitHub Pages review dashboard generated from the latest output artifacts.

Live URL:

```text
https://yashdhanani.github.io/Discharge-Summary-Agent/
```

## Data And Outputs

### `task/`

Contains the provided patient source-note PDF.

### `sample_patients/`

Contains two synthetic sample patients:

- `patient-a-clean`
- `patient-b-conflict-pending`

### `outputs/`

Generated artifacts for the provided patient.

### `outputs_samples/`

Generated artifacts for the sample patient batch.

### `ocr_cache/`

Retained OCR text cache for reproducible reruns and scanned-PDF fallback.

## Validation

Run:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_project.py
```

The validation checks:

- required output artifacts exist
- trace steps are complete
- quality reports are valid
- structured summaries preserve evidence
- medication rows include evidence
- learning metrics improve edit burden
- dashboard assets exist

## Safety Design

- Supported facts require evidence.
- Missing values remain explicit.
- Uncertain fields are marked for clinician review.
- Medication reconciliation does not hide unclear changes.
- Conflicts are surfaced.
- OCR/tool failures are visible in review flags.
- The rendered document remains a clinician-review draft.
