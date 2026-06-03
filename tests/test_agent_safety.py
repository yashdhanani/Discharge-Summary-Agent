from __future__ import annotations

import tempfile
import unittest
import logging
from pathlib import Path
from unittest.mock import patch

from dscribe_agent.agent import DischargeSummaryAgent, render_markdown
from dscribe_agent.extractors import (
    detect_conflicts,
    extract_admission_meds,
    extract_discharge_meds,
    extract_pending_results,
    extract_summary_fields,
    reconcile_medications,
)
from dscribe_agent.models import AgentState, DocumentPage, Evidence, Field
from dscribe_agent.pdf_ingest import find_patient_pdfs, read_pdf_pages
from dscribe_agent.web_app import ALLOWED_ARTIFACTS, list_runs


class AgentSafetyTests(unittest.TestCase):
    def test_typed_note_extraction_and_reconciliation(self) -> None:
        pages = [
            DocumentPage(
                "typed.pdf",
                1,
                "\n".join(
                    [
                        "Patient: Maya Rao, 54-year-old female",
                        "Admission Date: 2026-01-10",
                        "Discharge Date: 2026-01-13",
                        "Principal Diagnosis: Community acquired pneumonia",
                        "Secondary Diagnoses: Type 2 diabetes mellitus; hypertension",
                        "Allergies: No known drug allergies",
                        "Hospital Course: Patient admitted with fever and hypoxia. Treated with IV antibiotics.",
                        "Admission Medications: Metformin 500MG BD; Amlodipine 5MG OD",
                        "Advice on Discharge:",
                        "TAB AMOXICILLIN 500MG TDS 5 DAYS",
                        "TAB METFORMIN 500MG BD 30 DAYS",
                        "TAB AMLODIPINE 5MG OD 30 DAYS",
                        "Pending Results: None documented.",
                        "Discharge Condition: Stable on room air.",
                    ]
                ),
            )
        ]

        summary = extract_summary_fields(pages)
        self.assertEqual(summary["patient_demographics"].value, "Maya Rao, 54-year-old female")
        self.assertEqual(summary["admission_date"].value, "2026-01-10")
        self.assertEqual(summary["principal_diagnosis"].value, "Community-acquired pneumonia")

        discharge = extract_discharge_meds(pages)
        admission = extract_admission_meds(pages)
        reconciled = reconcile_medications(admission, discharge)
        by_name = {row["medication"]: row for row in reconciled}
        self.assertEqual(by_name["METFORMIN"]["status"], "continued/changed")
        self.assertEqual(by_name["AMLODIPINE"]["status"], "continued/changed")
        self.assertEqual(extract_pending_results(pages)[0].value, "None documented.")

    def test_medication_attributes_do_not_leak_between_rows(self) -> None:
        pages = [
            DocumentPage(
                "meds.pdf",
                1,
                "\n".join(
                    [
                        "Advice on Discharge:",
                        "TAB OFLOX TZ 1-0-1 5 DAYS",
                        "TAB LOPERAMIDE 2MG SOS 3 DAYS",
                    ]
                ),
            )
        ]

        meds = {med.name: med for med in extract_discharge_meds(pages)}
        self.assertEqual(meds["OFLOX TZ"].dose, "MISSING")
        self.assertIn("Dose not reliably sourced.", meds["OFLOX TZ"].flags)
        self.assertEqual(meds["LOPERAMIDE"].dose, "2MG")

    def test_conflict_detection_surfaces_competing_principal_diagnoses(self) -> None:
        pages = [
            DocumentPage(
                "conflict.pdf",
                1,
                "\n".join(
                    [
                        "Principal Diagnosis: Acute gastroenteritis with dehydration",
                        "Progress Note: Assessment lists urinary tract infection after urine routine showed pyuria.",
                        "Secondary Diagnoses: Acute kidney injury, improved",
                    ]
                ),
            )
        ]

        conflicts = detect_conflicts(pages)
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(
            conflicts[0]["values"],
            ["Acute gastroenteritis with dehydration", "Urinary tract infection"],
        )

    def test_no_fabrication_guardrail_downgrades_unsupported_fields(self) -> None:
        state = AgentState(
            summary={
                "principal_diagnosis": Field("Pneumonia", "supported"),
                "allergies": Field(
                    "No known drug allergies",
                    "supported",
                    evidence=[Evidence("note.pdf", 1, "Allergies: No known drug allergies")],
                ),
            }
        )

        result = DischargeSummaryAgent()._validate_no_fabrication(state)
        self.assertIn("downgraded 1", result)
        self.assertEqual(state.summary["principal_diagnosis"].status, "uncertain")
        self.assertEqual(state.summary["allergies"].status, "supported")

    def test_short_text_pdf_does_not_trigger_ocr_warning(self) -> None:
        from scripts.make_synthetic_patients import write_pdf

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "short.pdf"
            write_pdf(
                pdf,
                [
                    "Patient: Demo Patient, 40-year-old female",
                    "Admission Date: 2026-01-01",
                    "Discharge Date: 2026-01-02",
                    "Principal Diagnosis: Community acquired pneumonia",
                    "Advice on Discharge:",
                    "TAB AMOXICILLIN 500MG TDS 5 DAYS",
                ],
            )
            pages, warnings = read_pdf_pages(pdf, None)
            self.assertGreater(sum(len(page.text) for page in pages), 150)
            self.assertEqual(warnings, [])

    def test_non_task_folder_keeps_assignment_named_patient_pdf(self) -> None:
        from scripts.make_synthetic_patients import write_pdf

        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "source-notes"
            task_dir = Path(tmp) / "task"
            source_dir.mkdir()
            task_dir.mkdir()
            source_pdf = source_dir / "assignment_patient_notes.pdf"
            task_brief = task_dir / "assignment_brief.pdf"
            task_patient = task_dir / "patient_notes.pdf"
            write_pdf(source_pdf, ["Patient: Source Patient", "Principal Diagnosis: Pneumonia"])
            write_pdf(task_brief, ["Assignment instructions"])
            write_pdf(task_patient, ["Patient: Task Patient", "Principal Diagnosis: Pneumonia"])

            self.assertEqual(find_patient_pdfs(source_dir), [source_pdf])
            self.assertEqual(find_patient_pdfs(task_dir), [task_patient])

    def test_corrupted_pdf_fails_safely(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "broken.pdf"
            pdf.write_bytes(b"not a real pdf")
            logger = logging.getLogger("pypdf")
            previous_level = logger.level
            logger.setLevel(logging.CRITICAL)
            with patch("dscribe_agent.pdf_ingest._macos_vision_ocr", return_value=None):
                try:
                    pages, warnings = read_pdf_pages(pdf, None)
                finally:
                    logger.setLevel(previous_level)

            self.assertEqual(pages, [])
            self.assertTrue(any("could not be opened as a PDF" in warning for warning in warnings))
            self.assertTrue(any("OCR fallback unavailable or empty" in warning for warning in warnings))

    def test_non_clinical_pdf_produces_safe_missing_draft(self) -> None:
        from scripts.make_synthetic_patients import write_pdf

        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "general_report.pdf"
            write_pdf(
                pdf,
                [
                    "Quarterly Operations Report",
                    "This document discusses staffing, billing, and facility maintenance.",
                    "It intentionally contains no patient demographics, diagnosis, medications, or discharge plan.",
                ],
            )
            state = DischargeSummaryAgent().run(pdf)
            draft = render_markdown(state)

            self.assertIn("MISSING", draft)
            self.assertIn("DRAFT FOR CLINICIAN REVIEW", draft)
            self.assertEqual(state.summary["patient_demographics"].status, "missing")
            self.assertEqual(state.summary["principal_diagnosis"].status, "missing")

    def test_web_dashboard_lists_safe_artifacts(self) -> None:
        self.assertIn("draft", ALLOWED_ARTIFACTS)
        self.assertIn("trace", ALLOWED_ARTIFACTS)
        self.assertIn("quality", ALLOWED_ARTIFACTS)
        runs = list_runs()
        self.assertIsInstance(runs, list)
        if Path("outputs/quality_report.json").exists():
            self.assertTrue(any(run["id"] == "provided" for run in runs))


if __name__ == "__main__":
    unittest.main()
