from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class EvidenceUnit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    kind: Literal["inspection", "specification", "supplier_response", "batch", "effectiveness"]
    source: str
    text: str
    observed_at: str | None = None
    policy_refs: list[str]
    attributes: dict[str, Any] = Field(default_factory=dict)


class CaseRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    dataset_id: str
    generator_version: str
    scenario: Literal["inbound_spec_deviation"] = "inbound_spec_deviation"
    data_origin: Literal["synthetic_demo"] = "synthetic_demo"
    lot_id: str
    supplier_id: str
    product: str
    spec_name: str
    required_value: float
    measured_value: float
    unit: str
    detection_stage: str
    evidence: list[EvidenceUnit]
    flags: dict[str, Any] = Field(default_factory=dict)


class CandidateRootCause(BaseModel):
    cause_id: str
    statement: str
    evidence_ids: list[str]
    policy_ids: list[str] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"]
    disconfirming_evidence_ids: list[str] = Field(default_factory=list)


class CorrectiveAction(BaseModel):
    action_version: int
    title: str
    owner_role: str
    due_days: int = Field(ge=1, le=30)
    steps: list[str]
    evidence_ids: list[str]
    policy_ids: list[str] = Field(default_factory=list)
    approval_required: bool = True


class EightDSection(BaseModel):
    """One evidence-bound section in the AI-assisted 8D draft."""

    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list)
    status: Literal["draft", "pending_human_confirmation"] = "draft"


class EightDDraftPayload(BaseModel):
    """Provider-facing structured output; authority remains outside the model."""

    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["1.0"] = "1.0"
    case_id: str
    d0_prepare: EightDSection
    d1_team: EightDSection
    d2_problem: EightDSection
    d3_containment: EightDSection
    d4_root_cause: EightDSection
    d5_corrective_action: EightDSection
    d6_validation: EightDSection
    d7_prevention: EightDSection
    d8_closure: EightDSection


class EightDDraft(EightDDraftPayload):
    origin: Literal["llm", "offline", "fallback"]


class SemanticTrace(BaseModel):
    """Audit metadata only; prompts, evidence text, URLs and credentials are omitted."""

    model_config = ConfigDict(extra="forbid")
    mode: Literal["offline", "llm", "fallback"] = "offline"
    provider: str | None = None
    model_alias: str | None = None
    attempts: int = 0
    fallback_reason: Literal[
        "configuration_error",
        "provider_error",
        "malformed_json",
        "schema_validation",
        "case_mismatch",
        "evidence_violation",
        "authority_violation",
    ] | None = None
    prompt_sha256: str | None = None
    output_sha256: str | None = None


class HumanDecision(BaseModel):
    decision_id: str
    case_id: str
    decision_type: Literal["approve_action", "reject_action", "accept_effectiveness"]
    actor_role: Literal["quality_engineer", "quality_manager", "supplier_quality"]
    decision: Literal["approved", "rejected"]
    reason: str
    action_version: int | None = None
    created_at: str = Field(default_factory=utc_now)


class OutboxEvent(BaseModel):
    event_id: str
    case_id: str
    action_version: int
    event_type: Literal["corrective_action_created"]
    payload: dict[str, Any]
    status: Literal["pending", "published", "cancelled"] = "pending"
    created_at: str = Field(default_factory=utc_now)


class ActionReceipt(BaseModel):
    case_id: str
    action_version: int
    local_reference: str
    event_id: str
    created_at: str = Field(default_factory=utc_now)


class TransitionRecord(BaseModel):
    sequence: int
    from_status: str
    to_status: str
    node: str
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class TraceEvent(BaseModel):
    sequence: int
    run_id: str
    node: str
    agent: str | None = None
    tool: str | None = None
    status: Literal["completed", "paused", "blocked", "failed"]
    error_type: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)


class WorkflowSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    run_id: str | None = None
    status: Literal[
        "draft",
        "awaiting_evidence",
        "awaiting_root_cause_review",
        "awaiting_action_approval",
        "action_created",
        "awaiting_effectiveness",
        "closed",
        "blocked",
    ] = "draft"
    stage: str = "D0"
    revision: int = 0
    evidence_ids: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    conflict_ids: list[str] = Field(default_factory=list)
    root_causes: list[CandidateRootCause] = Field(default_factory=list)
    action: CorrectiveAction | None = None
    eight_d_draft: EightDDraft | None = None
    semantic_trace: SemanticTrace = Field(default_factory=SemanticTrace)
    pending_decision_id: str | None = None
    decisions: list[HumanDecision] = Field(default_factory=list)
    receipt: ActionReceipt | None = None
    effectiveness_evidence_ids: list[str] = Field(default_factory=list)
    tool_failures: list[str] = Field(default_factory=list)
    trace: list[TransitionRecord] = Field(default_factory=list)
    trace_events: list[TraceEvent] = Field(default_factory=list)
    last_error: str | None = None


class WorkflowResult(BaseModel):
    case: CaseRecord
    snapshot: WorkflowSnapshot
    trace_id: str
    outcome: Literal["paused", "closed", "blocked"]
