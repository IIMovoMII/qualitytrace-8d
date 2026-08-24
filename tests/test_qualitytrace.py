from pathlib import Path

from qualitytrace.checks import run_acceptance
from qualitytrace.fixtures import make_case
from qualitytrace.models import HumanDecision
from qualitytrace.tools import publish_corrective_action
from qualitytrace.workflow import QualityTraceEngine


def test_complete_path_pauses_then_closes(tmp_path: Path):
    case = make_case("complete")
    engine = QualityTraceEngine(tmp_path / "complete.sqlite")
    first = engine.start(case)
    assert first.snapshot.status == "awaiting_action_approval"
    assert "EV-EFFECTIVENESS" not in first.snapshot.evidence_ids
    approved = engine.resume(case, HumanDecision(
        decision_id="d1", case_id=case.case_id, decision_type="approve_action", actor_role="quality_manager",
        decision="approved", reason="approve", action_version=1,
    ))
    assert approved.snapshot.status == "awaiting_effectiveness"
    engine.add_effectiveness(case, ["EV-EFFECTIVENESS"])
    final = engine.resume(case, HumanDecision(
        decision_id="d2", case_id=case.case_id, decision_type="accept_effectiveness", actor_role="quality_manager",
        decision="approved", reason="effective",
    ))
    assert final.snapshot.status == "closed"
    assert final.snapshot.receipt is not None
    assert any(event.agent == "InvestigationAgent" for event in final.snapshot.trace_events)
    assert any(event.tool == "ActionTools.publish_corrective_action" for event in final.snapshot.trace_events)


def test_missing_evidence_has_no_side_effect(tmp_path: Path):
    case = make_case("missing_evidence")
    engine = QualityTraceEngine(tmp_path / "missing.sqlite")
    result = engine.start(case)
    assert result.snapshot.status == "awaiting_evidence"
    assert result.snapshot.missing_evidence == ["EV-SUPPLIER"]
    assert engine.store.receipt(case.case_id, 1) is None


def test_conflict_and_wrong_object_block(tmp_path: Path):
    for kind in ("conflict", "wrong_object"):
        case = make_case(kind)
        result = QualityTraceEngine(tmp_path / f"{kind}.sqlite").start(case)
        assert result.snapshot.status == "blocked"
        assert result.snapshot.receipt is None


def test_tool_failure_recovers_with_bounded_retry(tmp_path: Path):
    case = make_case("tool_failure_recovery")
    result = QualityTraceEngine(tmp_path / "retry.sqlite").start(case)
    assert result.snapshot.status == "awaiting_action_approval"
    assert len(result.snapshot.tool_failures) == 1


def test_acceptance_report_covers_five_paths(tmp_path: Path):
    report = run_acceptance(tmp_path / "acceptance.json")
    assert set(report["cases"]) == {"complete", "missing_evidence", "conflict", "wrong_object", "tool_failure_recovery"}
    assert report["cases"]["complete"]["final_status"] == "closed"
    assert report["cases"]["tool_failure_recovery"]["final_status"] == "closed"


def test_same_action_version_is_idempotent(tmp_path: Path):
    case = make_case("complete")
    engine = QualityTraceEngine(tmp_path / "idempotent.sqlite")
    first = engine.start(case)
    action = first.snapshot.action
    assert action is not None
    receipt_a = publish_corrective_action(engine.store, case, action, approved=True)
    receipt_b = publish_corrective_action(engine.store, case, action, approved=True)
    assert receipt_a.event_id == receipt_b.event_id
    assert engine.store.export_summary()["tables"]["outbox_events"] == 1


def test_unauthorized_role_cannot_approve_action(tmp_path: Path):
    case = make_case("complete")
    engine = QualityTraceEngine(tmp_path / "unauthorized.sqlite")
    engine.start(case)
    result = engine.resume(case, HumanDecision(
        decision_id="d-unauthorized", case_id=case.case_id, decision_type="approve_action",
        actor_role="supplier_quality", decision="approved", reason="supplier self approval", action_version=1,
    ))
    assert result.snapshot.status == "blocked"
    assert result.snapshot.receipt is None
    assert "无权批准" in (result.snapshot.last_error or "")


def test_insufficient_effectiveness_evidence_does_not_close(tmp_path: Path):
    case = make_case("complete")
    effectiveness = next(item for item in case.evidence if item.evidence_id == "EV-EFFECTIVENESS")
    effectiveness.attributes["readings"] = effectiveness.attributes["readings"][:4]
    effectiveness.attributes["sample_size"] = 4
    engine = QualityTraceEngine(tmp_path / "insufficient-effectiveness.sqlite")
    engine.start(case)
    engine.resume(case, HumanDecision(
        decision_id="d-action", case_id=case.case_id, decision_type="approve_action",
        actor_role="quality_manager", decision="approved", reason="approve", action_version=1,
    ))
    engine.add_effectiveness(case, ["EV-EFFECTIVENESS"])
    result = engine.resume(case, HumanDecision(
        decision_id="d-effect", case_id=case.case_id, decision_type="accept_effectiveness",
        actor_role="quality_manager", decision="approved", reason="reviewed",
    ))
    assert result.snapshot.status == "awaiting_effectiveness"
    assert "QT-POL-006" in (result.snapshot.last_error or "")


def test_incomplete_initial_readings_are_blocked(tmp_path: Path):
    case = make_case("complete")
    inspection = next(item for item in case.evidence if item.evidence_id == "EV-INSPECTION")
    inspection.attributes["readings"] = inspection.attributes["readings"][:4]
    inspection.attributes["sample_size"] = 4
    result = QualityTraceEngine(tmp_path / "short-initial-sample.sqlite").start(case)
    assert result.snapshot.status == "blocked"
    assert "样本量不足" in (result.snapshot.last_error or "")
