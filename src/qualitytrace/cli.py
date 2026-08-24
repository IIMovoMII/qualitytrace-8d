from __future__ import annotations

import argparse
import json
from pathlib import Path

from .checks import run_acceptance
from .data_factory import generate_dataset, validate_persisted_dataset
from .fixtures import make_case
from .models import HumanDecision
from .semantic import SemanticDraftError, provider_from_env
from .workflow import QualityTraceEngine


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"
DB = ARTIFACTS / "demo.sqlite"


def demo(*, use_llm: bool = False) -> None:
    if DB.exists():
        DB.unlink()
    case = make_case("complete")
    provider = provider_from_env() if use_llm else None
    engine = QualityTraceEngine(DB, semantic_provider=provider)
    first = engine.start(case)
    print(json.dumps({
        "step": "initial",
        "status": first.snapshot.status,
        "pending": first.snapshot.pending_decision_id,
        "semantic_mode": first.snapshot.semantic_trace.mode,
        "fallback_reason": first.snapshot.semantic_trace.fallback_reason,
        "eight_d_schema": first.snapshot.eight_d_draft.schema_version if first.snapshot.eight_d_draft else None,
    }, ensure_ascii=False, indent=2))
    second = engine.resume(case, HumanDecision(
        decision_id="DEC-DEMO-ACTION", case_id=case.case_id, decision_type="approve_action",
        actor_role="quality_manager", decision="approved", reason="批准隔离和换型验证", action_version=1,
    ))
    print(json.dumps({"step": "approved", "status": second.snapshot.status, "receipt": second.snapshot.receipt.model_dump(mode="json") if second.snapshot.receipt else None}, ensure_ascii=False, indent=2))
    engine.add_effectiveness(case, ["EV-EFFECTIVENESS"])
    final = engine.resume(case, HumanDecision(
        decision_id="DEC-DEMO-EFFECT", case_id=case.case_id, decision_type="accept_effectiveness",
        actor_role="quality_manager", decision="approved", reason="复检合格，措施有效",
    ))
    print(json.dumps({"step": "closed", "status": final.snapshot.status, "trace": [item.model_dump(mode="json") for item in final.snapshot.trace]}, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description="QualityTrace 8D 本地成品入口")
    parser.add_argument("command", choices=("demo", "llm-demo", "acceptance", "run", "generate-data", "check-data"))
    args = parser.parse_args()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if args.command == "generate-data":
        print(json.dumps(generate_dataset(ROOT), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-data":
        result = validate_persisted_dataset(ROOT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["valid"] else 1
    if args.command in {"demo", "llm-demo"}:
        try:
            demo(use_llm=args.command == "llm-demo")
        except SemanticDraftError as error:
            print(json.dumps({"error": "llm_configuration_error", "detail": str(error)}, ensure_ascii=False, indent=2))
            return 2
        return 0
    if args.command == "acceptance":
        report = run_acceptance(ARTIFACTS / "acceptance_report.json")
        print(json.dumps({"project": report["project"], "cases": {k: v["final_status"] for k, v in report["cases"].items()}}, ensure_ascii=False, indent=2))
        return 0
    case = make_case("complete")
    result = QualityTraceEngine(DB).start(case)
    print(result.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
