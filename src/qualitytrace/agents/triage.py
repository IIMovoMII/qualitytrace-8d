from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..models import CaseRecord, EvidenceUnit


class TriageResult(BaseModel):
    case_id: str
    risk_level: Literal["low", "medium", "high"]
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    object_consistent: bool = True


def triage_case(case: CaseRecord, evidence: list[EvidenceUnit], missing: list[str], conflicts: list[str]) -> TriageResult:
    batch = next((item for item in evidence if item.evidence_id == "EV-BATCH"), None)
    expected = case.flags.get("expected_lot_id")
    consistent = not expected or (batch is not None and batch.attributes.get("lot_id") == expected)
    risk = "high" if missing or conflicts or not consistent else "medium"
    return TriageResult(case_id=case.case_id, risk_level=risk, evidence_ids=[item.evidence_id for item in evidence], missing_evidence=missing, conflict_ids=conflicts, object_consistent=consistent)
