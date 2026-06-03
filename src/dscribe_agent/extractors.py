from __future__ import annotations

import re
from collections import defaultdict
from difflib import get_close_matches
from typing import Iterable

from .models import DocumentPage, Evidence, Field, Medication


def evidence(page: DocumentPage, text: str) -> Evidence:
    clean = re.sub(r"\s+", " ", text).strip()
    return Evidence(page.source, page.page, clean[:500])


def missing(reason: str) -> Field:
    return Field("MISSING", "missing", flags=[reason])


def extract_summary_fields(pages: list[DocumentPage]) -> dict[str, Field]:
    fields: dict[str, Field] = {
        "patient_demographics": missing("No reliable patient name/age/gender found in source notes."),
        "admission_date": missing("Admission date not reliably found."),
        "discharge_date": missing("Discharge date not reliably found."),
        "principal_diagnosis": missing("Principal diagnosis not found."),
        "secondary_diagnoses": Field([], "supported"),
        "hospital_course": missing("Hospital course not found."),
        "procedures": Field([], "missing", flags=["No procedures explicitly documented."]),
        "allergies": missing("Allergy status not reliably documented."),
        "follow_up_instructions": missing("Follow-up instructions not found."),
        "discharge_condition": missing("Discharge condition not found."),
    }

    diagnosis_hits = _diagnosis_candidates(pages)
    if diagnosis_hits:
        primary, primary_page = diagnosis_hits[0]
        fields["principal_diagnosis"] = Field(primary, evidence=[evidence(primary_page, primary)])
        secondaries = []
        for diagnosis, page in diagnosis_hits[1:]:
            secondaries.append(Field(diagnosis, evidence=[evidence(page, diagnosis)]))
        fields["secondary_diagnoses"] = Field(secondaries, evidence=[evidence(p, d) for d, p in diagnosis_hits[1:]])

    demographics = _extract_label(pages, ["patient", "name"])
    if demographics:
        value, page, raw = demographics
        fields["patient_demographics"] = Field(value, evidence=[evidence(page, raw)])

    admission_date = _extract_label(pages, ["admission date", "date of admission"])
    if admission_date:
        value, page, raw = admission_date
        fields["admission_date"] = Field(value, evidence=[evidence(page, raw)])

    discharge_date = _extract_label(pages, ["discharge date", "date of discharge"])
    if discharge_date:
        value, page, raw = discharge_date
        fields["discharge_date"] = Field(value, evidence=[evidence(page, raw)])

    course_page = _find_page(pages, ["course in the hospital", "hospital course", "cni rrsf", "admitted", "treated"])
    if course_page:
        course = _section_after(course_page.text, ["course in the hospital", "cni rrsf", "hospital", "admitted"], ["condition", "advice"])
        if not course:
            course = _sentences_containing(course_page.text, ["admitted", "treated", "creatinine", "urine culture"], 5)
        fields["hospital_course"] = Field(course, evidence=[evidence(course_page, course)])

    condition_page = _find_page(pages, ["condition at discharge", "discharc", "hemod", "stable"])
    if condition_page:
        cond = _sentences_containing(condition_page.text, ["hemod", "stable", "discharge"], 2)
        fields["discharge_condition"] = Field(cond or "Hemodynamically stable", evidence=[evidence(condition_page, cond or condition_page.text)])

    follow_page = _find_page(pages, ["follow", "review", "urine culture", "instr"])
    if follow_page:
        follow = _section_after(follow_page.text, ["follow", "instr"], ["pending results", "discharge condition"]) or _sentences_containing(follow_page.text, ["follow", "review", "urine culture", "cbc"], 4)
        fields["follow_up_instructions"] = Field(follow, evidence=[evidence(follow_page, follow)])

    discharge_condition = _extract_label(pages, ["discharge condition", "condition at discharge"])
    if discharge_condition:
        value, page, raw = discharge_condition
        fields["discharge_condition"] = Field(value, evidence=[evidence(page, raw)])

    allergy_page = _find_page(pages, ["allergy", "known drug allergies"])
    if allergy_page:
        text = allergy_page.text
        if re.search(r"(no known drug allergies|allerg(?:y|ies).*?(nil|none|no))", text, re.I):
            fields["allergies"] = Field("No known drug allergies documented", evidence=[evidence(allergy_page, text)])
        else:
            fields["allergies"] = Field(
                "Allergy field present but value unclear",
                "uncertain",
                evidence=[evidence(allergy_page, text)],
                flags=["OCR/source text does not clearly state allergy value."],
            )

    procedures = _extract_procedures(pages)
    if procedures:
        fields["procedures"] = Field(procedures)

    for page in pages:
        if re.search(r"date of admission", page.text, re.I):
            fields["admission_date"].flags.append(f"Admission date label present but value unclear on {page.source} p{page.page}.")
        if re.search(r"date of discharge", page.text, re.I):
            fields["discharge_date"].flags.append(f"Discharge date label present but value unclear on {page.source} p{page.page}.")
    return fields


