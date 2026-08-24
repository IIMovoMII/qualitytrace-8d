from __future__ import annotations

from ..models import CaseRecord, CandidateRootCause, CorrectiveAction
from ..tools import draft_action


def draft_corrective_action(case: CaseRecord, causes: list[CandidateRootCause]) -> CorrectiveAction:
    return draft_action(case, causes)
