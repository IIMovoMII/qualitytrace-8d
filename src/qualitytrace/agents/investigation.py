from __future__ import annotations

from ..models import CaseRecord, CandidateRootCause, EvidenceUnit
from ..tools import ReadTools, propose_root_causes


def investigate_root_causes(case: CaseRecord, evidence: list[EvidenceUnit]) -> list[CandidateRootCause]:
    tools = ReadTools(case)
    comparison = tools.compare_spec_and_measurement(evidence)
    return propose_root_causes(case, evidence, comparison)