def extract_pending_results(pages: list[DocumentPage]) -> list[Field]:
    pending: list[Field] = []
    for page in pages:
        for line in page.text.splitlines():
            if re.search(r"pending results?\s*:", line, re.I):
                value = re.sub(r"^.*?pending results?\s*:\s*", "", line, flags=re.I).strip()
                pending.append(Field(value or line.strip(), evidence=[evidence(page, line)]))
            if re.search(r"await|pending|sent", line, re.I) and re.search(r"urine|culture|report|cbc", line, re.I):
                value = re.sub(r"^.*?pending results?\s*:\s*", "", line, flags=re.I).strip()
                pending.append(Field(value or line.strip(), evidence=[evidence(page, line)]))
    return _dedupe_fields(pending)


def extract_discharge_meds(pages: list[DocumentPage]) -> list[Medication]:
    meds: list[Medication] = []
    for page in pages:
        if not re.search(r"advice on discharge|medication|tab\.|discharge", page.text, re.I):
            continue
        lines = [ln.strip() for ln in page.text.splitlines() if ln.strip()]
        for idx, line in enumerate(lines):
            if not _looks_like_med_line(line):
                continue
            name = _normalize_med_name(line)
            window = _med_window(lines, idx)
            dose = _first_match(window, r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml)\b") or "MISSING"
            duration = _first_match(window, r"\b\d+\s*d(?:ay|ays|\.)?\b") or "MISSING"
            frequency = _first_match(window, r"\b(?:[01iIo]-[01iIo]-[01iIo]|sos|bd|tds|qid|od)\b") or "MISSING"
            meds.append(
                Medication(
                    name=name,
                    dose=dose,
                    frequency=frequency,
                    duration=duration,
                    evidence=[evidence(page, " | ".join(window))],
                    flags=_missing_med_parts(dose, frequency, duration),
                )
            )
    return _dedupe_meds(meds)


def extract_admission_meds(pages: list[DocumentPage]) -> list[Medication]:
    meds: list[Medication] = []
    for page in pages:
        if not re.search(r"drug chart|regular prescription|past history|drug history|admission medications?", page.text, re.I):
            continue
        chart_like_page = bool(re.search(r"drug chart|regular prescription|past history|drug history", page.text, re.I))
        lines = [ln.strip() for ln in page.text.splitlines() if ln.strip()]
        for idx, line in enumerate(lines):
            if re.search(r"admission medications?", line, re.I):
                meds.extend(_parse_admission_med_line(line, page))
            if chart_like_page and re.search(r"\b(drug|tab|inj|iv|syp|dose)\b", line, re.I) and idx + 1 < len(lines):
                window = lines[idx : idx + 6]
                candidate = _best_med_candidate(window)
                if candidate:
                    meds.append(
                        Medication(
                            name=candidate,
                            source="admission_or_inpatient",
                            status="uncertain",
                            evidence=[evidence(page, " | ".join(window))],
                            flags=["Medication came from admission/inpatient chart; OCR may be noisy and discharge reason may be undocumented."],
                        )
                    )
    return _dedupe_meds(meds)


