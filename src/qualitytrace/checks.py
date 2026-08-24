from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fixtures import all_cases
from .models import HumanDecision
from .workflow import QualityTraceEngine


def _decision(case_id: str, decision_type: str, action_version: int | None = None) -> HumanDecision:
    return HumanDecision(
        decision_id=f"DEC-{case_id}-{decision_type}",
        case_id=case_id,
        decision_type=decision_type,  # type: ignore[arg-type]
        actor_role="quality_manager",
        decision="approved",
        reason="依据已绑定证据和复核记录作出人工确认",
        action_version=action_version,
    )


def run_acceptance(output_path: Path) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {"schema_version": 1, "project": "QualityTrace 8D", "cases": {}}
    for kind, case in all_cases().items():
        database = output_path.parent / f"{case.case_id}.sqlite"
        if database.exists():
            database.unlink()
        engine = QualityTraceEngine(database)
        first = engine.start(case)
        row: dict[str, Any] = {
            "initial_status": first.snapshot.status,
            "initial_trace": [item.model_dump(mode="json") for item in first.snapshot.trace],
            "tool_failures": first.snapshot.tool_failures,
        }
        if kind in {"complete", "tool_failure_recovery"}:
            approved = engine.resume(case, _decision(case.case_id, "approve_action", 1))
            row["after_action_approval"] = approved.snapshot.status
            engine.add_effectiveness(case, ["EV-EFFECTIVENESS"])
            closed = engine.resume(case, _decision(case.case_id, "accept_effectiveness"))
            row["final_status"] = closed.snapshot.status
            row["receipt"] = closed.snapshot.receipt.model_dump(mode="json") if closed.snapshot.receipt else None
            row["idempotent_receipt"] = engine.store.receipt(case.case_id, 1).model_dump(mode="json") if engine.store.receipt(case.case_id, 1) else None
        else:
            row["final_status"] = first.snapshot.status
        row["trace"] = (engine.store.latest(case.case_id) or first.snapshot).model_dump(mode="json")["trace"]
        row["database"] = str(database)
        report["cases"][kind] = row
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report
