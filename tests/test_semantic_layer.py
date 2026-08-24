import json
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from qualitytrace.agents import draft_corrective_action, investigate_root_causes
from qualitytrace.fixtures import make_case
from qualitytrace.models import EightDDraftPayload
from qualitytrace.semantic import LiteLLMConfig, LiteLLMProvider, build_local_draft
from qualitytrace.workflow import QualityTraceEngine


class StubProvider:
    provider_name = "stub"
    model_alias = "anonymous-test-model"

    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def generate(self, request: dict[str, Any], schema: dict[str, Any]):
        self.calls += 1
        if self.error:
            raise self.error
        return self.result


def _valid_payload() -> dict[str, Any]:
    case = make_case("complete")
    evidence = [item for item in case.evidence if item.kind != "effectiveness"]
    causes = investigate_root_causes(case, evidence)
    action = draft_corrective_action(case, causes)
    payload = build_local_draft(case, causes, action, origin="offline").model_dump(mode="json")
    payload.pop("origin")
    return payload


def test_llm_structured_draft_is_used_after_schema_and_evidence_validation(tmp_path: Path):
    provider = StubProvider(_valid_payload())
    case = make_case("complete")
    result = QualityTraceEngine(tmp_path / "llm.sqlite", semantic_provider=provider).start(case)
    assert provider.calls == 1
    assert result.snapshot.status == "awaiting_action_approval"
    assert result.snapshot.semantic_trace.mode == "llm"
    assert result.snapshot.semantic_trace.attempts == 1
    assert result.snapshot.semantic_trace.fallback_reason is None
    assert result.snapshot.eight_d_draft is not None
    assert result.snapshot.eight_d_draft.origin == "llm"
    assert result.snapshot.eight_d_draft.d8_closure.status == "pending_human_confirmation"


def test_malformed_llm_json_falls_back_without_blocking_business_flow(tmp_path: Path):
    provider = StubProvider("not-json")
    result = QualityTraceEngine(tmp_path / "malformed.sqlite", semantic_provider=provider).start(make_case("complete"))
    assert result.snapshot.status == "awaiting_action_approval"
    assert result.snapshot.semantic_trace.mode == "fallback"
    assert result.snapshot.semantic_trace.fallback_reason == "malformed_json"
    assert result.snapshot.eight_d_draft is not None
    assert result.snapshot.eight_d_draft.origin == "fallback"


def test_provider_failure_falls_back_once_and_does_not_retry(tmp_path: Path):
    provider = StubProvider(error=TimeoutError("upstream timeout"))
    result = QualityTraceEngine(tmp_path / "timeout.sqlite", semantic_provider=provider).start(make_case("complete"))
    assert provider.calls == 1
    assert result.snapshot.semantic_trace.mode == "fallback"
    assert result.snapshot.semantic_trace.fallback_reason == "provider_error"
    assert result.snapshot.semantic_trace.attempts == 1


def test_unknown_evidence_reference_is_rejected_and_falls_back(tmp_path: Path):
    payload = _valid_payload()
    payload["d4_root_cause"]["evidence_ids"] = ["EV-NOT-VISIBLE"]
    result = QualityTraceEngine(
        tmp_path / "evidence-violation.sqlite",
        semantic_provider=StubProvider(payload),
    ).start(make_case("complete"))
    assert result.snapshot.semantic_trace.mode == "fallback"
    assert result.snapshot.semantic_trace.fallback_reason == "evidence_violation"


def test_llm_cannot_mark_root_cause_or_closure_as_final(tmp_path: Path):
    payload = _valid_payload()
    payload["d8_closure"]["status"] = "draft"
    result = QualityTraceEngine(
        tmp_path / "authority-violation.sqlite",
        semantic_provider=StubProvider(payload),
    ).start(make_case("complete"))
    assert result.snapshot.semantic_trace.mode == "fallback"
    assert result.snapshot.semantic_trace.fallback_reason == "authority_violation"


def test_litellm_adapter_requests_json_schema_without_persisting_secret():
    captured: dict[str, Any] = {}
    payload = _valid_payload()

    def fake_completion(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}]}

    config = LiteLLMConfig(
        model="openai/test-model",
        api_base="https://example.invalid/v1",
        api_key=SecretStr("test-placeholder-key"),
        response_mode="json_schema",
    )
    provider = LiteLLMProvider(config, completion_fn=fake_completion)
    raw = provider.generate({"allowed_evidence_ids": []}, EightDDraftPayload.model_json_schema())
    assert isinstance(raw, str)
    assert captured["response_format"]["type"] == "json_schema"
    assert captured["max_retries"] == 0
    assert captured["api_key"] == "test-placeholder-key"
    assert "test-placeholder-key" not in repr(config)
