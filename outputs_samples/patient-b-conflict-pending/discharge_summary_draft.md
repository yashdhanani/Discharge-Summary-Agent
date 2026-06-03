# Discharge Summary Draft

Status: DRAFT FOR CLINICIAN REVIEW. Do not finalize without human verification.

## Required Sections
### Patient Demographics
- SUPPORTED: Nisha Patel, 38-year-old female

### Admission Date
- SUPPORTED: 2026-02-04

### Discharge Date
- MISSING: MISSING
- REVIEW: Discharge date not reliably found.

### Principal Diagnosis
- SUPPORTED: Acute gastroenteritis with dehydration

### Secondary Diagnoses
- Urinary tract infection
- Acute kidney injury

### Hospital Course
- SUPPORTED: Hospital Course: Patient presented with loose stools, vomiting, fever, and dysuria. Initial creatinine was elevated and improved after IV fluids. Urine culture and sensitivity was sent; report awaited at discharge. Admission Medications: Thyroxine 50MCG OD

### Procedures
- MISSING: []
- REVIEW: No procedures explicitly documented.

### Allergies
- MISSING: MISSING
- REVIEW: Allergy status not reliably documented.

### Follow Up Instructions
- SUPPORTED: Follow-up Instructions: Review immediately for fever, worsening loose stools, vomiting, fatigue, reduced urine output, or abdominal pain. Review urine culture when available.

### Discharge Condition
- SUPPORTED: Stable at request discharge, but final discharge date was not documented in the source note.

## Discharge Medications
- OFLOX TZ: dose=MISSING; frequency=1-0-1; duration=5 DAYS
  - REVIEW: Dose not reliably sourced.
- LOPERAMIDE: dose=2MG; frequency=SOS; duration=3 DAYS
- METRONIDAZOLE: dose=400MG; frequency=TDS; duration=5 DAYS

## Medication Reconciliation
- OFLOX TZ: added_at_discharge_or_not_seen_on_admission
  - REVIEW: Dose not reliably sourced.
  - REVIEW: No clear matching admission medication found; reconcile indication/reason.
- LOPERAMIDE: added_at_discharge_or_not_seen_on_admission
  - REVIEW: No clear matching admission medication found; reconcile indication/reason.
- METRONIDAZOLE: added_at_discharge_or_not_seen_on_admission
  - REVIEW: No clear matching admission medication found; reconcile indication/reason.
- THYROXINE: stopped_or_not_on_discharge_list
  - REVIEW: Medication appears in admission/inpatient source but not discharge list; clinician reconciliation required.

## Pending Results
- SUPPORTED: sensitivity was sent; report awaited at discharge.
- SUPPORTED: Urine culture and sensitivity report awaited.

## Conflicts And Review Flags
- diagnosis: Multiple diagnosis statements found; agent did not collapse them into one unsupported final answer. Values: ['Acute gastroenteritis with dehydration', 'Urinary tract infection']
- CLINICIAN_REVIEW: Medication reconciliation: LOPERAMIDE - No clear matching admission medication found; reconcile indication/reason.
- CLINICIAN_REVIEW: Medication reconciliation: METRONIDAZOLE - No clear matching admission medication found; reconcile indication/reason.
- CLINICIAN_REVIEW: Medication reconciliation: OFLOX TZ - Dose not reliably sourced.; No clear matching admission medication found; reconcile indication/reason.
- CLINICIAN_REVIEW: Medication reconciliation: THYROXINE - Medication appears in admission/inpatient source but not discharge list; clinician reconciliation required.
- CLINICIAN_REVIEW: Metronidazole-like medication found; confirm alcohol avoidance counseling and indication.
- CLINICIAN_REVIEW: Multiple diagnosis statements found; agent did not collapse them into one unsupported final answer.
- CLINICIAN_REVIEW: Potential QT/CNS safety concern: quinolone antibiotic plus loperamide-like antidiarrheal; clinician review recommended.
- CLINICIAN_REVIEW: allergies is missing or uncertain.
- CLINICIAN_REVIEW: discharge_date is missing or uncertain.
- CLINICIAN_REVIEW: procedures is missing or uncertain.

## Evidence Notes
- patient_demographics: source_notes.pdf p1 - Patient: Nisha Patel, 38-year-old female
- admission_date: source_notes.pdf p1 - Admission Date: 2026-02-04
- principal_diagnosis: source_notes.pdf p1 - Acute gastroenteritis with dehydration
- secondary_diagnoses: source_notes.pdf p1 - Urinary tract infection
- hospital_course: source_notes.pdf p1 - Hospital Course: Patient presented with loose stools, vomiting, fever, and dysuria. Initial creatinine was elevated and improved after IV fluids. Urine culture and sensitivity was sent; report awaited at discharge. Admis
- follow_up_instructions: source_notes.pdf p1 - Follow-up Instructions: Review immediately for fever, worsening loose stools, vomiting, fatigue, reduced urine output, or abdominal pain. Review urine culture when available.
- discharge_condition: source_notes.pdf p1 - Discharge Condition: Stable at request discharge, but final discharge date was not
- discharge_medication.OFLOX TZ: source_notes.pdf p1 - TAB OFLOX TZ 1-0-1 5 DAYS
- discharge_medication.LOPERAMIDE: source_notes.pdf p1 - TAB LOPERAMIDE 2MG SOS 3 DAYS
- discharge_medication.METRONIDAZOLE: source_notes.pdf p1 - TAB METRONIDAZOLE 400MG TDS 5 DAYS