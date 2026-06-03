from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from .extractors import (
    detect_conflicts,
    extract_admission_meds,
    extract_discharge_meds,
    extract_pending_results,
    extract_summary_fields,
    reconcile_medications,
)
from .models import AgentState, Field
from .pdf_ingest import find_patient_pdfs, read_pdf_pages
from .tools import drug_interaction_lookup, flag_for_clinician_review


class DischargeSummaryAgent:
    def __init__(self, max_steps: int = 10, ocr_cache_dir: Path | None = None) -> None:
        self.max_steps = max_steps
        self.ocr_cache_dir = ocr_cache_dir

    def run(self, input_path: Path) -> AgentState:
        state = AgentState()
        actions: dict[str, Callable[[AgentState], str]] = {
            "ingest_pdfs": lambda s: self._ingest(input_path, s),
            "extract_summary_fields": self._extract_summary,
            "extract_pending_results": self._extract_pending,
            "extract_medications": self._extract_meds,
            "reconcile_medications": self._reconcile_meds,
            "detect_conflicts": self._detect_conflicts,
            "run_safety_tools": self._run_safety_tools,
            "validate_no_fabrication": self._validate_no_fabrication,
            "render_draft": lambda s: "Draft can be rendered from supported fields and explicit flags.",
        }

        step = 0
        completed: set[str] = set()
        while step < self.max_steps:
            name = self._choose_next_action(state, completed)
            if not name:
                break
            action = actions[name]
            step += 1
            reasoning = self._reasoning_for(name, state)
            try:
                result = action(state)
            except Exception as exc:  # noqa: BLE001 - deliberate robust failure boundary
                result = f"FAILED: {exc}"
                state.escalations.append(flag_for_clinician_review(f"Tool/action {name} failed: {exc}"))
            completed.add(name)
            next_decision = self._next_decision(state, completed, step)
            state.trace.append(
                {
                    "step": step,
                    "reasoning": reasoning,
                    "tool_or_action": name,
                    "inputs": self._trace_inputs(name, input_path, state),
                    "result": result,
                    "next_decision": next_decision,
                }
            )

        if self._choose_next_action(state, completed):
            state.escalations.append(flag_for_clinician_review("Agent hit hard iteration cap before completing all planned checks."))
        return state

    def _ingest(self, input_path: Path, state: AgentState) -> str:
        pdfs = find_patient_pdfs(input_path)
        if not pdfs:
            raise FileNotFoundError(f"No PDFs found at {input_path}")
        warnings: list[str] = []
        for pdf in pdfs:
            pages, pdf_warnings = read_pdf_pages(pdf, self.ocr_cache_dir)
            state.pages.extend(pages)
            warnings.extend(pdf_warnings)
        if warnings:
            state.escalations.extend(flag_for_clinician_review(w) for w in warnings)
        chars = sum(len(p.text) for p in state.pages)
        return f"Read {len(pdfs)} PDF(s), {len(state.pages)} page(s), {chars} extracted characters."

    def _extract_summary(self, state: AgentState) -> str:
        state.summary = extract_summary_fields(state.pages)
        missing = [k for k, v in state.summary.items() if v.status in {"missing", "uncertain"}]
        for field in missing:
            state.escalations.append(flag_for_clinician_review(f"{field} is missing or uncertain."))
        return f"Extracted {len(state.summary)} summary fields; {len(missing)} need review."

    def _extract_pending(self, state: AgentState) -> str:
        state.pending_results = extract_pending_results(state.pages)
        if not state.pending_results:
            state.pending_results.append(
                Field(
                    "MISSING",
                    "missing",
                    flags=["No pending-result section found; verify manually."],
                )
            )
            state.escalations.append(flag_for_clinician_review("No pending-result section found; verify manually."))
        return f"Found {len(state.pending_results)} pending/missing result mention(s)."

    def _extract_meds(self, state: AgentState) -> str:
        state.discharge_meds = extract_discharge_meds(state.pages)
        state.admission_meds = extract_admission_meds(state.pages)
        if not state.discharge_meds:
            state.escalations.append(flag_for_clinician_review("No discharge medication list extracted."))
        return f"Extracted {len(state.discharge_meds)} discharge meds and {len(state.admission_meds)} admission/inpatient meds."

    def _reconcile_meds(self, state: AgentState) -> str:
        state.med_reconciliation = reconcile_medications(state.admission_meds, state.discharge_meds)
        flagged = sum(1 for row in state.med_reconciliation if row["flags"])
        for row in state.med_reconciliation:
            if row["flags"]:
                state.escalations.append(flag_for_clinician_review(f"Medication reconciliation: {row['medication']} - {'; '.join(row['flags'])}"))
        return f"Medication reconciliation produced {len(state.med_reconciliation)} rows; {flagged} flagged."

    def _detect_conflicts(self, state: AgentState) -> str:
        state.conflicts = detect_conflicts(state.pages)
        for conflict in state.conflicts:
            state.escalations.append(flag_for_clinician_review(conflict["message"]))
        return f"Detected {len(state.conflicts)} potential conflict(s)."

    def _run_safety_tools(self, state: AgentState) -> str:
        alerts = drug_interaction_lookup([m.name for m in state.discharge_meds])
        for alert in alerts:
            state.escalations.append(flag_for_clinician_review(alert))
        return f"Drug-interaction mock returned {len(alerts)} alert(s)."

    def _validate_no_fabrication(self, state: AgentState) -> str:
        unsupported: list[str] = []
        for key, field in state.summary.items():
            list_items_have_evidence = (
                isinstance(field.value, list)
                and bool(field.value)
                and all(getattr(item, "evidence", None) for item in field.value)
            )
            if field.status == "supported" and field.value not in ([], "", None) and not field.evidence and not list_items_have_evidence:
                unsupported.append(key)
        if unsupported:
            for key in unsupported:
                state.summary[key].status = "uncertain"
                state.summary[key].flags.append("Supported value lacked evidence; downgraded by guardrail.")
            state.escalations.append(flag_for_clinician_review(f"Guardrail downgraded unsupported fields: {', '.join(unsupported)}"))
        return f"No-fabrication guardrail checked {len(state.summary)} fields; downgraded {len(unsupported)}."

    def _reasoning_for(self, name: str, state: AgentState) -> str:
        reasons = {
            "ingest_pdfs": "Need source text before any clinical extraction; sparse PDFs require fallback rather than silent failure.",
            "extract_summary_fields": "Required discharge-summary sections must be filled only from sourced evidence.",
            "extract_pending_results": "Pending/missing data must be explicit and visible to the reviewer.",
            "extract_medications": "Medication reconciliation requires separate admission/inpatient and discharge lists.",
            "reconcile_medications": "Medication additions, stops, and unclear changes are safety-critical.",
            "detect_conflicts": "Contradictory diagnoses or results should be surfaced, not arbitrarily resolved.",
            "run_safety_tools": "Medication safety checks are tool calls that the agent should choose when meds exist.",
            "validate_no_fabrication": "Before rendering, supported facts must have evidence or be downgraded.",
            "render_draft": "All checks are complete; produce a clinician-review draft.",
        }
        return reasons.get(name, f"Continue planned work with {len(state.pages)} pages available.")

    def _trace_inputs(self, name: str, input_path: Path, state: AgentState) -> dict[str, Any]:
        if name == "ingest_pdfs":
            return {"input_path": str(input_path)}
        return {"pages": len(state.pages), "summary_fields": list(state.summary), "discharge_meds": [m.name for m in state.discharge_meds]}

    def _choose_next_action(self, state: AgentState, completed: set[str]) -> str | None:
        if "ingest_pdfs" not in completed:
            return "ingest_pdfs"
        if "extract_summary_fields" not in completed:
            return "extract_summary_fields"
        if "extract_pending_results" not in completed:
            return "extract_pending_results"
        if "extract_medications" not in completed:
            return "extract_medications"
        if "reconcile_medications" not in completed:
            return "reconcile_medications"
        if "detect_conflicts" not in completed:
            return "detect_conflicts"
        if "run_safety_tools" not in completed and state.discharge_meds:
            return "run_safety_tools"
        if "validate_no_fabrication" not in completed:
            return "validate_no_fabrication"
        if "render_draft" not in completed:
            return "render_draft"
        return None

    def _next_decision(self, state: AgentState, completed: set[str], step: int) -> str:
        if step >= self.max_steps:
            return "Stop: hard step cap reached."
        next_action = self._choose_next_action(state, completed)
        if not next_action:
            return "Stop: planned checks complete."
        if next_action == "run_safety_tools":
            return "Continue to run_safety_tools because discharge medications were extracted."
        if next_action == "validate_no_fabrication" and not state.discharge_meds:
            return "Skip medication safety lookup because no discharge medications were extracted; continue to validate_no_fabrication."
        return f"Continue to {next_action}."