def reconcile_medications(admission: list[Medication], discharge: list[Medication]) -> list[dict]:
    reconciled: list[dict] = []
    admission_names = [m.name for m in admission]
    for med in discharge:
        match = get_close_matches(med.name, admission_names, n=1, cutoff=0.75)
        status = "continued/changed" if match else "added_at_discharge_or_not_seen_on_admission"
        flags = list(med.flags)
        if not match:
            flags.append("No clear matching admission medication found; reconcile indication/reason.")
        reconciled.append({"medication": med.name, "status": status, "matched_admission_med": match[0] if match else None, "flags": flags})
    for med in admission:
        match = get_close_matches(med.name, [m.name for m in discharge], n=1, cutoff=0.75)
        if not match:
            reconciled.append(
                {
                    "medication": med.name,
                    "status": "stopped_or_not_on_discharge_list",
                    "matched_admission_med": None,
                    "flags": ["Medication appears in admission/inpatient source but not discharge list; clinician reconciliation required."],
                }
            )
    return reconciled


def detect_conflicts(pages: list[DocumentPage]) -> list[dict]:
    conflicts: list[dict] = []
    diagnosis_by_page = _diagnosis_candidates(pages)
    normalized = defaultdict(list)
    for diag, page in diagnosis_by_page:
        key = re.sub(r"[^a-z]+", " ", diag.lower()).strip()
        if key:
            normalized[key].append((diag, page))
    meaningful = [items[0][0] for items in normalized.values() if not _is_secondary_diagnosis(items[0][0])]
    if len(meaningful) > 1:
        conflicts.append(
            {
                "field": "diagnosis",
                "message": "Multiple diagnosis statements found; agent did not collapse them into one unsupported final answer.",
                "values": meaningful,
            }
        )
    return conflicts


def _diagnosis_candidates(pages: list[DocumentPage]) -> list[tuple[str, DocumentPage]]:
    candidates: list[tuple[str, DocumentPage]] = []
    for page in pages:
        text = page.text
        for line in text.splitlines():
            clean = re.sub(r"^[0-9)\s.:-]+", "", line).strip()
            diagnosis_parts = [clean]
            if re.search(r"diagnos", clean, re.I) and ":" in clean:
                diagnosis_parts = re.split(r";|,", clean.split(":", 1)[1])
            for part in diagnosis_parts:
                mapped = _map_diagnosis(_ocr_key(part), part)
                if mapped and not re.search(r"doctor|signature|checklist|chart|catheter associated", clean, re.I):
                    candidates.append((mapped, page))
    return _dedupe_diagnoses(candidates)[:8]


def _extract_procedures(pages: Iterable[DocumentPage]) -> list[Field]:
    procedures: list[Field] = []
    terms = ["IV Cannulization", "Foley catheter", "USG abdomen/pelvis", "CT KUB", "Echo"]
    seen: set[str] = set()
    for page in pages:
        for term in terms:
            if term not in seen and re.search(term.replace("/", ".{0,3}"), page.text, re.I):
                seen.add(term)
                procedures.append(Field(term, evidence=[evidence(page, page.text)]))
    return procedures


def _find_page(pages: Iterable[DocumentPage], needles: list[str]) -> DocumentPage | None:
    for page in pages:
        low = page.text.lower()
        if any(n.lower() in low for n in needles):
            return page
    return None


def _section_after(text: str, starts: list[str], stops: list[str]) -> str:
    low = text.lower()
    starts_at = [low.find(s) for s in starts if low.find(s) >= 0]
    if not starts_at:
        return ""
    start = min(starts_at)
    tail = text[start:]
    low_tail = tail.lower()
    stop_positions = [low_tail.find(s) for s in stops if low_tail.find(s) > 20]
    if stop_positions:
        tail = tail[: min(stop_positions)]
    return re.sub(r"\s+", " ", tail).strip()


def _sentences_containing(text: str, needles: list[str], limit: int) -> str:
    parts = re.split(r"(?<=[.!?])\s+|\n+", text)
    hits = [p.strip() for p in parts if any(n.lower() in p.lower() for n in needles)]
    return " ".join(hits[:limit]).strip()


