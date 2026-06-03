from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = DOCS / "data"
RUNS_DIR = DATA / "runs"
REPO_URL = "https://github.com/yashdhanani/Discharge-Summary-Agent"
PAGES_URL = "https://yashdhanani.github.io/Discharge-Summary-Agent/"

ARTIFACTS = {
    "draft": "discharge_summary_draft.md",
    "trace": "trace.json",
    "quality": "quality_report.json",
    "quality_md": "quality_report.md",
    "structured": "structured_summary.json",
    "learning": "learning_metrics.json",
}

RUN_SPECS = [
    ("provided", "Provided patient source notes", ROOT / "outputs"),
    ("patient-a-clean", "Demo: patient a clean", ROOT / "outputs_demo" / "patient-a-clean"),
    (
        "patient-b-conflict-pending",
        "Demo: patient b conflict pending",
        ROOT / "outputs_demo" / "patient-b-conflict-pending",
    ),
]


def main() -> None:
    if RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    runs: list[dict[str, Any]] = []
    for run_id, label, output_dir in RUN_SPECS:
        if not output_dir.exists():
            raise FileNotFoundError(f"Missing output directory: {output_dir}")
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        artifacts: dict[str, str] = {}
        for artifact, filename in ARTIFACTS.items():
            source = output_dir / filename
            if not source.exists():
                raise FileNotFoundError(f"Missing artifact: {source}")
            target = run_dir / filename
            shutil.copyfile(source, target)
            artifacts[artifact] = f"data/runs/{run_id}/{filename}"

        quality = read_json(output_dir / "quality_report.json")
        learning = read_json(output_dir / "learning_metrics.json")
        required = quality.get("required_fields", {})
        medications = quality.get("medications", {})
        runs.append(
            {
                "id": run_id,
                "label": label,
                "status": "ready",
                "artifacts": artifacts,
                "summary": {
                    "evidence_coverage": required.get("evidence_coverage"),
                    "missing_fields": len(required.get("missing", [])),
                    "clinician_review_flags": len(quality.get("clinician_review_flags", [])),
                    "conflicts": quality.get("conflicts_count", 0),
                    "discharge_meds": medications.get("discharge_count", 0),
                },
                "quality": quality,
                "learning": {
                    "before_edit_burden": learning.get("before_edit_burden"),
                    "after_edit_burden": learning.get("after_edit_burden"),
                    "best_strategy": learning.get("best_strategy"),
                },
            }
        )

    manifest = {
        "project": "Dscribe Discharge Summary Agent",
        "repo_url": REPO_URL,
        "pages_url": PAGES_URL,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runs": runs,
    }
    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (DOCS / ".nojekyll").touch()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


if __name__ == "__main__":
    main()
