from __future__ import annotations

from pathlib import Path
from textwrap import wrap


ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = ROOT / "sample_patients"


PATIENTS = {
    "patient-a-clean": [
        "Patient: Maya Rao, 54-year-old female",
        "Admission Date: 2026-01-10",
        "Discharge Date: 2026-01-13",
        "Principal Diagnosis: Community acquired pneumonia",
        "Secondary Diagnoses: Type 2 diabetes mellitus; hypertension",
        "Allergies: No known drug allergies",
        "Hospital Course: Patient admitted with fever, productive cough, and hypoxia. Chest X-ray showed right lower zone infiltrate. Treated with IV antibiotics, oxygen, and bronchodilator support. Oxygen requirement resolved by discharge.",
        "Procedures: Chest X-ray; IV cannulization",
        "Admission Medications: Metformin 500MG BD; Amlodipine 5MG OD",
        "Advice on Discharge:",
        "TAB AMOXICILLIN 500MG TDS 5 DAYS",
        "TAB METFORMIN 500MG BD 30 DAYS",
        "TAB AMLODIPINE 5MG OD 30 DAYS",
        "TAB PANTOPRAZOLE 40MG OD 7 DAYS",
        "Follow-up Instructions: Review with physician in 7 days. Return earlier for fever, breathlessness, chest pain, or persistent vomiting.",
        "Pending Results: None documented.",
        "Discharge Condition: Hemodynamically stable, maintaining saturation on room air.",
    ],
    "patient-b-conflict-pending": [
        "Patient: Nisha Patel, 38-year-old female",
        "Admission Date: 2026-02-04",
        "Principal Diagnosis: Acute gastroenteritis with dehydration",
        "Progress Note: Assessment lists urinary tract infection after urine routine showed pyuria. This conflicts with the admission diagnosis and should be flagged rather than merged silently.",
        "Secondary Diagnoses: Acute kidney injury, improved",
        "Allergies: Unknown",
        "Hospital Course: Patient presented with loose stools, vomiting, fever, and dysuria. Initial creatinine was elevated and improved after IV fluids. Urine culture and sensitivity was sent; report awaited at discharge.",
        "Admission Medications: Thyroxine 50MCG OD",
        "Advice on Discharge:",
        "TAB OFLOX TZ 1-0-1 5 DAYS",
        "TAB LOPERAMIDE 2MG SOS 3 DAYS",
        "TAB METRONIDAZOLE 400MG TDS 5 DAYS",
        "Follow-up Instructions: Review immediately for fever, worsening loose stools, vomiting, fatigue, reduced urine output, or abdominal pain. Review urine culture when available.",
        "Pending Results: Urine culture and sensitivity report awaited.",
        "Discharge Condition: Stable at request discharge, but final discharge date was not documented in the source note.",
    ],
}


def main() -> None:
    for patient_id, lines in PATIENTS.items():
        folder = SAMPLE_DIR / patient_id
        folder.mkdir(parents=True, exist_ok=True)
        write_pdf(folder / "source_notes.pdf", lines)
        (folder / "source_notes.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"Wrote {folder / 'source_notes.pdf'}")


def write_pdf(path: Path, lines: list[str]) -> None:
    wrapped_lines: list[str] = []
    for line in lines:
        wrapped_lines.extend(wrap(line, width=88) or [""])
    pages = [wrapped_lines[i : i + 52] for i in range(0, len(wrapped_lines), 52)]

    objects: list[bytes] = []
    page_object_numbers: list[int] = []
    catalog_obj = 1
    pages_obj = 2
    font_obj = 3
    next_obj = 4

    for page_lines in pages:
        page_obj = next_obj
        content_obj = next_obj + 1
        next_obj += 2
        page_object_numbers.append(page_obj)
        stream = _page_stream(page_lines)
        objects.append(
            f"{page_obj} 0 obj\n"
            f"<< /Type /Page /Parent {pages_obj} 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> /Contents {content_obj} 0 R >>\n"
            "endobj\n".encode("latin-1")
        )
        objects.append(
            f"{content_obj} 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
            + stream
            + b"\nendstream\nendobj\n"
        )

    header_objects = [
        f"{catalog_obj} 0 obj\n<< /Type /Catalog /Pages {pages_obj} 0 R >>\nendobj\n".encode("latin-1"),
        (
            f"{pages_obj} 0 obj\n<< /Type /Pages /Kids "
            f"[{' '.join(f'{n} 0 R' for n in page_object_numbers)}] /Count {len(page_object_numbers)} >>\nendobj\n"
        ).encode("latin-1"),
        f"{font_obj} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n".encode("latin-1"),
    ]
    all_objects = header_objects + objects

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for obj in all_objects:
        offsets.append(len(output))
        output.extend(obj)
    xref_at = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n".encode("latin-1"))
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root {catalog_obj} 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n".encode("latin-1")
    )
    path.write_bytes(bytes(output))


def _page_stream(lines: list[str]) -> bytes:
    commands = ["BT", "/F1 10 Tf", "50 750 Td", "14 TL"]
    for line in lines:
        commands.append(f"({_escape_pdf_text(line)}) Tj")
        commands.append("T*")
    commands.append("ET")
    return "\n".join(commands).encode("latin-1", errors="replace")


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


if __name__ == "__main__":
    main()