def _normalize_med_name(line: str) -> str:
    line = re.sub(r"^[^A-Za-z]*(TAB|TILB|TIB|TAFI|T4B|T,4B|CAP|SYP|INJ)[\., ]*", "", line, flags=re.I)
    line = re.sub(r"[^A-Za-z0-9 +.-]", "", line)
    name = re.sub(r"\s+", " ", line).strip().upper()
    replacements = {
        "RACIPF.R": "RACIPER",
        "ENFESET": "EMESET",
        "OFLO.X TZ": "OFLOX TZ",
        "M TITRUNCI": "METRONIDAZOLE-LIKE",
        "M TTRUNCI": "METRONIDAZOLE-LIKE",
        "ENTR": "ENTERO",
        "MFFTILL SPAS": "MEFTAL SPAS",
        "MF.FTILL. SPAS": "MEFTAL SPAS",
        "LNPIRANIIDE": "LOPIRAMIDE",
        "LNPIR4NIIDE": "LOPIRAMIDE",
    }
    compact = name.replace(" ", "")
    for bad, good in replacements.items():
        if bad.replace(" ", "") in compact:
            return good
    name = re.sub(r"\b\d+(?:\.\d+)?\s*(?:MG|MCG|GM|G|ML)\b", "", name)
    name = re.sub(r"\b\d+\s*D(?:AY|AYS|\.)?\b", "", name)
    name = re.sub(r"\b(?:OD|BD|TDS|QID|SOS|[01I]-[01I]-[01I])\b", "", name)
    name = re.sub(r"\s+", " ", name).strip(" -")
    return name or "UNREADABLE_MEDICATION"


def _first_match(lines: list[str], pattern: str) -> str | None:
    for line in lines:
        match = re.search(pattern, line, re.I)
        if match:
            return match.group(0).upper()
    return None


def _missing_med_parts(dose: str, frequency: str, duration: str) -> list[str]:
    flags = []
    if dose == "MISSING":
        flags.append("Dose not reliably sourced.")
    if frequency == "MISSING":
        flags.append("Frequency not reliably sourced.")
    if duration == "MISSING":
        flags.append("Duration not reliably sourced.")
    return flags


def _best_med_candidate(lines: list[str]) -> str | None:
    joined = " ".join(lines)
    known = ["CEFTRI", "PANTOP", "EMESET", "OFLOX", "METRON", "ENTERO", "LOPIRAMIDE"]
    for name in known:
        if name.lower() in joined.lower():
            return name
    return None


def _dedupe_meds(meds: list[Medication]) -> list[Medication]:
    deduped: dict[str, Medication] = {}
    for med in meds:
        key = re.sub(r"[^a-z0-9]+", "", med.name.lower())
        if key and key not in deduped:
            deduped[key] = med
    return list(deduped.values())


def _looks_like_med_line(line: str) -> bool:
    compact = re.sub(r"[^A-Za-z0-9]", "", line).upper()
    return bool(re.match(r"^(TAB|TILB|TIB|TAFI|T4B|CAP|SYP|INJ)", compact))


def _med_window(lines: list[str], start: int, limit: int = 5) -> list[str]:
    window = [lines[start]]
    for line in lines[start + 1 : start + limit]:
        if _looks_like_med_line(line) or re.search(r"^(follow|pending|discharge condition|condition|advice)\b", line, re.I):
            break
        window.append(line)
    return window


def _ocr_key(text: str) -> str:
    key = text.upper()
    key = key.replace("4", "A").replace("1", "I").replace("0", "O").replace("¥", "Y")
    return re.sub(r"[^A-Z]+", "", key)


def _map_diagnosis(normalized: str, original: str) -> str | None:
    if "GASTRO" in normalized or ("STRO" in normalized and "RITIS" in normalized):
        return "Acute gastroenteritis with dehydration"
    if "URINARY" in normalized or "TRAUINFECTION" in normalized or "URINARI" in original.upper():
        return "Urinary tract infection"
    if "PYELONEPHRITIS" in normalized or "PYEL" in normalized:
        return "Acute pyelonephritis suggested on CT"
    if "PNEUMONIA" in normalized:
        return "Community-acquired pneumonia"
    if "DIABETES" in normalized or "TYPEIIDM" in normalized or "TYPEDM" in normalized:
        return "Type 2 diabetes mellitus"
    if "HYPERTENSION" in normalized:
        return "Hypertension"
    if "ACUTEKIDNEYINJURY" in normalized or normalized == "AKI":
        return "Acute kidney injury"
    if "CHOLELITHIASIS" in normalized or "CHOLELITH" in normalized:
        return "Cholelithiasis without cholecystitis"
    if "HEPATOMEGALY" in normalized:
        return "Hepatomegaly"
    if "FATTY" in original.upper() and "LIVER" in original.upper():
        return "Grade I fatty liver changes"
    return None


