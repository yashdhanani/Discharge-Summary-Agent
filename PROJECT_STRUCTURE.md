# Project Structure And Technical Walkthrough

This project is a safe local discharge-summary agent for the Dscribe AI Engineer take-home assignment. It reads synthetic clinical source-note PDFs, extracts only evidence-backed facts, flags missing or uncertain information, reconciles medications, detects conflicts, and produces a clinician-review draft plus traceable quality artifacts.

## High-Level Goal

Build an agentic AI system that turns messy clinical source notes into a structured discharge summary without fabricating unsupported clinical facts.

The project covers:

- Part 1 required agent: PDF ingestion, bounded agent loop, tool use, trace logging, missing-data handling, medication reconciliation, conflict detection, and no-fabrication checks.
- Part 2 optional stretch: simulated doctor edits, edit-distance reward, epsilon-greedy strategy selection, and before/after learning metrics.
- Full local web dashboard: frontend plus backend for viewing generated draft, trace, quality report, learning metrics, and structured JSON.
- GitHub Pages review dashboard: static live view of the generated artifacts for direct repo-based review.

## Folder Layout

```text
home assignment/
|-- README.md
|-- PROJECT_STRUCTURE.md
|-- SUBMISSION_CHECKLIST.md
|-- DEMO_AND_INTERVIEW_GUIDE.md
|-- pyproject.toml
|-- requirements.txt
|-- task/
|   |-- assignment_brief.pdf
|   |-- gmail_next_steps.pdf
|   `-- patient_source_notes.pdf
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
|-- web/
|   |-- index.html
|   |-- styles.css
|   |-- app.js
|   `-- favicon.svg
|-- docs/
|   |-- index.html
|   |-- styles.css
|   |-- app.js
|   |-- favicon.svg
|   `-- data/
|-- .github/
|   `-- workflows/
|       `-- pages.yml
|-- demo_patients/
|   |-- patient-a-clean/
|   |   |-- source_notes.txt
|   |   `-- source_notes.pdf
|   `-- patient-b-conflict-pending/
|       |-- source_notes.txt
|       `-- source_notes.pdf
|-- scripts/
|   |-- make_synthetic_patients.py
|   |-- build_static_site.py
|   `-- validate_submission.py
|-- tests/
|   `-- test_agent_safety.py
|-- outputs/
|-- outputs_demo/
`-- ocr_cache/
```

## Core Python Package

### `src/dscribe_agent/models.py`

Defines the typed state model used across the project.

- `Evidence`: source PDF name, page number, and source snippet.
- `Field`: extracted clinical field with value, status, evidence, and review flags.
- `Medication`: medication entity with dose, frequency, duration, source, evidence, and flags.
- `DocumentPage`: page-level extracted text.
- `AgentState`: shared state passed through the agent loop.

This file is intentionally small because every other module depends on these stable data structures.

### `src/dscribe_agent/pdf_ingest.py`

Handles patient PDF discovery and text extraction.

Responsibilities:

- Finds patient PDFs from a file or folder.
- Ignores assignment/gmail PDFs only when scanning the built-in `task/` folder.
- Extracts native PDF text with `pypdf`.
- Detects sparse scanned PDFs.
- Uses cached OCR from `ocr_cache/` when available.
- Falls back to local macOS Vision OCR when needed.
- Handles corrupted, encrypted, empty, and unreadable PDFs by escalating warnings instead of crashing.
- Emits warnings instead of failing silently.

Safety point: if OCR is sparse or unavailable, that becomes a clinician-review flag downstream.

### `src/dscribe_agent/extractors.py`

Contains deterministic clinical extraction logic.

Main extraction functions:

- `extract_summary_fields`: required discharge-summary sections.
- `extract_pending_results`: pending or missing results.
- `extract_discharge_meds`: discharge medication list.
- `extract_admission_meds`: admission or inpatient medication list.
- `reconcile_medications`: additions, missing source values, unclear changes.
- `detect_conflicts`: conflicting diagnosis/result statements.

This module is conservative by design. It returns `MISSING`, `uncertain`, or review flags when source text is unclear.

### `src/dscribe_agent/tools.py`

Contains mocked external-style tools.

- `drug_interaction_lookup`: simulated medication safety lookup.
- `flag_for_clinician_review`: standardizes review-flag messages.

Why mocked tools are useful here: the assignment requires tool use and safety handling, but real clinical drug APIs would add credentials, cost, and external dependency risk.

### `src/dscribe_agent/agent.py`

The main bounded, state-driven agent loop.

Possible actions:

1. `ingest_pdfs`
2. `extract_summary_fields`
3. `extract_pending_results`
4. `extract_medications`
5. `reconcile_medications`
6. `detect_conflicts`
7. `run_safety_tools`
8. `validate_no_fabrication`
9. `render_draft`

Important behavior:

- Uses an explicit step cap via `max_steps`.
- Chooses the next action by inspecting `AgentState` and the set of completed actions.
- Records reasoning, action, inputs, result, and next decision for every step.
- Catches tool/action failures and escalates them.
- Continues safely after sparse/unreadable source text by producing missing-field review output.
- Calls medication safety tools only when discharge medications are present.
- Downgrades unsupported "supported" fields in the no-fabrication guardrail.
- Renders the final markdown draft from state, not from free-form guessing.

### `src/dscribe_agent/reporting.py`

Builds submission-ready output artifacts.

Generated reports:

- `quality_report.json`
- `quality_report.md`
- `structured_summary.json`

Quality metrics include:

- pages read
- extracted character count
- agent steps
- step-cap status
- required-field coverage
- evidence coverage
- medication counts
- reconciliation alerts
- pending results
- conflicts
- clinician review flags

### `src/dscribe_agent/learning.py`

Implements Part 2 optional stretch.

Flow:

1. Generate a draft.
2. Simulate doctor edits.
3. Measure edit burden using normalized string similarity.
4. Compare rendering strategies.
5. Use epsilon-greedy selection.
6. Save before/after metrics in `learning_metrics.json`.

Important safety design: learning changes presentation style only. It does not change extracted facts, evidence, diagnoses, medications, or safety flags.

The learning system is intentionally isolated from clinical fact extraction. It only changes rendering strategy and presentation style. Clinical facts, evidence extraction, medication reconciliation, and safety checks remain deterministic and unaffected.

### `src/dscribe_agent/cli.py`

Command-line entry point.

Supports:

- single patient run
- batch demo run
- hard step limit
- optional learning demo
- output artifact generation

Main commands:

```bash
PYTHONPATH=src python -m dscribe_agent.cli --input task --output outputs --learning-demo
PYTHONPATH=src python -m dscribe_agent.cli --input demo_patients --output outputs_demo --batch --learning-demo
```

### `src/dscribe_agent/web_app.py`

Local backend server for the dashboard.

Responsibilities:

- Serves files from `web/`.
- Exposes run metadata.
- Exposes safe artifact reads.
- Triggers provided-patient and demo-batch runs.
- Prevents arbitrary artifact file access by using an allowlist.

API endpoints:

```text
GET  /api/health
GET  /api/runs
GET  /api/artifact?run_id=<id>&artifact=<artifact>
POST /api/run
```

`POST /api/run` supports `task` for the provided assignment patient and `demo` for the synthetic demo batch.

Allowed artifact names:

- `draft`
- `trace`
- `quality`
- `quality_md`
- `structured`
- `learning`
- `state`

## Web Frontend

### `web/index.html`

Defines the dashboard shell:

- top action bar
- run list sidebar
- summary metrics
- artifact tabs
- content area
- toast notifications

## GitHub Pages Frontend

### `docs/index.html`

Static live-review dashboard deployed from GitHub Pages at:

```text
https://yashdhanani.github.io/Discharge-Summary-Agent/
```

It renders the generated artifacts in `docs/data/` so reviewers can inspect the draft, trace, quality report, learning metrics, and structured JSON directly from the repository URL.

### `scripts/build_static_site.py`

Builds the static Pages data bundle from `outputs/` and `outputs_demo/`.

The Pages dashboard is intentionally read-only. It does not replace the local backend; processing a new PDF still uses the CLI or `src/dscribe_agent/web_app.py`.

### `web/styles.css`

Production-style responsive UI.

Key details:

- desktop two-column layout
- mobile single-column layout
- stable metrics grid
- wrapped trace cards
- scroll-safe JSON/code blocks
- accessible tab states
- no horizontal overflow after audit fixes

### `web/app.js`

Frontend behavior.

Responsibilities:

- Calls backend APIs.
- Renders run list.
- Switches tabs.
- Renders markdown draft.
- Renders trace steps.
- Renders quality report cards.
- Draws the learning curve canvas.
- Renders structured JSON.
- Handles run buttons and refresh.

## Input Data

### `task/`

Contains:

- Gmail instruction PDF.
- Assignment brief PDF.
- Provided synthetic patient source-note PDF.

The ingestion layer filters out assignment/gmail PDFs so the agent runs on patient source notes.

### `demo_patients/`

Contains two synthetic patients:

- `patient-a-clean`: cleaner case with fewer flags.
- `patient-b-conflict-pending`: case with conflicts and pending-result issues.

These are useful for walkthrough videos because they show the system handling both normal and risky cases.

## Output Artifacts

### `outputs/`

Generated from the provided patient source-note PDF.

Important files:

```text
outputs/discharge_summary_draft.md
outputs/trace.json
outputs/quality_report.md
outputs/quality_report.json
outputs/structured_summary.json
outputs/state.json
outputs/learning_metrics.json
```

### `outputs_demo/`

Generated from synthetic demo patients.

Each patient folder has the same artifacts as `outputs/`, and `batch_index.json` summarizes the batch run.

### `ocr_cache/`

Stores OCR text retained for reproducible reruns and scanned-PDF fallback.

## End-To-End Data Flow

```text
PDF input
  -> pdf_ingest.py
  -> DocumentPage objects
  -> agent.py bounded loop
  -> extractors.py clinical extraction
  -> tools.py safety checks
  -> reporting.py quality + structured outputs
  -> learning.py optional edit-learning metrics
  -> CLI outputs and web dashboard
