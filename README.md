# Dscribe Discharge Summary Agent

Safe local agent for turning messy clinical source-note PDFs into a structured discharge-summary draft for clinician review. The implementation is intentionally conservative: if a clinical fact is not supported by source text, the draft says `MISSING`, `uncertain`, or `CLINICIAN_REVIEW` instead of guessing.

## What To Review

- `outputs/discharge_summary_draft.md` - draft generated from the provided patient source-note PDF.
- `outputs/trace.json` - readable agent step trace with reasoning, action, inputs, result, and next decision.
- `outputs/quality_report.md` - evidence coverage, missing fields, med reconciliation flags, safety alerts.
- `outputs/structured_summary.json` - machine-readable version of the draft.
- `outputs_demo/` - two synthetic demo patients for the required video walkthrough.
- `ocr_cache/` - local OCR text cache retained for reproducible reruns and scanned-PDF fallback.
- `web/` - frontend dashboard served by the local backend.
- `tests/test_agent_safety.py` - safety regression tests.
- `SUBMISSION_CHECKLIST.md` - requirement-by-requirement mapping for reviewers and video prep.
- `DEMO_AND_INTERVIEW_GUIDE.md` - 3-5 minute video script and interview talking points.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
PYTHONPATH=src python -m dscribe_agent.cli --input task --output outputs --learning-demo
```

Run the two-patient synthetic demo:

```bash
python scripts/make_synthetic_patients.py
PYTHONPATH=src python -m dscribe_agent.cli --input demo_patients --output outputs_demo --batch --learning-demo
```

Run the frontend/backend dashboard:

```bash
PYTHONPATH=src python -m dscribe_agent.web_app --port 8000
```

Then open `http://127.0.0.1:8000`.

Run tests:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_submission.py
```

When submitting a zip, exclude `.venv/`; recreate it with the commands above.

Optional console-script install:

```bash
python -m pip install --no-build-isolation -e .
dscribe-agent --input task --output outputs --learning-demo
```

## Agent Design

The agent uses a bounded, state-driven loop with a hard step cap. It is not a fixed one-shot formatter; each action updates `AgentState`, and the next action is chosen by inspecting what evidence, medications, pending results, conflicts, and safety checks are still unresolved.

1. Ingest source PDFs with native text extraction.
2. Use `ocr_cache/` when available, or fall back to local macOS Vision OCR for scanned PDFs.
3. Extract required discharge-summary sections with evidence snippets.
4. Extract pending/missing results.
5. Extract admission/inpatient and discharge medications separately.
6. Reconcile medication additions, stops, and changes.
7. Detect conflicting diagnoses.
8. Run mocked medication safety tools.
9. Validate the no-fabrication guardrail.
10. Render the draft, trace, structured JSON, and quality report.

The loop stops at `--max-steps` and escalates if it cannot complete safely. If no discharge medications are extracted, the agent skips the medication safety lookup and moves to no-fabrication validation; if medications are present, it calls the safety tool.

## Safety Guardrails

Clinical safety is the main design constraint.

- Every supported fact must carry source evidence.
- Missing demographics, dates, allergies, medication doses, or pending results are explicit.
- Conflicting diagnoses are surfaced instead of merged.
- Medication changes without a clear admission/discharge match are flagged for reconciliation.
- Mocked drug-safety alerts are escalated, not buried.
- OCR sparsity and tool failures become clinician-review flags.
- Corrupted, encrypted, non-clinical, or unreadable PDFs fail safely with missing fields and review flags rather than fabricated clinical content.
- The output is always a draft for clinician review.

## Part 2 Learning Loop

`--learning-demo` simulates doctor edits and measures edit burden with normalized string similarity. A small epsilon-greedy bandit compares rendering strategies and rewards the one that reduces edits. The learning mechanism changes presentation policy only; it never changes extracted facts, diagnoses, medications, or safety flags.

The learning system is intentionally isolated from clinical fact extraction. It only changes rendering strategy and presentation style. Clinical facts, evidence extraction, medication reconciliation, and safety checks remain deterministic and unaffected.

This keeps the stretch demo aligned with the Part 1 guardrail: optimization can reduce edit burden, but it cannot make the agent vaguer or overwrite clinical evidence.

## Demo Video Script

For the required 3-5 minute video:

1. Run `PYTHONPATH=src python -m dscribe_agent.cli --input task --output outputs --learning-demo`.
2. Open `outputs/trace.json` and show PDF ingestion, med reconciliation, conflict detection, and safety-tool steps.
3. Open `outputs/discharge_summary_draft.md` and point to missing demographics/dates, pending urine culture, and medication flags.
4. Run `PYTHONPATH=src python -m dscribe_agent.cli --input demo_patients --output outputs_demo --batch --learning-demo`.
5. Show `outputs_demo/batch_index.json`: one clean patient and one conflict/pending-data patient.
6. Show `learning_metrics.json` before/after edit burden.
7. State clearly: "The learning system is intentionally isolated from clinical fact extraction. It only changes rendering strategy and presentation style. Clinical facts, evidence extraction, medication reconciliation, and safety checks remain deterministic and unaffected."
8. Open `http://127.0.0.1:8000` and show the dashboard view.

## Limitations

The extraction layer is deterministic and explainable rather than LLM-heavy; that improves auditability but misses some handwritten or layout-dependent details. With more time I would add stronger layout-aware OCR, calibrated confidence scoring, a richer drug normalization ontology, and evaluation on more synthetic patient folders with clinician-style corrected summaries.
