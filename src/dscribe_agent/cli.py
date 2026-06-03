from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import re

from .agent import DischargeSummaryAgent, render_markdown, render_trace
from .learning import run_learning_demo
from .pdf_ingest import find_patient_pdfs
from .reporting import build_quality_report, build_structured_summary, render_quality_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local Dscribe discharge-summary agent.")
    parser.add_argument("--input", required=True, help="Patient PDF or folder containing patient source PDFs.")
    parser.add_argument("--output", default="outputs", help="Output directory for draft, trace, and metrics.")
    parser.add_argument("--max-steps", type=int, default=10, help="Hard cap on agent loop iterations.")
    parser.add_argument("--learning-demo", action="store_true", help="Run Part 2 simulated edit-learning demo.")
    parser.add_argument("--batch", action="store_true", help="Treat each immediate child folder/PDF as a separate patient.")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = default_ocr_cache(output_dir)
    agent = DischargeSummaryAgent(max_steps=args.max_steps, ocr_cache_dir=cache_dir)

    if args.batch:
        runs = []
        for patient_input in discover_patient_inputs(Path(args.input)):
            patient_output = output_dir / slug(patient_input.stem if patient_input.is_file() else patient_input.name)
            runs.append(run_one(agent, patient_input, patient_output, args.learning_demo))
        (output_dir / "batch_index.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
        print(f"Wrote {output_dir / 'batch_index.json'}")
    else:
        run_one(agent, Path(args.input), output_dir, args.learning_demo)


def run_one(agent: DischargeSummaryAgent, input_path: Path, output_dir: Path, learning_demo: bool) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    state = agent.run(input_path)
    draft = render_markdown(state)
    quality = build_quality_report(state)
    structured = build_structured_summary(state)

    (output_dir / "discharge_summary_draft.md").write_text(draft, encoding="utf-8")
    (output_dir / "trace.json").write_text(render_trace(state), encoding="utf-8")
    (output_dir / "state.json").write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")
    (output_dir / "structured_summary.json").write_text(json.dumps(structured, indent=2), encoding="utf-8")
    (output_dir / "quality_report.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    (output_dir / "quality_report.md").write_text(render_quality_markdown(quality), encoding="utf-8")

    print(f"Wrote {output_dir / 'discharge_summary_draft.md'}")
    print(f"Wrote {output_dir / 'trace.json'}")
    print(f"Wrote {output_dir / 'quality_report.md'}")

    learning_summary = None
    if learning_demo:
        report = run_learning_demo(draft, output_dir / "learning_metrics.json")
        print(f"Wrote {output_dir / 'learning_metrics.json'}")
        print(f"Learning demo: before={report['before_edit_burden']} after={report['after_edit_burden']} best={report['best_strategy']}")
        learning_summary = {
            "before_edit_burden": report["before_edit_burden"],
            "after_edit_burden": report["after_edit_burden"],
            "best_strategy": report["best_strategy"],
        }
    return {
        "input": str(input_path),
        "output": str(output_dir),
        "quality": {
            "missing": quality["required_fields"]["missing"],
            "uncertain": quality["required_fields"]["uncertain"],
            "discharge_meds": quality["medications"]["discharge_count"],
            "review_flags": len(quality["clinician_review_flags"]),
        },
        "learning": learning_summary,
    }


def discover_patient_inputs(input_path: Path) -> list[Path]:
    if input_path.is_file():
        return [input_path]
    children = sorted(input_path.iterdir())
    patient_dirs = [p for p in children if p.is_dir() and find_patient_pdfs(p)]
    patient_pdfs = [
        p for p in children
        if p.is_file() and p.suffix.lower() == ".pdf" and p in find_patient_pdfs(input_path)
    ]
    if patient_dirs:
        return patient_dirs
    if patient_pdfs:
        return patient_pdfs
    return [input_path]


def slug(value: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return clean or "patient"


def default_ocr_cache(output_dir: Path) -> Path:
    explicit_cache = Path("ocr_cache")
    legacy_cache = Path(".codex_pdf_text")
    if explicit_cache.exists():
        return explicit_cache
    if legacy_cache.exists():
        return legacy_cache
    return output_dir / "ocr_cache"


if __name__ == "__main__":
    main()
