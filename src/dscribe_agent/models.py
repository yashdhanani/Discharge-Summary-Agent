from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Evidence:
    source: str
    page: int
    text: str


@dataclass
class Field:
    value: Any
    status: str = "supported"
    evidence: list[Evidence] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class Medication:
    name: str
    dose: str = "MISSING"
    frequency: str = "MISSING"
    duration: str = "MISSING"
    source: str = "discharge"
    status: str = "supported"
    evidence: list[Evidence] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class DocumentPage:
    source: str
    page: int
    text: str


@dataclass
class AgentState:
    pages: list[DocumentPage] = field(default_factory=list)
    summary: dict[str, Field] = field(default_factory=dict)
    discharge_meds: list[Medication] = field(default_factory=list)
    admission_meds: list[Medication] = field(default_factory=list)
    med_reconciliation: list[dict[str, Any]] = field(default_factory=list)
    pending_results: list[Field] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    escalations: list[str] = field(default_factory=list)
    trace: list[dict[str, Any]] = field(default_factory=list)
