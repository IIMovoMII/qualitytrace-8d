from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .models import CaseRecord, EvidenceUnit, HumanDecision, WorkflowSnapshot


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = PROJECT_ROOT / "data" / "rule_registry.json"

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"awaiting_evidence"},
    "awaiting_evidence": {"awaiting_root_cause_review", "blocked"},
    "awaiting_root_cause_review": {"awaiting_action_approval", "blocked"},
    "awaiting_action_approval": {"action_created", "blocked"},
    "action_created": {"awaiting_effectiveness"},
    "awaiting_effectiveness": {"closed", "blocked"},
    "closed": set(),
    "blocked": set(),
}


@lru_cache(maxsize=1)
def policy_registry() -> dict[str, Any]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def workflow_rule(name: str) -> Any:
    return policy_registry()["workflow_rules"][name]


def validate_transition(current: str, target: str) -> None:
    if current == target:
        return
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"禁止状态转移：{current} -> {target}")


def required_evidence_missing(evidence_ids: Iterable[str]) -> list[str]:
    present = set(evidence_ids)
    return [item for item in workflow_rule("required_evidence_ids") if item not in present]


def validate_initial_evidence(case: CaseRecord, evidence: list[EvidenceUnit]) -> list[str]:
    errors: list[str] = []
    items = {item.evidence_id: item for item in evidence}
    batch = items.get("EV-BATCH")
    specification = items.get("EV-SPEC")
    inspection = items.get("EV-INSPECTION")
    if not batch or not specification or not inspection:
        return errors

    if batch.attributes.get("lot_id") != case.lot_id or batch.attributes.get("supplier_id") != case.supplier_id:
        errors.append("批次或供应商对象与当前案件不一致")
    if float(specification.attributes.get("required", float("nan"))) != case.required_value:
        errors.append("规格名义值与案件字段不一致")
    if specification.attributes.get("unit") != case.unit or inspection.attributes.get("unit") != case.unit:
        errors.append("规格、读数与案件单位不一致")
    try:
        if date.fromisoformat(specification.attributes["effective_date"]) > date.fromisoformat(batch.attributes["receipt_date"]):
            errors.append("规格在批次收货日尚未生效")
    except (KeyError, TypeError, ValueError):
        errors.append("规格生效日或批次收货日不可解析")

    readings = [float(value) for value in inspection.attributes.get("readings", [])]
    sample_size = int(inspection.attributes.get("sample_size", 0))
    if sample_size < int(workflow_rule("minimum_initial_sample_size")) or len(readings) != sample_size:
        errors.append("初检样本量不足或逐件读数不完整")
    tolerance = float(specification.attributes["tolerance"])
    lower = case.required_value - tolerance
    upper = case.required_value + tolerance
    calculated_oos = sum(value < lower or value > upper for value in readings)
    if calculated_oos != int(inspection.attributes.get("out_of_spec", -1)):
        errors.append("初检超规格数量与逐件读数不一致")
    if readings and max(readings) != case.measured_value:
        errors.append("案件代表测量值与逐件读数不一致")
    return errors


def _approved_decision(
    decisions: Iterable[HumanDecision],
    decision_type: str,
    allowed_roles: set[str],
    action_version: int | None = None,
) -> HumanDecision | None:
    for decision in reversed(list(decisions)):
        if decision.decision_type != decision_type or decision.actor_role not in allowed_roles:
            continue
        if action_version is not None and decision.action_version != action_version:
            continue
        return decision if decision.decision == "approved" else None
    return None


def action_approval(decisions: Iterable[HumanDecision], action_version: int) -> HumanDecision | None:
    return _approved_decision(
        decisions,
        "approve_action",
        set(workflow_rule("action_approval_roles")),
        action_version,
    )


def effectiveness_approval(decisions: Iterable[HumanDecision]) -> HumanDecision | None:
    return _approved_decision(
        decisions,
        "accept_effectiveness",
        set(workflow_rule("effectiveness_approval_roles")),
    )


def can_create_action(snapshot: WorkflowSnapshot) -> bool:
    return (
        snapshot.status == "awaiting_action_approval"
        and snapshot.action is not None
        and not snapshot.conflict_ids
        and not snapshot.missing_evidence
        and action_approval(snapshot.decisions, snapshot.action.action_version) is not None
    )


def can_close(snapshot: WorkflowSnapshot, case: CaseRecord) -> bool:
    if snapshot.status != "awaiting_effectiveness" or not snapshot.effectiveness_evidence_ids:
        return False
    if effectiveness_approval(snapshot.decisions) is None:
        return False

    selected = [
        item for item in case.evidence
        if item.evidence_id in snapshot.effectiveness_evidence_ids and item.kind == "effectiveness"
    ]
    if len(selected) != len(snapshot.effectiveness_evidence_ids):
        return False

    specification = next((item for item in case.evidence if item.evidence_id == "EV-SPEC"), None)
    if specification is None:
        return False
    tolerance = float(specification.attributes["tolerance"])
    lower = case.required_value - tolerance
    upper = case.required_value + tolerance
    minimum = int(workflow_rule("minimum_effectiveness_sample_size"))
    maximum_oos = int(workflow_rule("maximum_effectiveness_out_of_spec"))

    for item in selected:
        attributes = item.attributes
        readings = [float(value) for value in attributes.get("readings", [])]
        if attributes.get("lot_id") != case.lot_id:
            return False
        if attributes.get("spec_revision") != specification.attributes.get("revision"):
            return False
        if attributes.get("unit") != case.unit:
            return False
        if int(attributes.get("sample_size", 0)) < minimum:
            return False
        if len(readings) != int(attributes.get("sample_size", 0)):
            return False
        if int(attributes.get("out_of_spec", -1)) > maximum_oos:
            return False
        if any(value < lower or value > upper for value in readings):
            return False
    return True
