from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .models import AgentState, Field, Medication


REQUIRED_FIELDS = [
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


def build_quality_report(state: AgentState) -> dict[str, Any]:
    missing_fields = []
    uncertain_fields = []
    evidence_backed = []
    for key in REQUIRED_FIELDS:
        field = state.summary.get(key)
        if field is None:
            missing_fields.append(key)
            continue
        if field.status == "missing":
            missing_fields.append(key)
        if field.status == "uncertain":
            uncertain_fields.append(key)
        if _has_evidence(field):
            evidence_backed.append(key)

    safety_alerts = [e for e in state.escalations if "Medication reconciliation:" not in e]
    reconciliation_alerts = [e for e in state.escalations if "Medication reconciliation:" in e]
    return {
        "patient_pages_read": len(state.pages),
        "extracted_characters": sum(len(p.text) for p in state.pages),
        "agent_steps": len(state.trace),
        "step_cap_respected": not any("hard iteration cap" in e.lower() for e in state.escalations),
        "required_fields": {
            "total": len(REQUIRED_FIELDS),
            "missing": missing_fields,
            "uncertain": uncertain_fields,
            "evidence_backed": evidence_backed,
            "evidence_coverage": round(len(evidence_backed) / len(REQUIRED_FIELDS), 3),
        },
        "medications": {
            "discharge_count": len(state.discharge_meds),
            "admission_or_inpatient_count": len(state.admission_meds),
            "reconciliation_rows": len(state.med_reconciliation),
            "reconciliation_alerts": len(reconciliation_alerts),
        },
        "pending_results_count": len(state.pending_results),
        "conflicts_count": len(state.conflicts),
        "safety_alerts_count": len(safety_alerts),
        "clinician_review_flags": sorted(set(state.escalations)),
    }


def render_quality_markdown(report: dict[str, Any]) -> str:
    fields = report["required_fields"]
    meds = report["medications"]
    lines = [
        "# Quality And Safety Report",
        "",
        f"- Pages read: {report['patient_pages_read']}",
        f"- Extracted characters: {report['extracted_characters']}",
        f"- Agent steps: {report['agent_steps']}",
        f"- Step cap respected: {report['step_cap_respected']}",
        f"- Evidence coverage: {fields['evidence_coverage']}",
        f"- Missing required fields: {', '.join(fields['missing']) or 'none'}",
        f"- Uncertain required fields: {', '.join(fields['uncertain']) or 'none'}",
        f"- Discharge medications extracted: {meds['discharge_count']}",
        f"- Medication reconciliation alerts: {meds['reconciliation_alerts']}",
        f"- Pending results: {report['pending_results_count']}",
        f"- Conflicts: {report['conflicts_count']}",
        f"- Safety alerts: {report['safety_alerts_count']}",
        "",
        "## Clinician Review Flags",
    ]
    for flag in report["clinician_review_flags"]:
        lines.append(f"- {flag}")
    return "\n".join(lines)


def build_structured_summary(state: AgentState) -> dict[str, Any]:
    return {
        "document_status": "clinical_review_required",
        "required_sections": {key: _field_to_plain(state.summary.get(key)) for key in REQUIRED_FIELDS},
        "discharge_medications": [_med_to_plain(med) for med in state.discharge_meds],
        "admission_or_inpatient_medications": [_med_to_plain(med) for med in state.admission_meds],
        "medication_reconciliation": state.med_reconciliation,
        "pending_results": [_field_to_plain(item) for item in state.pending_results],
        "conflicts": state.conflicts,
        "clinician_review_flags": sorted(set(state.escalations)),
    }


def _field_to_plain(field: Field | None) -> dict[str, Any]:
    if field is None:
        return {"value": "MISSING", "status": "missing", "evidence": [], "flags": ["Field was not produced."]}
    if isinstance(field.value, list):
        value: Any = [
            _field_to_plain(item) if isinstance(item, Field) else item
            for item in field.value
        ]
    else:
        value = field.value
    return {
        "value": value,
        "status": field.status,
        "evidence": [asdict(ev) for ev in field.evidence],
        "flags": list(field.flags),
    }


def _med_to_plain(med: Medication) -> dict[str, Any]:
    return {
        "name": med.name,
        "dose": med.dose,
        "frequency": med.frequency,
        "duration": med.duration,
        "source": med.source,
        "status": med.status,
        "evidence": [asdict(ev) for ev in med.evidence],
        "flags": list(med.flags),
    }


def _has_evidence(field: Field) -> bool:
    if field.evidence:
        return True
    if isinstance(field.value, list):
        return any(isinstance(item, Field) and bool(item.evidence) for item in field.value)
    return False
