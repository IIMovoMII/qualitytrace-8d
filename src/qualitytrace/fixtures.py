from __future__ import annotations

import json
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

from .models import CaseRecord


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CASES_PATH = PROJECT_ROOT / "data" / "generated" / "cases.json"


@lru_cache(maxsize=1)
def _load_cases() -> dict[str, dict]:
    if not CASES_PATH.is_file():
        raise FileNotFoundError(
            "缺少确定性合成数据；请先运行 scripts/generate_synthetic_data.py"
        )
    payload = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    if payload.get("dataset_id") != "QT8D-SYNTHETIC-20260821-A":
        raise ValueError("QualityTrace 合成数据集 ID 不匹配")
    return payload["cases"]


def make_case(kind: str = "complete") -> CaseRecord:
    cases = _load_cases()
    if kind not in cases:
        raise ValueError(f"未知 fixture：{kind}")
    return CaseRecord.model_validate(deepcopy(cases[kind]))


def all_cases() -> dict[str, CaseRecord]:
    return {kind: make_case(kind) for kind in _load_cases()}
