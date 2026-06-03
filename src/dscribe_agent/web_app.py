from __future__ import annotations

import argparse
import json
import mimetypes
from json import JSONDecodeError
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .agent import DischargeSummaryAgent
from .cli import default_ocr_cache, discover_patient_inputs, run_one, slug


APP_VERSION = "1.0.0"
DEFAULT_MAX_STEPS = 10
MIN_MAX_STEPS = 1
MAX_MAX_STEPS = 20
ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = ROOT / "web"
ALLOWED_ARTIFACTS = {
    "draft": "discharge_summary_draft.md",
    "trace": "trace.json",
    "quality": "quality_report.json",
    "quality_md": "quality_report.md",
    "structured": "structured_summary.json",
    "learning": "learning_metrics.json",
    "state": "state.json",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local discharge-summary agent web dashboard.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    print(f"Discharge Summary Agent dashboard: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        print(f"[web] {self.address_string()} - {format % args}")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/"):
            self._handle_api_get(parsed.path, parse_qs(parsed.query))
            return
        self._serve_static(parsed.path)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/api/run":
            self._send_error("Not found", HTTPStatus.NOT_FOUND)
            return
        try:
            payload = self._read_request_json()
            result = run_dashboard_job(payload)
            self._send_json(result)
        except ValueError as exc:
            self._send_error(str(exc), HTTPStatus.BAD_REQUEST)
        except Exception as exc:  # noqa: BLE001 - top-level API safety boundary
            self._send_error(str(exc), HTTPStatus.INTERNAL_SERVER_ERROR)

    def _handle_api_get(self, path: str, query: dict[str, list[str]]) -> None:
        if path == "/api/health":
            self._send_json(
                {
                    "status": "ok",
                    "version": APP_VERSION,
                    "project_scope": "provided_patient_and_two_sample_patients",
                    "task_input_exists": (ROOT / "task").exists(),
                    "sample_input_exists": (ROOT / "sample_patients").exists(),
                    "artifact_keys": sorted(ALLOWED_ARTIFACTS),
                    "runs": len(list_runs()),
                }
            )
        elif path == "/api/runs":
            self._send_json({"runs": list_runs()})
        elif path == "/api/artifact":
            run_id = _one(query, "run_id")
            artifact = _one(query, "artifact")
            self._send_artifact(run_id, artifact)
        else:
            self._send_error("Not found", HTTPStatus.NOT_FOUND)

    def _send_artifact(self, run_id: str, artifact: str) -> None:
        run = next((item for item in list_runs() if item["id"] == run_id), None)
        if not run:
            self._send_error("Run not found", HTTPStatus.NOT_FOUND)
            return
        filename = ALLOWED_ARTIFACTS.get(artifact)
        if not filename:
            self._send_error("Artifact not allowed", HTTPStatus.BAD_REQUEST)
            return
        path = Path(run["output_dir"]) / filename
        if not path.exists():
            self._send_error(f"{filename} does not exist", HTTPStatus.NOT_FOUND)
            return
        if path.suffix == ".json":
            try:
                content = json.loads(path.read_text(encoding="utf-8"))
            except JSONDecodeError:
                self._send_error(f"{filename} is not valid JSON", HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            self._send_json({"artifact": artifact, "content": content})
        else:
            self._send_json({"artifact": artifact, "content": path.read_text(encoding="utf-8")})

    def _serve_static(self, path: str) -> None:
        if path in {"", "/"}:
            path = "/index.html"
        elif path == "/favicon.ico":
            path = "/favicon.svg"
        safe_name = path.lstrip("/")
        file_path = (WEB_DIR / safe_name).resolve()
        if not str(file_path).startswith(str(WEB_DIR.resolve())) or not file_path.exists():
            self._send_bytes(b"Not found", "text/plain", HTTPStatus.NOT_FOUND)
            return
        mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self._send_bytes(file_path.read_bytes(), mime)

    def _read_request_json(self) -> dict[str, Any]:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0") or "0"))
        try:
            payload = json.loads(body.decode("utf-8") or "{}")
        except JSONDecodeError as exc:
            raise ValueError("Request body must be valid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self._send_bytes(data, "application/json", status)

    def _send_error(self, message: str, status: HTTPStatus) -> None:
        self._send_json({"error": message, "status": status.phrase}, status)

    def _send_bytes(self, data: bytes, mime: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", f"{mime}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if mime == "application/json":
            self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)


def run_dashboard_job(payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode", "task")
    if mode not in {"task", "sample"}:
        raise ValueError("mode must be 'task' or 'sample'.")
    max_steps = _coerce_step_limit(payload.get("max_steps", DEFAULT_MAX_STEPS))
    learning = bool(payload.get("learning", True))
    agent = DischargeSummaryAgent(max_steps=max_steps, ocr_cache_dir=default_ocr_cache(ROOT / "outputs"))

    if mode == "task":
        summary = run_one(agent, ROOT / "task", ROOT / "outputs", learning)
        return {"mode": mode, "max_steps": max_steps, "runs": [summary], "available_runs": list_runs()}

    output_root = ROOT / "outputs_samples"
    patient_inputs = discover_patient_inputs(ROOT / "sample_patients")
    if not patient_inputs:
        raise ValueError("No sample patient PDFs found in sample_patients.")
    runs = []
    for patient_input in patient_inputs:
        patient_output = output_root / slug(patient_input.stem if patient_input.is_file() else patient_input.name)
        runs.append(run_one(agent, patient_input, patient_output, learning))
    (output_root / "batch_index.json").write_text(json.dumps(runs, indent=2), encoding="utf-8")
    return {"mode": mode, "max_steps": max_steps, "runs": runs, "available_runs": list_runs()}


def list_runs() -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    if (ROOT / "outputs" / "quality_report.json").exists():
        runs.append(_run_metadata("provided", "Provided patient source notes", ROOT / "outputs"))
    sample_root = ROOT / "outputs_samples"
    if sample_root.exists():
        for child in sorted(sample_root.iterdir()):
            if child.is_dir() and (child / "quality_report.json").exists():
                runs.append(_run_metadata(f"sample/{child.name}", f"Sample: {child.name.replace('-', ' ')}", child))
    return runs


def _run_metadata(run_id: str, label: str, output_dir: Path) -> dict[str, Any]:
    quality = _read_json(output_dir / "quality_report.json")
    learning = _read_json(output_dir / "learning_metrics.json")
    required = quality.get("required_fields", {})
    medications = quality.get("medications", {})
    return {
        "id": run_id,
        "label": label,
        "output_dir": str(output_dir),
        "status": "ready",
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
        }
        if learning
        else None,
    }


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _coerce_step_limit(raw_value: Any) -> int:
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValueError("max_steps must be an integer.") from exc
    if value < MIN_MAX_STEPS or value > MAX_MAX_STEPS:
        raise ValueError(f"max_steps must be between {MIN_MAX_STEPS} and {MAX_MAX_STEPS}.")
    return value


def _one(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or [""]
    return values[0]


if __name__ == "__main__":
    main()
