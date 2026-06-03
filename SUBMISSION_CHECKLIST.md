# Dscribe Assignment Compliance Checklist

This checklist maps the take-home assignment requirements to the implemented project files and generated artifacts.

## Part 1 Required Agent

| Requirement | Status | Where It Is Covered |
| --- | --- | --- |
| Real agent loop, not a single prompt | Complete | `src/dscribe_agent/agent.py` uses a bounded state-driven loop that chooses the next action from `AgentState` and completed checks. |
| PDF ingestion | Complete | `src/dscribe_agent/pdf_ingest.py` reads PDFs with `pypdf`, uses OCR cache, and falls back to local macOS Vision OCR. |
| No fabrication | Complete | `agent.py` validates supported fields have evidence and downgrades unsupported values to review/uncertain. |
| Missing and pending data handling | Complete | `extractors.py` emits `MISSING`, `uncertain`, pending results, and clinician-review flags. |
| Medication reconciliation | Complete | `extract_admission_meds`, `extract_discharge_meds`, and `reconcile_medications` compare admission vs discharge meds. |
| Conflicting information handling | Complete | `detect_conflicts` flags competing diagnosis statements instead of choosing silently. |
| Tool usage | Complete | `tools.py` includes mocked drug-interaction lookup and clinician-review escalation. |
| Robust failure handling | Complete | PDF ingestion catches unreadable/corrupt PDF failures; agent catches tool/action failures and escalates them. |
| Step/iteration cap | Complete | `DischargeSummaryAgent(max_steps=10)` enforces a hard cap and records if the cap is hit. |
| Observability trace | Complete | `outputs/trace.json`, `outputs_demo/*/trace.json`, and dashboard Trace tab show reasoning, action, inputs, result, and next decision. |

## Required Output Sections

The structured summary and markdown draft include:

- Patient demographics
- Admission date
- Discharge date
- Principal diagnosis
- Secondary diagnoses
- Hospital course
- Procedures
- Discharge medications
- Medication reconciliation / changes from admission
- Allergies
- Follow-up instructions
- Pending results
- Discharge condition
- Conflicts and clinician-review flags
- Evidence notes

Generated files:

```text
outputs/discharge_summary_draft.md
outputs/structured_summary.json
outputs/quality_report.md
outputs/trace.json
outputs_demo/patient-a-clean/*
outputs_demo/patient-b-conflict-pending/*
```

## Part 2 Stretch Learning

| Requirement | Status | Where It Is Covered |
| --- | --- | --- |
| Reward / accuracy signal from edits | Complete | `learning.py` uses normalized edit burden with `SequenceMatcher`; reward is `1 - edit_burden`. |
| Simulated doctor edits | Complete | `simulated_doctor_edit` applies a hidden reviewer style policy. |
| Learning mechanism | Complete | `run_learning_demo` uses epsilon-greedy strategy selection over rendering strategies. |
| Before/after metrics and curve | Complete | `learning_metrics.json` stores before/after edit burden, best strategy, and iteration curve. |
| Safety limitations discussed | Complete | `README.md` and `PROJECT_STRUCTURE.md` explain that learning only changes presentation style, not clinical facts. |

Critical safety statement for the video:

```text
The learning system is intentionally isolated from clinical fact extraction. It only changes rendering strategy and presentation style. Clinical facts, evidence extraction, medication reconciliation, and safety checks remain deterministic and unaffected.
```

## Robust PDF Handling

The project is built for messy source-note PDFs in the provided patient folders.

Safety behavior:

- Clinical PDFs produce evidence-backed drafts where possible.
- Scanned PDFs use OCR cache or local OCR fallback.
- Corrupt, encrypted, unreadable, empty, or non-clinical PDFs fail safely with missing fields and review flags.
- The agent never invents plausible clinical details to fill gaps.

## Video Demo Plan

Record 3-5 minutes:

1. Start the dashboard with `PYTHONPATH=src python -m dscribe_agent.web_app --port 8000`.
2. Run `Run Provided`.
3. Run `Run Demo Batch`.
4. Open the demo conflict/pending patient.
5. Show the Trace tab and point out PDF ingestion, medication reconciliation, conflict detection, and clinician-review escalation.
6. Show the Draft tab and point to `MISSING`, `CLINICIAN_REVIEW`, pending results, and conflicts.
7. Show the Learning tab and before/after edit burden.
8. State the safety isolation sentence above.

## Submission Package

Include:

- `README.md`
- `PROJECT_STRUCTURE.md`
- `SUBMISSION_CHECKLIST.md`
- `DEMO_AND_INTERVIEW_GUIDE.md`
- `src/`
- `web/`
- `scripts/`
- `tests/`
- `task/`
- `demo_patients/`
- `outputs/`
- `outputs_demo/`
- `ocr_cache/`
- `requirements.txt`
- `pyproject.toml`

Exclude:

- `.venv/`
- `__pycache__/`
- `.DS_Store`
- API keys or secrets
- real patient data

## Final Verification Commands

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_submission.py
PYTHONPATH=src python -m dscribe_agent.web_app --port 8000
```
