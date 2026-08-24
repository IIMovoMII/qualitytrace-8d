from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping, Protocol

from pydantic import SecretStr, ValidationError

from .models import (
    CandidateRootCause,
    CaseRecord,
    CorrectiveAction,
    EightDDraft,
    EightDDraftPayload,
    EightDSection,
    EvidenceUnit,
    SemanticTrace,
)


ResponseMode = Literal["json_schema", "json_object", "prompt_only"]


class SemanticDraftError(RuntimeError):
    def __init__(self, category: str, message: str) -> None:
        super().__init__(message)
        self.category = category


class SemanticProvider(Protocol):
    provider_name: str
    model_alias: str

    def generate(self, request: dict[str, Any], schema: dict[str, Any]) -> Mapping[str, Any] | str:
        ...


@dataclass(frozen=True)
class LiteLLMConfig:
    model: str
    api_base: str | None = None
    api_key: SecretStr | None = None
    timeout_seconds: float = 60.0
    response_mode: ResponseMode = "json_schema"

    @classmethod
    def from_env(cls) -> "LiteLLMConfig":
        model = os.getenv("QUALITYTRACE_LLM_MODEL", "").strip()
        if not model:
            raise SemanticDraftError("configuration_error", "缺少 QUALITYTRACE_LLM_MODEL")
        response_mode = os.getenv("QUALITYTRACE_LLM_RESPONSE_MODE", "json_schema").strip().lower()
        if response_mode not in {"json_schema", "json_object", "prompt_only"}:
            raise SemanticDraftError("configuration_error", "QUALITYTRACE_LLM_RESPONSE_MODE 不受支持")
        timeout_raw = os.getenv("QUALITYTRACE_LLM_TIMEOUT_SECONDS", "60").strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise SemanticDraftError("configuration_error", "QUALITYTRACE_LLM_TIMEOUT_SECONDS 必须为数字") from exc
        if not 1 <= timeout_seconds <= 600:
            raise SemanticDraftError("configuration_error", "QUALITYTRACE_LLM_TIMEOUT_SECONDS 必须在 1 到 600 之间")
        api_key = os.getenv("QUALITYTRACE_LLM_API_KEY", "").strip()
        return cls(
            model=model,
            api_base=os.getenv("QUALITYTRACE_LLM_API_BASE", "").strip() or None,
            api_key=SecretStr(api_key) if api_key else None,
            timeout_seconds=timeout_seconds,
            response_mode=response_mode,  # type: ignore[arg-type]
        )


class LiteLLMProvider:
    """Lazy LiteLLM adapter; credentials never enter the workflow snapshot."""

    provider_name = "litellm"

    def __init__(
        self,
        config: LiteLLMConfig,
        completion_fn: Callable[..., Any] | None = None,
    ) -> None:
        self.config = config
        self.model_alias = config.model
        self._completion_fn = completion_fn

    def _completion(self) -> Callable[..., Any]:
        if self._completion_fn is not None:
            return self._completion_fn
        try:
            from litellm import completion
        except ImportError as exc:
            raise SemanticDraftError(
                "configuration_error",
                "未安装可选 LiteLLM 依赖；请使用 requirements-llm.txt",
            ) from exc
        return completion

    def generate(self, request: dict[str, Any], schema: dict[str, Any]) -> Mapping[str, Any] | str:
        system_prompt = (
            "你是制造质量异常调查的草稿组件。只使用请求中列出的可见证据和既有候选，"
            "不得确认根因、批准整改、声称措施有效或宣布结案。严格返回符合给定 JSON Schema 的对象，"
            "所有引用必须来自 allowed_evidence_ids。"
        )
        user_prompt = json.dumps(
            {"task": "整理一份待人工复核的结构化 8D 草稿", "input": request, "json_schema": schema},
            ensure_ascii=False,
            sort_keys=True,
        )
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0,
            "timeout": self.config.timeout_seconds,
            "max_retries": 0,
        }
        if self.config.api_base:
            kwargs["api_base"] = self.config.api_base
        if self.config.api_key:
            kwargs["api_key"] = self.config.api_key.get_secret_value()
        if self.config.response_mode == "json_schema":
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "qualitytrace_8d_draft", "strict": True, "schema": schema},
            }
        elif self.config.response_mode == "json_object":
            kwargs["response_format"] = {"type": "json_object"}

        try:
            response = self._completion()(**kwargs)
        except SemanticDraftError:
            raise
        except Exception as exc:
            raise SemanticDraftError("provider_error", "LiteLLM 请求失败") from exc
        return _extract_response_content(response)