def render_markdown(state: AgentState) -> str:
    lines = [
        "# Discharge Summary Draft",
        "",
        "Status: DRAFT FOR CLINICIAN REVIEW. Do not finalize without human verification.",
        "",
        "## Required Sections",
    ]
    ordered = [
        "patient_demographics",
        "admission_date",
        "discharge_date",
        "principal_diagnosis",
        "secondary_diagnoses",
        "hospital_course",
        "procedures",
        "allergies",
        "follow_up_instructions",
        "discharge_condition",
    ]
    for key in ordered:
        field = state.summary.get(key)
        lines.append(f"### {key.replace('_', ' ').title()}")
        lines.extend(_field_lines(field))
        lines.append("")

    lines.append("## Discharge Medications")
    if state.discharge_meds:
        for med in state.discharge_meds:
            lines.append(f"- {med.name}: dose={med.dose}; frequency={med.frequency}; duration={med.duration}")
            for flag in med.flags:
                lines.append(f"  - REVIEW: {flag}")
    else:
        lines.append("- MISSING: no discharge medication list could be extracted.")
    lines.append("")

    lines.append("## Medication Reconciliation")
    for row in state.med_reconciliation:
        lines.append(f"- {row['medication']}: {row['status']}")
        for flag in row["flags"]:
            lines.append(f"  - REVIEW: {flag}")
    lines.append("")

    lines.append("## Pending Results")
    if state.pending_results:
        for item in state.pending_results:
            for line in _field_lines(item):
                lines.append(line if line.startswith("- ") else f"- {line}")
    else:
        lines.append("- MISSING: no pending-result references found.")
    lines.append("")

    lines.append("## Conflicts And Review Flags")
    if state.conflicts:
        for conflict in state.conflicts:
            lines.append(f"- {conflict['field']}: {conflict['message']} Values: {conflict.get('values')}")
    for escalation in sorted(set(state.escalations)):
        lines.append(f"- {escalation}")
    lines.append("")

    lines.append("## Evidence Notes")
    for key, field in state.summary.items():
        if field and field.evidence:
            ev = field.evidence[0]
            lines.append(f"- {key}: {ev.source} p{ev.page} - {ev.text[:220]}")
    for med in state.discharge_meds:
        if med.evidence:
            ev = med.evidence[0]
            lines.append(f"- discharge_medication.{med.name}: {ev.source} p{ev.page} - {ev.text[:220]}")
    return "\n".join(lines)


def render_trace(state: AgentState) -> str:
    return json.dumps(state.trace, indent=2, default=lambda obj: asdict(obj))


def _field_lines(field: Any) -> list[str]:
    if field is None:
        return ["- MISSING"]
    if isinstance(field.value, list):
        if not field.value:
            lines = [f"- {field.status.upper()}: []"]
        else:
            lines = []
            for item in field.value:
                if hasattr(item, "value"):
                    lines.append(f"- {item.value}")
                else:
                    lines.append(f"- {item}")
    else:
        lines = [f"- {field.status.upper()}: {field.value}"]
    for flag in getattr(field, "flags", []):
        lines.append(f"- REVIEW: {flag}")
    return lines