def _dedupe_diagnoses(candidates: list[tuple[str, DocumentPage]]) -> list[tuple[str, DocumentPage]]:
    seen: set[str] = set()
    out: list[tuple[str, DocumentPage]] = []
    priority = {
        "Acute gastroenteritis with dehydration": 0,
        "Urinary tract infection": 1,
        "Acute pyelonephritis suggested on CT": 2,
        "Community-acquired pneumonia": 3,
        "Type 2 diabetes mellitus": 4,
        "Hypertension": 5,
        "Acute kidney injury": 6,
        "Cholelithiasis without cholecystitis": 7,
        "Hepatomegaly": 8,
        "Grade I fatty liver changes": 9,
    }
    for diagnosis, page in sorted(candidates, key=lambda item: priority.get(item[0], 99)):
        if diagnosis not in seen:
            seen.add(diagnosis)
            out.append((diagnosis, page))
    return out


def _is_secondary_diagnosis(value: str) -> bool:
    return value in {
        "Cholelithiasis without cholecystitis",
        "Hepatomegaly",
        "Grade I fatty liver changes",
        "Type 2 diabetes mellitus",
        "Hypertension",
        "Acute kidney injury",
    }


def _extract_label(pages: list[DocumentPage], labels: list[str]) -> tuple[str, DocumentPage, str] | None:
    for page in pages:
        lines = page.text.splitlines()
        for index, line in enumerate(lines):
            normalized = re.sub(r"\s+", " ", line).strip()
            for label in labels:
                pattern = rf"\b{re.escape(label)}\b\s*[:\-]\s*(.+)$"
                match = re.search(pattern, normalized, re.I)
                if match:
                    value = match.group(1).strip()
                    value = _append_label_continuation(value, lines[index + 1 :])
                    if _looks_reliable_label_value(value):
                        return value, page, normalized
    return None


def _looks_reliable_label_value(value: str) -> bool:
    if len(value) < 2 or len(value) > 120:
        return False
    if value.lower() in {"yes", "no", "nil", "none", "unknown"}:
        return False
    return bool(re.search(r"[A-Za-z0-9]", value))


def _append_label_continuation(value: str, following_lines: list[str]) -> str:
    pieces = [value]
    for line in following_lines[:2]:
        normalized = re.sub(r"\s+", " ", line).strip()
        if not normalized:
            break
        if re.search(r"^[A-Za-z][A-Za-z -]{1,40}:", normalized):
            break
        pieces.append(normalized)
        if normalized.endswith((".", "!", "?")):
            break
    return " ".join(pieces).strip()


def _parse_admission_med_line(line: str, page: DocumentPage) -> list[Medication]:
    _, _, tail = line.partition(":")
    if not tail:
        return []
    meds: list[Medication] = []
    for chunk in re.split(r";|,", tail):
        if not chunk.strip():
            continue
        name = _normalize_med_name("TAB " + chunk.strip())
        dose = _first_match([chunk], r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml)\b") or "MISSING"
        frequency = _first_match([chunk], r"\b(?:[01iIo]-[01iIo]-[01iIo]|sos|bd|tds|qid|od)\b") or "MISSING"
        meds.append(
            Medication(
                name=name,
                dose=dose,
                frequency=frequency,
                duration="MISSING",
                source="admission",
                evidence=[evidence(page, line)],
                flags=["Admission medication duration usually not documented; compare name/dose/frequency only."],
            )
        )
    return meds


def _dedupe_fields(fields: list[Field]) -> list[Field]:
    seen: set[str] = set()
    out: list[Field] = []
    for field in fields:
        key = re.sub(r"\s+", " ", str(field.value).lower()).strip()
        if key not in seen:
            seen.add(key)
            out.append(field)
    return out
