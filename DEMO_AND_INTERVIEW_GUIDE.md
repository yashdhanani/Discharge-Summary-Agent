# Demo And Interview Guide

Use this guide for the required 3-5 minute screen recording and for explaining the project in an interview.

## What To Select In The Form

Select:

```text
Part 1 + Part 2
```

Part 1 is complete, and Part 2 includes a simulated reviewer, reward metric, epsilon-greedy learning mechanism, before/after metrics, and an improvement curve.

## Video Demo Flow

Keep the video tight. Aim for 3-5 minutes.

### 1. Start The Dashboard

```bash
PYTHONPATH=src python -m dscribe_agent.web_app --port 8000
```

Open:

```text
http://127.0.0.1:8000/
```

### 2. Run The Provided Patient

Click:

```text
Run Provided
```

Say:

```text
This runs the provided patient source-note PDF. The trace records source ingestion, extracted pages, extracted characters, and the next clinical action.
```

### 3. Run The Demo Batch

Click:

```text
Run Demo Batch
```

Say:

```text
The assignment asks for at least two patients in the video. The provided folder has one patient, so I added two synthetic patients: one clean case and one case with conflict and pending data.
```

### 4. Show The Trace Tab

Open the trace for the provided patient or the conflict/pending demo patient.

Point out:

- `ingest_pdfs`
- `extract_summary_fields`
- `extract_pending_results`
- `extract_medications`
- `reconcile_medications`
- `detect_conflicts`
- `run_safety_tools`
- `validate_no_fabrication`
- `render_draft`

Say:

```text
Every step records reasoning, action, inputs, result, and next decision. This is not a single prompt; the agent updates state, then chooses the next action by checking which required clinical obligations are still unresolved.
```

### 5. Show Missing/Pending Data

Open the Draft or Quality tab.

Say:

```text
When the agent cannot source a required field, it marks it as MISSING or uncertain and adds a clinician-review flag instead of inventing a value.
```

### 6. Show Medication Reconciliation

Open the Draft or Quality tab.

Say:

```text
Admission and discharge medications are extracted separately. If a medication was added, stopped, changed, or lacks dose/frequency/duration evidence, the system flags it for reconciliation.
```

### 7. Show Conflict Detection

Use:

```text
Demo: patient b conflict pending
```

Say:

```text
This case includes conflicting diagnosis information and a pending urine culture. The agent does not choose a convenient answer; it surfaces the conflict and pending result for clinician review.
```

### 8. Show Part 2 Learning

Open the Learning tab.

Say:

```text
Part 2 simulates doctor edits, computes normalized edit burden, and uses an epsilon-greedy bandit over rendering strategies. The chart shows edit-burden improvement over iterations.
```

Then say the safety sentence clearly:

```text
The learning system is intentionally isolated from clinical fact extraction. It only changes rendering strategy and presentation style. Clinical facts, evidence extraction, medication reconciliation, and safety checks remain deterministic and unaffected.
```

## Agentic Behavior Talking Points

The agent uses a bounded state-driven loop. Each step reacts to state and tool results, then the next action is selected from the remaining clinical obligations.

Key decision points:

```text
If PDF native text is sparse -> use OCR cache or OCR fallback.
If OCR or PDF read fails -> record warning and escalate; do not pretend success.
If a required field has no evidence -> mark MISSING or uncertain.
If medications exist -> call medication safety tool.
If admission/discharge med matching is unclear -> flag reconciliation.
If conflicting diagnoses appear -> surface conflict instead of choosing one.
If a supported field lacks evidence -> downgrade it with the no-fabrication guardrail.
If step cap is hit -> stop and flag clinician review.
```

How to explain it:

```text
The agent is intentionally conservative. It does not try to maximize fluent output. It maximizes traceability and clinical safety. Unsupported facts are downgraded or flagged, and every decision is visible in the trace.
```

## Part 2 Interview Explanation

Short version:

```text
I implemented a simulated doctor-edit loop with normalized edit burden as the reward. The learner uses an epsilon-greedy strategy selector over rendering policies. It improves presentation quality while preserving the Part 1 safety boundary.
```

Important limitation:

```text
The reviewer is simulated, so the metric proves the feedback loop works but does not prove clinical correctness. Real deployment would need clinician-edited held-out charts and safety-specific evaluation.
```

## Final Repo Checklist

Include:

```text
README.md
PROJECT_STRUCTURE.md
SUBMISSION_CHECKLIST.md
DEMO_AND_INTERVIEW_GUIDE.md
requirements.txt
pyproject.toml
src/
web/
scripts/
tests/
task/
demo_patients/
outputs/
outputs_demo/
ocr_cache/
```

Exclude:

```text
.venv/
__pycache__/
*.pyc
.DS_Store
API keys
real patient data
```

## Final Verification Commands

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python scripts/validate_submission.py
```