```

## Agent Trace Format

Each trace step records:

```json
{
  "step": 1,
  "reasoning": "Need source text before any clinical extraction...",
  "tool_or_action": "ingest_pdfs",
  "inputs": {"input_path": "task"},
  "result": "Read 1 PDF(s), 71 page(s), 24261 extracted characters.",
  "next_decision": "Continue to extract_summary_fields."
}
```

This proves the project is agentic and auditable, not just a single prompt-to-summary formatter.

## Safety And No-Fabrication Strategy

The project avoids unsafe output through several layers:

- Evidence required for supported clinical facts.
- Missing fields are explicit.
- Uncertain fields are marked for review.
- Medication rows preserve missing dose/frequency/duration values.
- Reconciliation rows flag unclear additions or changes.
- Conflicts are surfaced instead of resolved silently.
- OCR and tool failures become clinician-review flags.
- Final draft is always labeled as a clinician-review draft.

## How To Run

Create environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run provided patient:

```bash
PYTHONPATH=src python -m dscribe_agent.cli --input task --output outputs --learning-demo
```

Run demo batch:

```bash
python scripts/make_synthetic_patients.py
PYTHONPATH=src python -m dscribe_agent.cli --input demo_patients --output outputs_demo --batch --learning-demo
```

Run web dashboard:

```bash
PYTHONPATH=src python -m dscribe_agent.web_app --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_submission.py
```

## Test Coverage

`tests/test_agent_safety.py` checks:

- typed note extraction
- medication reconciliation
- conflict detection
- unsupported-field downgrade
- OCR warning behavior
- dashboard artifact allowlist

`scripts/validate_submission.py` checks:

- required artifacts exist
- output folders are valid
- trace has agent steps
- quality report exists
- structured summary exists
- demo batch exists
- web assets exist

## Current Verified Status

The latest audit passed:

- 3 runs available in the dashboard.
- 30 clean full-page screenshots across desktop and mobile.
- 0 console errors.
- 0 request failures.
- 0 layout/content problems.
- Unit tests passed.
- Submission validation passed.

## How To Explain This In An Interview

Short version:

"I built a local, safety-first discharge-summary agent. It ingests patient PDFs, handles scanned PDFs with OCR fallback, runs a bounded multi-step agent loop, extracts required sections with evidence, reconciles medications, detects conflicts, calls mocked safety tools, and outputs a draft plus trace, quality report, structured JSON, and learning metrics. The dashboard lets reviewers inspect every artifact. I optimized for clinical safety and auditability rather than unsupported fluency."

Technical version:

"The core design is an explicit state machine around `AgentState`. Each step updates structured state; then the loop chooses the next action by checking which clinical obligations remain unresolved. Extraction functions return typed `Field` and `Medication` objects with statuses, evidence, and flags. Before rendering, a no-fabrication guardrail downgrades any unsupported supported field. The optional learning loop uses simulated doctor edits and a reward signal based on normalized edit burden, but it only changes rendering strategy, not facts."

## Submission Notes

Include:

- source code
- `README.md`
- `PROJECT_STRUCTURE.md`
- generated `outputs/`
- generated `outputs_demo/`
- `ocr_cache/`
- tests
- scripts
- web dashboard files

Do not include:

- `.venv/`
- Python cache folders
- unrelated OS files