def provider_from_env() -> LiteLLMProvider:
    return LiteLLMProvider(LiteLLMConfig.from_env())


def _extract_response_content(response: Any) -> str:
    try:
        choices = response["choices"] if isinstance(response, Mapping) else response.choices
        choice = choices[0]
        message = choice["message"] if isinstance(choice, Mapping) else choice.message
        content = message["content"] if isinstance(message, Mapping) else message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise SemanticDraftError("malformed_json", "LiteLLM 响应缺少 choices[0].message.content") from exc
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(getattr(item, "text", None), str):
                parts.append(item.text)
        if parts:
            return "".join(parts)
    raise SemanticDraftError("malformed_json", "LiteLLM 响应内容不是可解析文本")


def _strip_json_fence(text: str) -> str:
    stripped = text.strip()
    match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else stripped


def _sha256(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _request_payload(
    case: CaseRecord,
    evidence: list[EvidenceUnit],
    causes: list[CandidateRootCause],
    action: CorrectiveAction,
) -> dict[str, Any]:
    return {
        "case": {
            "case_id": case.case_id,
            "scenario": case.scenario,
            "lot_id": case.lot_id,
            "supplier_id": case.supplier_id,
            "product": case.product,
            "spec_name": case.spec_name,
            "required_value": case.required_value,
            "measured_value": case.measured_value,
            "unit": case.unit,
            "detection_stage": case.detection_stage,
        },
        "allowed_evidence_ids": sorted(item.evidence_id for item in evidence),
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "kind": item.kind,
                "text": item.text,
                "attributes": item.attributes,
                "policy_refs": item.policy_refs,
            }
            for item in evidence
        ],
        "validated_root_cause_candidates": [item.model_dump(mode="json") for item in causes],
        "validated_corrective_action": action.model_dump(mode="json"),
        "authority": {
            "root_cause_confirmation": "human_only",
            "corrective_action_approval": "human_only",
            "effectiveness_confirmation": "human_only",
            "closure": "human_only",
        },
    }


def build_local_draft(
    case: CaseRecord,
    causes: list[CandidateRootCause],
    action: CorrectiveAction,
    *,
    origin: Literal["offline", "fallback"],
) -> EightDDraft:
    cause_text = "；".join(item.statement for item in causes)
    cause_evidence = sorted({evidence_id for item in causes for evidence_id in item.evidence_ids})
    action_text = f"{action.title}；" + "；".join(action.steps)
    payload = EightDDraftPayload(
        case_id=case.case_id,
        d0_prepare=EightDSection(
            text=f"登记来料批次 {case.lot_id} 的{case.spec_name}偏差并保留发现环节。",
            evidence_ids=["EV-BATCH", "EV-INSPECTION"],
        ),
        d1_team=EightDSection(
            text="建议由质量工程、供应商质量和质量负责人组成复核角色；具体人员待人工指定。",
            status="pending_human_confirmation",
        ),
        d2_problem=EightDSection(
            text=(
                f"目标值 {case.required_value:.2f} {case.unit}，代表读数 {case.measured_value:.2f} {case.unit}；"
                "需结合逐件读数和当前生效规格确认影响范围。"
            ),
            evidence_ids=["EV-SPEC", "EV-INSPECTION"],
        ),
        d3_containment=EightDSection(
            text=f"隔离批次 {case.lot_id}，在质量负责人确认前不得直接放行。",
            evidence_ids=["EV-BATCH", "EV-SPEC", "EV-INSPECTION"],
            status="pending_human_confirmation",
        ),
        d4_root_cause=EightDSection(
            text=f"候选根因：{cause_text}",
            evidence_ids=cause_evidence,
            status="pending_human_confirmation",
        ),
        d5_corrective_action=EightDSection(
            text=f"纠正措施草案：{action_text}",
            evidence_ids=action.evidence_ids,
            status="pending_human_confirmation",
        ),
        d6_validation=EightDSection(
            text="措施执行后需补充同规格、同对象的逐件复检记录，再由质量负责人确认有效性。",
            evidence_ids=["EV-SPEC", "EV-INSPECTION"],
            status="pending_human_confirmation",
        ),
        d7_prevention=EightDSection(
            text="建议把规格版本、工装切换记录和复检样本量纳入后续防错清单。",
            evidence_ids=["EV-SPEC", "EV-SUPPLIER"],
            status="pending_human_confirmation",
        ),
        d8_closure=EightDSection(
            text="当前仅为草稿；根因、整改、有效性和结案均等待授权人员确认。",
            status="pending_human_confirmation",
        ),
    )
    return EightDDraft(**payload.model_dump(mode="json"), origin=origin)


