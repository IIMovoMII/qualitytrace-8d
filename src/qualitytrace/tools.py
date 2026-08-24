from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from .models import ActionReceipt, CaseRecord, CandidateRootCause, CorrectiveAction, EvidenceUnit, OutboxEvent
from .persistence import CheckpointStore
from .policies import workflow_rule


class ToolFailure(RuntimeError):
    pass


class ReadTools:
    def __init__(self, case: CaseRecord) -> None:
        self.case = case
        self.calls: defaultdict[str, int] = defaultdict(int)

    def inspect_evidence(self) -> list[EvidenceUnit]:
        self.calls["inspect_evidence"] += 1
        failures = int(self.case.flags.get("read_tool_failures_before_success", 0))
        if self.calls["inspect_evidence"] <= failures:
            raise ToolFailure("inspection source temporarily unavailable")
        # Effectiveness evidence belongs to a later workflow phase and must not
        # leak into the initial investigation context.
        return [item for item in self.case.evidence if item.kind != "effectiveness"]

    def compare_spec_and_measurement(self, evidence: list[EvidenceUnit]) -> dict[str, Any]:
        spec = next((item for item in evidence if item.evidence_id == "EV-SPEC"), None)
        inspection = next((item for item in evidence if item.evidence_id == "EV-INSPECTION"), None)
        if not spec or not inspection:
            return {"missing": [item for item in ("EV-SPEC", "EV-INSPECTION") if item not in {x.evidence_id for x in evidence}]}
        upper = float(spec.attributes["required"]) + float(spec.attributes["tolerance"])
        lower = float(spec.attributes["required"]) - float(spec.attributes["tolerance"])
        measured = float(inspection.attributes["measured"])
        return {"lower": lower, "upper": upper, "measured": measured, "deviation": measured - float(spec.attributes["required"]), "out_of_spec": not lower <= measured <= upper}

    def find_conflicts(self, evidence: list[EvidenceUnit]) -> list[str]:
        conflicts = self.case.flags.get("conflict_evidence_ids", [])
        return list(conflicts) if conflicts else []


def propose_root_causes(case: CaseRecord, evidence: list[EvidenceUnit], comparison: dict[str, Any]) -> list[CandidateRootCause]:
    supplier = next((item for item in evidence if item.evidence_id == "EV-SUPPLIER"), None)
    specification = next((item for item in evidence if item.evidence_id == "EV-SPEC"), None)
    if not comparison.get("out_of_spec"):
        return []
    tooling_revision = supplier.attributes.get("tooling_revision", "未知版本") if supplier else "未知版本"
    target_revision = specification.attributes.get("revision", "当前规格") if specification else "当前规格"
    return [CandidateRootCause(
        cause_id="RC-001",
        statement=f"供应商沿用 {tooling_revision} 工装，未完成 {target_revision} 规格切换，导致{case.spec_name}超过上限。",
        evidence_ids=["EV-SPEC", "EV-INSPECTION", "EV-SUPPLIER"],
        policy_ids=["QT-POL-001", "QT-POL-002", "QT-POL-004"],
        confidence="high" if supplier else "medium",
    )]


def draft_action(case: CaseRecord, causes: list[CandidateRootCause]) -> CorrectiveAction:
    specification = next(item for item in case.evidence if item.evidence_id == "EV-SPEC")
    revision = specification.attributes["revision"]
    return CorrectiveAction(
        action_version=1,
        title=f"冻结受影响批次并完成 {revision} 工装切换验证",
        owner_role="supplier_quality",
        due_days=int(workflow_rule("corrective_action_due_days")),
        steps=[
            f"隔离 {case.lot_id}，禁止直接放行",
            f"核对并切换到 {revision} 工装，保留换型记录",
            f"完成至少 {workflow_rule('minimum_effectiveness_sample_size')} 件复检并提交逐件测量记录",
        ],
        evidence_ids=sorted({e for cause in causes for e in cause.evidence_ids}),
        policy_ids=["QT-POL-003", "QT-POL-004", "QT-POL-005", "QT-POL-006"],
    )


def publish_corrective_action(store: CheckpointStore, case: CaseRecord, action: CorrectiveAction, *, approved: bool = False) -> ActionReceipt:
    if not approved:
        raise PermissionError("副作用工具必须收到已持久化的质量负责人批准")
    existing = store.receipt(case.case_id, action.action_version)
    if existing:
        return existing
    event = OutboxEvent(
        event_id=f"EVT-{uuid.uuid4().hex[:12]}",
        case_id=case.case_id,
        action_version=action.action_version,
        event_type="corrective_action_created",
        payload=action.model_dump(mode="json"),
    )
    store.enqueue(event)
    receipt = ActionReceipt(
        case_id=case.case_id,
        action_version=action.action_version,
        local_reference=f"QT-ACTION-{case.case_id}-{action.action_version}",
        event_id=event.event_id,
    )
    store.save_receipt(receipt)
    return receipt
