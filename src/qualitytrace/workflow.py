from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .models import CaseRecord, HumanDecision, TraceEvent, TransitionRecord, WorkflowResult, WorkflowSnapshot, utc_now
from .persistence import CheckpointStore
from .policies import (
    action_approval,
    can_close,
    can_create_action,
    effectiveness_approval,
    required_evidence_missing,
    validate_initial_evidence,
    validate_transition,
)
from .tools import ReadTools, ToolFailure, draft_action, propose_root_causes, publish_corrective_action
from .agents import draft_corrective_action, investigate_root_causes, triage_case
from .semantic import SemanticProvider, generate_eight_d_draft


class GraphState(TypedDict, total=False):
    case: dict[str, Any]
    snapshot: dict[str, Any]
    route: str
    trace_id: str


class QualityTraceEngine:
    """LangGraph workflow with an explicit local durable checkpoint boundary."""

    def __init__(self, database: Path, semantic_provider: SemanticProvider | None = None) -> None:
        self.store = CheckpointStore(database)
        self.semantic_provider = semantic_provider

    def _save(self, snapshot: WorkflowSnapshot) -> None:
        self.store.save(snapshot)

    def _transition(self, snapshot: WorkflowSnapshot, target: str, node: str, reason: str, evidence_ids: list[str] | None = None) -> None:
        validate_transition(snapshot.status, target)
        record = TransitionRecord(
            sequence=len(snapshot.trace) + 1,
            from_status=snapshot.status,
            to_status=target,
            node=node,
            reason=reason,
            evidence_ids=evidence_ids or [],
        )
        snapshot.status = target  # type: ignore[assignment]
        snapshot.revision += 1
        snapshot.trace.append(record)
        agent = {"root_cause": "InvestigationAgent", "action_gate": "DraftAgent", "evidence": "TriageAgent"}.get(node)
        tool = {"evidence": "ReadTools.inspect_evidence/compare_spec_and_measurement", "action_gate": "ActionTools.publish_corrective_action"}.get(node)
        snapshot.trace_events.append(TraceEvent(
            sequence=len(snapshot.trace_events) + 1,
            run_id=snapshot.run_id or "unknown",
            node=node,
            agent=agent,
            tool=tool,
            status="blocked" if target == "blocked" else ("paused" if target.startswith("awaiting_") else "completed"),
            evidence_ids=evidence_ids or [],
        ))

    def _blocked(self, snapshot: WorkflowSnapshot, node: str, reason: str, evidence_ids: list[str] | None = None) -> None:
        if snapshot.status != "blocked":
            self._transition(snapshot, "blocked", node, reason, evidence_ids)
        snapshot.last_error = reason
        self._save(snapshot)

    @staticmethod
    def _decision_for(snapshot: WorkflowSnapshot, decision_type: str) -> HumanDecision | None:
        for decision in reversed(snapshot.decisions):
            if decision.decision_type == decision_type:
                return decision
        return None

    def _route(self, state: GraphState) -> str:
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        if snapshot.status in {"closed", "blocked"}:
            return "END"
        if snapshot.status == "awaiting_evidence" and snapshot.missing_evidence:
            return "END"
        if snapshot.status == "awaiting_action_approval":
            decision = self._decision_for(snapshot, "approve_action")
            return "END" if snapshot.pending_decision_id and decision is None else "action_gate"
        if snapshot.status == "awaiting_effectiveness":
            if snapshot.last_error and snapshot.last_error.startswith("复检证据未满足"):
                return "END"
            decision = self._decision_for(snapshot, "accept_effectiveness")
            if not snapshot.effectiveness_evidence_ids:
                return "END"
            return "END" if snapshot.pending_decision_id and decision is None else "effectiveness"
        return {
            "draft": "intake",
            "awaiting_evidence": "evidence",
            "awaiting_root_cause_review": "root_cause",
            "action_created": "action_created",
        }.get(snapshot.status, "END")

    def _dispatch(self, state: GraphState) -> GraphState:
        state["route"] = self._route(state)
        return state

    def _intake(self, state: GraphState) -> GraphState:
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        self._transition(snapshot, "awaiting_evidence", "intake", "登记来料批次、规格和发现环节")
        self._save(snapshot)
        state["snapshot"] = snapshot.model_dump(mode="json")
        return state

    def _evidence(self, state: GraphState) -> GraphState:
        case = CaseRecord.model_validate(state["case"])
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        tools = ReadTools(case)
        evidence = None
        for attempt in range(1, 3):
            try:
                evidence = tools.inspect_evidence()
                break
            except ToolFailure as exc:
                snapshot.tool_failures.append(f"inspect_evidence attempt={attempt}: {exc}")
        if evidence is None:
            self._blocked(snapshot, "evidence", "只读调查工具连续两次失败，转人工处理")
            state["snapshot"] = snapshot.model_dump(mode="json")
            return state
        evidence_ids = [item.evidence_id for item in evidence]
        snapshot.evidence_ids = evidence_ids
        missing = required_evidence_missing(evidence_ids)
        if missing:
            snapshot.missing_evidence = missing
            self._transition(snapshot, "awaiting_evidence", "evidence", "缺少必需证据，暂停等待补件", missing)
            self._save(snapshot)
            state["snapshot"] = snapshot.model_dump(mode="json")
            return state
        contract_errors = validate_initial_evidence(case, evidence)
        if contract_errors:
            self._blocked(
                snapshot,
                "evidence",
                "初始证据未满足规则合同：" + "；".join(contract_errors),
                ["EV-BATCH", "EV-SPEC", "EV-INSPECTION"],
            )
            state["snapshot"] = snapshot.model_dump(mode="json")
            return state
        conflicts = tools.find_conflicts(evidence)
        triage = triage_case(case, evidence, missing, conflicts)
        if conflicts:
            snapshot.conflict_ids = conflicts
            self._blocked(snapshot, "evidence", "同一台账存在相互冲突的供应商事实，需人工裁决", conflicts)
            state["snapshot"] = snapshot.model_dump(mode="json")
            return state
        self._transition(snapshot, "awaiting_root_cause_review", "evidence", "证据完整且对象一致，进入根因分析", evidence_ids)
        self._save(snapshot)
        state["snapshot"] = snapshot.model_dump(mode="json")
        return state

    def _root_cause(self, state: GraphState) -> GraphState:
        case = CaseRecord.model_validate(state["case"])
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        evidence = [item for item in case.evidence if item.evidence_id in snapshot.evidence_ids]
        causes = investigate_root_causes(case, evidence)
        if not causes:
            self._blocked(snapshot, "root_cause", "未能从证据确认规格偏差根因，不能自行补全")
        else:
            snapshot.root_causes = causes
            snapshot.action = draft_corrective_action(case, causes)
            snapshot.eight_d_draft, snapshot.semantic_trace = generate_eight_d_draft(
                case,
                evidence,
                causes,
                snapshot.action,
                self.semantic_provider,
            )
            draft_mode = {
                "llm": "LLM 结构化草稿已通过 Schema 与证据白名单校验",
                "fallback": "LLM 失败，已回退到本地结构化草稿",
                "offline": "使用本地结构化草稿",
            }[snapshot.semantic_trace.mode]
            self._transition(
                snapshot,
                "awaiting_action_approval",
                "root_cause",
                f"形成可核验根因候选和纠正措施草案；{draft_mode}",
                [item for cause in causes for item in cause.evidence_ids],
            )
            self._save(snapshot)
        state["snapshot"] = snapshot.model_dump(mode="json")
        return state

    def _action_gate(self, state: GraphState) -> GraphState:
        case = CaseRecord.model_validate(state["case"])
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        if snapshot.action is None:
            self._blocked(snapshot, "action_gate", "缺少纠正措施草案，禁止产生副作用")
        elif not snapshot.pending_decision_id:
            snapshot.pending_decision_id = f"DEC-{case.case_id}-ACTION-{snapshot.action.action_version}"
            snapshot.revision += 1
            self._save(snapshot)
        elif can_create_action(snapshot):
            snapshot.receipt = publish_corrective_action(self.store, case, snapshot.action, approved=True)
            self._transition(snapshot, "action_created", "action_gate", "质量负责人批准后写入本地 outbox；按 case_id+action_version 幂等", snapshot.action.evidence_ids)
            self._save(snapshot)
        else:
            decision = self._decision_for(snapshot, "approve_action")
            if decision and decision.decision == "rejected":
                self._blocked(snapshot, "action_gate", "质量负责人拒绝纠正措施，转人工处理")
            elif decision and action_approval(snapshot.decisions, snapshot.action.action_version) is None:
                self._blocked(snapshot, "action_gate", "审批角色无权批准纠正措施，禁止产生副作用")
        state["snapshot"] = snapshot.model_dump(mode="json")
        return state

    def _action_created(self, state: GraphState) -> GraphState:
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        self._transition(snapshot, "awaiting_effectiveness", "action_created", "措施收据已生成，等待复检证据")
        self._save(snapshot)
        state["snapshot"] = snapshot.model_dump(mode="json")
        return state

    def _effectiveness(self, state: GraphState) -> GraphState:
        case = CaseRecord.model_validate(state["case"])
        snapshot = WorkflowSnapshot.model_validate(state["snapshot"])
        if not snapshot.effectiveness_evidence_ids:
            self._save(snapshot)
        elif not snapshot.pending_decision_id:
            snapshot.pending_decision_id = f"DEC-{case.case_id}-EFFECTIVENESS"
            snapshot.revision += 1
            self._save(snapshot)
        elif self._decision_for(snapshot, "accept_effectiveness"):
            decision = self._decision_for(snapshot, "accept_effectiveness")
            if decision and decision.decision == "approved" and can_close(snapshot, case):
                self._transition(snapshot, "closed", "effectiveness", "复检证据合格且质量负责人确认有效性", snapshot.effectiveness_evidence_ids)
                self._save(snapshot)
            elif decision and decision.decision == "approved" and effectiveness_approval(snapshot.decisions) is None:
                self._blocked(snapshot, "effectiveness", "审批角色无权确认有效性，禁止关闭案件")
            elif decision and decision.decision == "approved":
                snapshot.last_error = "复检证据未满足 QT-POL-006 的样本量、规格或对象门槛，保持等待"
                snapshot.revision += 1
                self._save(snapshot)
            else:
                self._blocked(snapshot, "effectiveness", "有效性确认被拒绝，转人工复盘")
        state["snapshot"] = snapshot.model_dump(mode="json")
        return state

    def _build_graph(self):
        graph = StateGraph(GraphState)
        graph.add_node("dispatch", self._dispatch)
        graph.add_node("intake", self._intake)
        graph.add_node("evidence", self._evidence)
        graph.add_node("root_cause", self._root_cause)
        graph.add_node("action_gate", self._action_gate)
        graph.add_node("action_created", self._action_created)
        graph.add_node("effectiveness", self._effectiveness)
        graph.add_edge(START, "dispatch")
        graph.add_conditional_edges("dispatch", lambda state: state["route"], {
            "intake": "intake", "evidence": "evidence", "root_cause": "root_cause",
            "action_gate": "action_gate", "action_created": "action_created",
            "effectiveness": "effectiveness", "END": END,
        })
        for node in ("intake", "evidence", "root_cause", "action_gate", "action_created", "effectiveness"):
            graph.add_edge(node, "dispatch")
        return graph.compile()

    def _invoke(self, case: CaseRecord, snapshot: WorkflowSnapshot, trace_id: str | None = None) -> WorkflowResult:
        snapshot.run_id = snapshot.run_id or trace_id or f"TRACE-{uuid.uuid4().hex[:12]}"
        result = self._build_graph().invoke({
            "case": case.model_dump(mode="json"),
            "snapshot": snapshot.model_dump(mode="json"),
            "trace_id": snapshot.run_id,
        })
        final = WorkflowSnapshot.model_validate(result["snapshot"])
        return WorkflowResult(case=case, snapshot=final, trace_id=result["trace_id"], outcome="closed" if final.status == "closed" else ("blocked" if final.status == "blocked" else "paused"))

    def start(self, case: CaseRecord) -> WorkflowResult:
        snapshot = self.store.latest(case.case_id) or WorkflowSnapshot(case_id=case.case_id)
        return self._invoke(case, snapshot)

    def resume(self, case: CaseRecord, decision: HumanDecision) -> WorkflowResult:
        snapshot = self.store.latest(case.case_id)
        if snapshot is None:
            raise ValueError(f"没有可恢复的 case：{case.case_id}")
        self.store.record_decision(decision)
        snapshot.decisions.append(decision)
        if decision.decision_type == "approve_action":
            snapshot.pending_decision_id = decision.decision_id
        elif decision.decision_type == "accept_effectiveness":
            snapshot.pending_decision_id = decision.decision_id
        snapshot.revision += 1
        self._save(snapshot)
        return self._invoke(case, snapshot)

    def add_effectiveness(self, case: CaseRecord, evidence_ids: list[str]) -> WorkflowSnapshot:
        snapshot = self.store.latest(case.case_id)
        if snapshot is None:
            raise ValueError(f"没有可恢复的 case：{case.case_id}")
        allowed = {item.evidence_id for item in case.evidence if item.kind == "effectiveness"}
        unknown = set(evidence_ids) - allowed
        if unknown:
            raise ValueError(f"有效性证据不属于当前 case：{sorted(unknown)}")
        snapshot.effectiveness_evidence_ids = sorted(set(evidence_ids))
        snapshot.pending_decision_id = None
        snapshot.last_error = None
        snapshot.revision += 1
        self._save(snapshot)
        return snapshot