def _parse_provider_payload(raw: Mapping[str, Any] | str) -> EightDDraftPayload:
    if isinstance(raw, str):
        try:
            payload = json.loads(_strip_json_fence(raw))
        except json.JSONDecodeError as exc:
            raise SemanticDraftError("malformed_json", "模型未返回合法 JSON") from exc
    else:
        payload = dict(raw)
    try:
        return EightDDraftPayload.model_validate(payload)
    except ValidationError as exc:
        raise SemanticDraftError("schema_validation", "模型输出未通过 EightDDraftPayload Schema") from exc


def _validate_provider_draft(
    draft: EightDDraftPayload,
    *,
    case_id: str,
    allowed_evidence_ids: set[str],
) -> None:
    if draft.case_id != case_id:
        raise SemanticDraftError("case_mismatch", "模型返回了错误 case_id")
    sections = (
        draft.d0_prepare,
        draft.d1_team,
        draft.d2_problem,
        draft.d3_containment,
        draft.d4_root_cause,
        draft.d5_corrective_action,
        draft.d6_validation,
        draft.d7_prevention,
        draft.d8_closure,
    )
    cited = {evidence_id for section in sections for evidence_id in section.evidence_ids}
    if cited - allowed_evidence_ids:
        raise SemanticDraftError("evidence_violation", "模型引用了不可见或不存在的证据")
    for section in (draft.d2_problem, draft.d4_root_cause, draft.d5_corrective_action):
        if not section.evidence_ids:
            raise SemanticDraftError("evidence_violation", "关键 8D 段落缺少证据绑定")
    for section in (draft.d3_containment, draft.d4_root_cause, draft.d5_corrective_action, draft.d8_closure):
        if section.status != "pending_human_confirmation":
            raise SemanticDraftError("authority_violation", "模型越过人工确认边界")


def generate_eight_d_draft(
    case: CaseRecord,
    evidence: list[EvidenceUnit],
    causes: list[CandidateRootCause],
    action: CorrectiveAction,
    provider: SemanticProvider | None,
) -> tuple[EightDDraft, SemanticTrace]:
    request = _request_payload(case, evidence, causes, action)
    prompt_sha256 = _sha256(request)
    if provider is None:
        draft = build_local_draft(case, causes, action, origin="offline")
        return draft, SemanticTrace(mode="offline", attempts=0, prompt_sha256=prompt_sha256, output_sha256=_sha256(draft.model_dump(mode="json")))

    try:
        raw = provider.generate(request, EightDDraftPayload.model_json_schema())
        payload = _parse_provider_payload(raw)
        _validate_provider_draft(
            payload,
            case_id=case.case_id,
            allowed_evidence_ids=set(request["allowed_evidence_ids"]),
        )
        draft = EightDDraft(**payload.model_dump(mode="json"), origin="llm")
        trace = SemanticTrace(
            mode="llm",
            provider=provider.provider_name,
            model_alias=provider.model_alias,
            attempts=1,
            prompt_sha256=prompt_sha256,
            output_sha256=_sha256(draft.model_dump(mode="json")),
        )
        return draft, trace
    except SemanticDraftError as exc:
        reason = exc.category
    except Exception:
        reason = "provider_error"

    if reason not in {
        "configuration_error",
        "provider_error",
        "malformed_json",
        "schema_validation",
        "case_mismatch",
        "evidence_violation",
        "authority_violation",
    }:
        reason = "provider_error"
    fallback = build_local_draft(case, causes, action, origin="fallback")
    return fallback, SemanticTrace(
        mode="fallback",
        provider=provider.provider_name,
        model_alias=provider.model_alias,
        attempts=1,
        fallback_reason=reason,  # type: ignore[arg-type]
        prompt_sha256=prompt_sha256,
        output_sha256=_sha256(fallback.model_dump(mode="json")),
    )
