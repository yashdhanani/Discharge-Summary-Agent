from __future__ import annotations

from typing import Iterable


def drug_interaction_lookup(medication_names: Iterable[str]) -> list[str]:
    names = {name.lower() for name in medication_names}
    alerts: list[str] = []
    quinolone = any("oflox" in n or "cipro" in n or "levo" in n for n in names)
    loperamide = any("lopir" in n or "loperamide" in n for n in names)
    if quinolone and loperamide:
        alerts.append(
            "Potential QT/CNS safety concern: quinolone antibiotic plus loperamide-like antidiarrheal; clinician review recommended."
        )
    if any("metron" in n or "metrogyl" in n for n in names):
        alerts.append("Metronidazole-like medication found; confirm alcohol avoidance counseling and indication.")
    return alerts


def flag_for_clinician_review(reason: str) -> str:
    return f"CLINICIAN_REVIEW: {reason}"
