# Discharge Summary Agent

Safe local agent for converting messy clinical source-note PDFs into a structured discharge-summary draft for clinician review.

The project is conservative by design: unsupported clinical facts are marked as `MISSING`, `uncertain`, or `CLINICIAN_REVIEW` instead of being guessed.

## Live Dashboard

[https://yashdhanani.github.io/Discharge-Summary-Agent/](https://yashdhanani.github.io/Discharge-Summary-Agent/)

The live dashboard is a static review build of generated artifacts. New PDF processing runs locally through the CLI or backend server.

## Project Highlights

- PDF ingestion with native text extraction and OCR-cache fallback.
- Bounded state-driven agent loop with a hard step cap.
- Evidence-backed required discharge-summary sections.
- Pending result detection.
- Medication extraction and reconciliation.
- Conflict detection for competing clinical statements.
- Mock medication safety tool calls.
- No-fabrication validation before rendering.
- Trace logging for every agent step.
- Simulated edit-learning report that changes presentation style only, never clinical facts.
- Local web dashboard and public static review dashboard.

## Repository Structure

```text
Discharge-Summary-Agent/
|-- README.md
|-- PROJECT_STRUCTURE.md
|-- pyproject.toml
|-- requirements.txt
|-- task/
|   `-- patient_source_notes.pdf
|-- sample_patients/
|-- src/dscribe_agent/
|-- scripts/
|-- tests/
|-- web/
|-- docs/
|-- outputs/
|-- outputs_samples/
`-- ocr_cache/
```

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run the provided patient:

```bash
PYTHONPATH=src python -m dscribe_agent.cli --input task --output outputs --learning-report
```

Run the sample patient batch:

```bash
python scripts/make_synthetic_patients.py
PYTHONPATH=src python -m dscribe_agent.cli --input sample_patients --output outputs_samples --batch --learning-report
```

Run the local dashboard:

```bash
PYTHONPATH=src python -m dscribe_agent.web_app --port 8000
```

Open:

```text
http://127.0.0.1:8000
```

Validate the project:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_project.py
```

Refresh the static dashboard data:

```bash
python scripts/build_static_site.py
```

## Generated Artifacts

Each run produces:

- `discharge_summary_draft.md`
- `trace.json`
- `quality_report.json`
- `quality_report.md`
- `structured_summary.json`
- `state.json`
- `learning_metrics.json`

## Safety Model

- Every supported fact must carry source evidence.
- Missing demographics, dates, allergies, medication dose/frequency/duration, and pending results stay explicit.
- Conflicting diagnoses are surfaced rather than collapsed into one unsupported answer.
- Medication reconciliation flags additions, missing source values, and unclear changes.
- OCR and tool failures become clinician-review flags.
- The final output is always a clinician-review draft.

## Learning Report

The learning report simulates reviewer edits and measures normalized edit burden across rendering strategies. This learning layer is intentionally isolated from clinical extraction. It can change wording and presentation strategy, but it cannot change diagnoses, medications, evidence, pending results, reconciliation, or safety flags.

## Production Roadmap

The current build is audit-first and ready for review. Strong production upgrades would include layout-aware OCR, calibrated confidence scoring, richer drug normalization, and larger clinician-style evaluation sets.
