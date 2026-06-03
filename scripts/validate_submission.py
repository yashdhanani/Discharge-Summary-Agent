from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_DIRS = [
    ROOT / "outputs",
    ROOT / "outputs_demo" / "patient-a-clean",
    ROOT / "outputs_demo" / "patient-b-conflict-pending",
]
REQUIRED_ARTIFACTS = [
    "discharge_summary_draft.md",
    "trace.json",
    "quality_report.json",
    "quality_report.md",
    "structured_summary.json",
    "learning_metrics.json",
]


def main() -> None:
    errors: list[str] = []
    for folder in RUN_DIRS:
        errors.extend(validate_run_folder(folder))

    batch_index = ROOT / "outputs_demo" / "batch_index.json"
    if not batch_index.exists():
        errors.append("outputs_demo/batch_index.json is missing.")
    else:
        batch = read_json(batch_index, errors)
        if len(batch or []) < 2:
            errors.append("Demo batch should include at least two patients.")

    for path in [ROOT / "web" / "index.html", ROOT / "web" / "app.js", ROOT / "web" / "styles.css"]:
        if not path.exists():
            errors.append(f"{path.relative_to(ROOT)} is missing.")

    if errors:
        print("Submission validation failed:")
        for error in errors:
            print(f"- {error}")
        raise SystemExit(1)

    print("Submission validation passed.")
    print(f"Checked {len(RUN_DIRS)} run folders, generated artifacts, demo batch, and web assets.")


def validate_run_folder(folder: Path) -> list[str]:
    errors: list[str] = []
    if not folder.exists():
        return [f"{folder.relative_to(ROOT)} is missing."]

    for artifact in REQUIRED_ARTIFACTS:
        path = folder / artifact
        if not path.exists():
            errors.append(f"{path.relative_to(ROOT)} is missing.")
        elif path.stat().st_size == 0:
            errors.append(f"{path.relative_to(ROOT)} is empty.")

    trace = read_json(folder / "trace.json", errors)
    quality = read_json(folder / "quality_report.json", errors)
    structured = read_json(folder / "structured_summary.json", errors)
    learning = read_json(folder / "learning_metrics.json", errors)

    if trace is not None:
        if not (1 <= len(trace) <= 10):
            errors.append(f"{folder.relative_to(ROOT)} trace should have 1-10 steps.")
        for index, step in enumerate(trace, start=1):
            for key in ["step", "reasoning", "tool_or_action", "inputs", "result", "next_decision"]:
                if key not in step:
                    errors.append(f"{folder.relative_to(ROOT)} trace step {index} missing {key}.")

    if quality is not None:
        if quality.get("step_cap_respected") is not True:
            errors.append(f"{folder.relative_to(ROOT)} did not respect step cap.")
        if quality.get("medications", {}).get("discharge_count", 0) < 1:
            errors.append(f"{folder.relative_to(ROOT)} extracted no discharge medications.")

    if structured is not None:
        if structured.get("document_status") != "draft_for_clinician_review":
            errors.append(f"{folder.relative_to(ROOT)} structured summary has wrong document status.")
        sections = structured.get("required_sections", {})
        for name, field in sections.items():
            if field.get("status") == "supported" and not field_has_evidence(field):
                errors.append(f"{folder.relative_to(ROOT)} supported field without evidence: {name}.")
        for med in structured.get("discharge_medications", []):
            if not med.get("evidence"):
                errors.append(f"{folder.relative_to(ROOT)} medication without evidence: {med.get('name')}.")

    if learning is not None:
        before = learning.get("before_edit_burden")
        after = learning.get("after_edit_burden")
        if before is None or after is None:
            errors.append(f"{folder.relative_to(ROOT)} learning metrics missing before/after.")
        elif after > before:
            errors.append(f"{folder.relative_to(ROOT)} learning burden got worse ({before} -> {after}).")

    return errors


def field_has_evidence(field: dict) -> bool:
    if field.get("evidence"):
        return True
    value = field.get("value")
    if isinstance(value, list):
        return any(isinstance(item, dict) and field_has_evidence(item) for item in value)
    return False


def read_json(path: Path, errors: list[str]):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"{path.relative_to(ROOT)} is invalid JSON: {exc}.")
        return None


if __name__ == "__main__":
    main()
