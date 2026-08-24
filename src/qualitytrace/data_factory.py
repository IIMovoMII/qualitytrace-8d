from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from copy import deepcopy
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = PROJECT_ROOT / "data"
GENERATED_ROOT = DATA_ROOT / "generated"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reading_status(value: float, nominal: float, tolerance: float) -> str:
    return "accepted" if nominal - tolerance <= value <= nominal + tolerance else "rejected"


def _generate_readings(spec: dict[str, Any]) -> tuple[list[float], list[float]]:
    base = spec["base_case"]
    randomizer = random.Random(int(spec["seed"]))
    nominal = float(base["required_value"])
    tolerance = float(base["tolerance"])
    initial_size = int(base["initial_sample_size"])
    in_spec_count = round(initial_size * float(base["initial_in_spec_ratio"]))
    inner_band = tolerance * float(base["initial_in_spec_band_of_tolerance"])
    anomaly_low, anomaly_high = [tolerance * float(value) for value in base["initial_high_anomaly_band_of_tolerance"]]

    initial = [round(randomizer.uniform(nominal - inner_band, nominal + inner_band), 2) for _ in range(in_spec_count)]
    initial.extend(round(randomizer.uniform(nominal + anomaly_low, nominal + anomaly_high), 2) for _ in range(initial_size - in_spec_count))
    randomizer.shuffle(initial)

    effective_band = tolerance * float(base["effectiveness_band_of_tolerance"])
    effectiveness = [
        round(randomizer.uniform(nominal - effective_band, nominal + effective_band), 2)
        for _ in range(int(base["effectiveness_sample_size"]))
    ]
    return initial, effectiveness


def _csv_text(readings: list[float], nominal: float, tolerance: float, unit: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["sample_index", f"reading_{unit}", "status"])
    for index, value in enumerate(readings, start=1):
        writer.writerow([index, f"{value:.2f}", _reading_status(value, nominal, tolerance)])
    return output.getvalue()


def _case_id(kind: str) -> str:
    return f"QT-{kind.upper()}-001"


def _source(case_id: str, filename: str) -> str:
    return f"data/generated/evidence/{case_id}/{filename}"


def _evidence_units(
    case_id: str,
    base: dict[str, Any],
    initial: list[float],
    effectiveness: list[float],
    *,
    wrong_object: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    nominal = float(base["required_value"])
    tolerance = float(base["tolerance"])
    lower = nominal - tolerance
    upper = nominal + tolerance
    initial_oos = sum(_reading_status(value, nominal, tolerance) == "rejected" for value in initial)
    effective_oos = sum(_reading_status(value, nominal, tolerance) == "rejected" for value in effectiveness)
    batch_lot = "LOT-DEMO-999" if wrong_object else base["lot_id"]
    batch_supplier = "SUP-DEMO-999" if wrong_object else base["supplier_id"]

    batch_payload = {
        "record_type": "synthetic_incoming_batch",
        "site_id": base["site_id"],
        "lot_id": batch_lot,
        "supplier_id": batch_supplier,
        "product": base["product"],
        "receipt_date": base["receipt_date"],
        "synthetic": True,
    }
    batch_text = (
        f"合成批次 {batch_lot}，供应商 {batch_supplier}，产品 {base['product']}，"
        f"于 {base['receipt_date']} 进入来料检验。"
    )
    spec_text = (
        f"# 合成规格 {base['spec_revision']}\n\n"
        f"- 产品：{base['product']}\n"
        f"- 参数：{base['spec_name']}\n"
        f"- 名义值：{nominal:.2f} {base['unit']}\n"
        f"- 公差：±{tolerance:.2f} {base['unit']}\n"
        f"- 合格范围：{lower:.2f}–{upper:.2f} {base['unit']}\n"
        f"- 生效日期：{base['spec_effective_date']}\n"
        "- 超出公差时不得直接放行。\n"
        "- 本文件为 QualityTrace 8D 合成资料，不是真实企业规格。\n"
    )
    inspection_text = (
        f"合成来料检验共抽检 {len(initial)} 件，读数为 "
        f"{', '.join(f'{value:.2f}' for value in initial)} {base['unit']}；"
        f"其中 {initial_oos} 件超出 {lower:.2f}–{upper:.2f} {base['unit']}。"
        f"设备 {base['inspection_equipment']} 的合成校准有效期至 {base['calibration_valid_until']}。"
    )
    supplier_text = (
        f"合成供应商回复：{base['lot_id']} 仍沿用 {base['previous_spec_revision']} 工装，"
        f"尚未完成 {base['spec_revision']} 切换；将在 {base['supplier_response_sla_hours']} 小时内补充纠正措施。"
    )
    effectiveness_text = (
        f"合成纠正后复检共 {len(effectiveness)} 件，读数为 "
        f"{', '.join(f'{value:.2f}' for value in effectiveness)} {base['unit']}；"
        f"超规格 {effective_oos} 件。"
    )

    files = {
        "batch_record.json": _json_text(batch_payload),
        f"spec_{base['spec_revision'].lower().replace('-', '_')}.md": spec_text,
        "inspection_report.csv": _csv_text(initial, nominal, tolerance, base["unit"]),
        "supplier_reply.txt": supplier_text + "\n",
        "reinspection_report.csv": _csv_text(effectiveness, nominal, tolerance, base["unit"]),
    }
    evidence = [
        {
            "evidence_id": "EV-BATCH",
            "kind": "batch",
            "source": _source(case_id, "batch_record.json"),
            "text": batch_text,
            "observed_at": f"{base['receipt_date']}T08:30:00+08:00",
            "policy_refs": ["QT-POL-003"],
            "attributes": {
                "site_id": base["site_id"],
                "lot_id": batch_lot,
                "supplier_id": batch_supplier,
                "receipt_date": base["receipt_date"],
                "synthetic": True,
            },
        },
        {
            "evidence_id": "EV-SPEC",
            "kind": "specification",
            "source": _source(case_id, f"spec_{base['spec_revision'].lower().replace('-', '_')}.md"),
            "text": spec_text.replace("\n", " ").strip(),
            "observed_at": f"{base['spec_effective_date']}T00:00:00+08:00",
            "policy_refs": ["QT-POL-001", "QT-POL-002"],
            "attributes": {
                "required": nominal,
                "tolerance": tolerance,
                "lower": round(lower, 2),
                "upper": round(upper, 2),
                "revision": base["spec_revision"],
                "effective_date": base["spec_effective_date"],
                "unit": base["unit"],
            },
        },
        {
            "evidence_id": "EV-INSPECTION",
            "kind": "inspection",
            "source": _source(case_id, "inspection_report.csv"),
            "text": inspection_text,
            "observed_at": f"{base['receipt_date']}T10:15:00+08:00",
            "policy_refs": ["QT-POL-001", "QT-POL-003"],
            "attributes": {
                "measured": max(initial),
                "readings": initial,
                "sample_size": len(initial),
                "out_of_spec": initial_oos,
                "equipment_id": base["inspection_equipment"],
                "calibration_valid_until": base["calibration_valid_until"],
                "unit": base["unit"],
            },
        },
        {
            "evidence_id": "EV-SUPPLIER",
            "kind": "supplier_response",
            "source": _source(case_id, "supplier_reply.txt"),
            "text": supplier_text,
            "observed_at": f"{base['receipt_date']}T15:20:00+08:00",
            "policy_refs": ["QT-POL-002", "QT-POL-004"],
            "attributes": {
                "lot_id": base["lot_id"],
                "tooling_revision": base["previous_spec_revision"],
                "target_revision": base["spec_revision"],
                "response_sla_hours": base["supplier_response_sla_hours"],
                "claim_status": "unverified_supplier_statement",
            },
        },
        {
            "evidence_id": "EV-EFFECTIVENESS",
            "kind": "effectiveness",
            "source": _source(case_id, "reinspection_report.csv"),
            "text": effectiveness_text,
            "observed_at": "2026-08-24T14:00:00+08:00",
            "policy_refs": ["QT-POL-001", "QT-POL-006"],
            "attributes": {
                "lot_id": base["lot_id"],
                "spec_revision": base["spec_revision"],
                "readings": effectiveness,
                "sample_size": len(effectiveness),
                "out_of_spec": effective_oos,
                "equipment_id": base["inspection_equipment"],
                "unit": base["unit"],
            },
        },
    ]
    return evidence, files


def build_dataset(spec: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    base = spec["base_case"]
    initial, effectiveness = _generate_readings(spec)
    cases: dict[str, dict[str, Any]] = {}
    evidence_files: dict[str, str] = {}

    for variant in spec["variants"]:
        kind = variant["kind"]
        case_id = _case_id(kind)
        wrong_object = kind == "wrong_object"
        evidence, files = _evidence_units(case_id, base, initial, effectiveness, wrong_object=wrong_object)
        flags: dict[str, Any] = {"expected_status_after_first_run": variant["expected_status_after_first_run"]}

        if kind == "missing_evidence":
            evidence = [item for item in evidence if item["evidence_id"] != "EV-SUPPLIER"]
            files.pop("supplier_reply.txt")
        elif kind == "conflict":
            conflict_text = (
                f"合成供应商第二次回复：{base['lot_id']} 已使用 {base['spec_revision']} 工装。"
                f"该说法与 EV-SUPPLIER 的 {base['previous_spec_revision']} 工装说法冲突。"
            )
            evidence.append({
                "evidence_id": "EV-CONFLICT",
                "kind": "supplier_response",
                "source": _source(case_id, "supplier_reply_v2.txt"),
                "text": conflict_text,
                "observed_at": f"{base['receipt_date']}T16:05:00+08:00",
                "policy_refs": ["QT-POL-002", "QT-POL-004"],
                "attributes": {
                    "lot_id": base["lot_id"],
                    "tooling_revision": base["spec_revision"],
                    "conflicts_with": "EV-SUPPLIER",
                    "claim_status": "unverified_supplier_statement",
                },
            })
            files["supplier_reply_v2.txt"] = conflict_text + "\n"
            flags["conflict_evidence_ids"] = ["EV-SUPPLIER", "EV-CONFLICT"]
        elif kind == "wrong_object":
            flags["expected_lot_id"] = base["lot_id"]
        elif kind == "tool_failure_recovery":
            flags["read_tool_failures_before_success"] = 1

        for filename, content in files.items():
            evidence_files[_source(case_id, filename)] = content

        cases[kind] = {
            "case_id": case_id,
            "dataset_id": spec["dataset_id"],
            "generator_version": spec["generator_version"],
            "scenario": spec["scenario"],
            "data_origin": spec["origin"],
            "lot_id": base["lot_id"],
            "supplier_id": base["supplier_id"],
            "product": base["product"],
            "spec_name": base["spec_name"],
            "required_value": float(base["required_value"]),
            "measured_value": max(initial),
            "unit": base["unit"],
            "detection_stage": "incoming_inspection",
            "evidence": evidence,
            "flags": flags,
        }

    history = [
        {
            "history_id": "QT-HIST-001",
            "data_origin": "synthetic_demo",
            "pattern": "old_tooling_after_spec_change",
            "problem": "合成历史批次在新规格生效后仍使用旧工装，尺寸出现高侧偏差。",
            "confirmed_root_cause": "工装切换清单未覆盖该产品族。",
            "key_evidence": ["规格生效日期早于收货日期", "换型记录仍为旧版本", "有效设备复测仍超上限"],
            "action": "补齐换型清单、锁定旧工装并按新规格复检。",
            "effectiveness": "5 件复检均在规格内并由质量负责人确认。",
            "role": "confirming_analogue",
            "use_limit": "只能提出检查方向，不能证明当前案件根因。"
        },
        {
            "history_id": "QT-HIST-002",
            "data_origin": "synthetic_demo",
            "pattern": "expired_calibration_false_alarm",
            "problem": "合成历史批次初测超差，但检测设备校准已过期。",
            "confirmed_root_cause": "测量系统失效造成误报，产品经有效设备复测合格。",
            "key_evidence": ["校准有效期早于检验日期", "两台设备结果不一致", "有效设备复测全部合格"],
            "action": "停用过期设备、复测受影响批次并补充校准到期提醒。",
            "effectiveness": "受影响批次完成复测，未确认产品规格偏差。",
            "role": "alternative_cause",
            "use_limit": "用于提醒检查测量系统；当前案件设备校准有效，因此不能直接套用。"
        },
        {
            "history_id": "QT-HIST-003",
            "data_origin": "synthetic_demo",
            "pattern": "mixed_lot_object_mismatch",
            "problem": "合成历史调查把相邻批次的检验记录错误绑定到目标案件。",
            "confirmed_root_cause": "扫码后人工复制批次号时发生对象串联。",
            "key_evidence": ["批次号不一致", "供应商号不一致", "目标批次缺少自己的检验记录"],
            "action": "阻断跨批次引用并要求重新采集目标对象证据。",
            "effectiveness": "对象校验阻止了错误批次的后续措施创建。",
            "role": "object_boundary_warning",
            "use_limit": "只用于对象一致性门禁，不参与当前根因投票。"
        }
    ]

    bundle = {
        "schema_version": 1,
        "dataset_id": spec["dataset_id"],
        "generator_version": spec["generator_version"],
        "seed": spec["seed"],
        "policy_set_id": registry["policy_set_id"],
        "cases": cases,
        "history": history,
        "evidence_files": evidence_files,
    }
    errors = validate_bundle(bundle, spec, registry)
    if errors:
        raise ValueError("合成数据未通过约束：" + "; ".join(errors))
    return bundle


def _evidence_map(case: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["evidence_id"]: item for item in case["evidence"]}


def _same_evidence(left: dict[str, Any], right: dict[str, Any], evidence_id: str) -> bool:
    left_item = deepcopy(_evidence_map(left)[evidence_id])
    right_item = deepcopy(_evidence_map(right)[evidence_id])
    left_item.pop("source", None)
    right_item.pop("source", None)
    return left_item == right_item


def validate_bundle(bundle: dict[str, Any], spec: dict[str, Any], registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    cases = bundle.get("cases", {})
    expected_kinds = [item["kind"] for item in spec["variants"]]
    if list(cases) != expected_kinds:
        errors.append(f"case kinds mismatch: {list(cases)}")
    if len({case.get("case_id") for case in cases.values()}) != len(cases):
        errors.append("case_id must be unique")

    policy_ids = {item["policy_id"] for item in registry["policies"]}
    nominal = float(spec["base_case"]["required_value"])
    tolerance = float(spec["base_case"]["tolerance"])
    for kind, case in cases.items():
        if case.get("data_origin") != "synthetic_demo":
            errors.append(f"{kind}: non-synthetic origin")
        if case.get("dataset_id") != spec["dataset_id"]:
            errors.append(f"{kind}: dataset_id mismatch")
        ids = [item["evidence_id"] for item in case["evidence"]]
        if len(ids) != len(set(ids)):
            errors.append(f"{kind}: duplicate evidence id")
        for item in case["evidence"]:
            if not item.get("policy_refs") or not set(item["policy_refs"]).issubset(policy_ids):
                errors.append(f"{kind}/{item['evidence_id']}: unresolved policy ref")
            if item["source"] not in bundle["evidence_files"]:
                errors.append(f"{kind}/{item['evidence_id']}: missing generated source")
        inspection = _evidence_map(case).get("EV-INSPECTION")
        if inspection:
            readings = inspection["attributes"].get("readings", [])
            calculated = sum(_reading_status(float(value), nominal, tolerance) == "rejected" for value in readings)
            if calculated != inspection["attributes"].get("out_of_spec"):
                errors.append(f"{kind}: initial out_of_spec mismatch")
        effectiveness = _evidence_map(case).get("EV-EFFECTIVENESS")
        if effectiveness:
            readings = effectiveness["attributes"].get("readings", [])
            calculated = sum(_reading_status(float(value), nominal, tolerance) == "rejected" for value in readings)
            if calculated != effectiveness["attributes"].get("out_of_spec"):
                errors.append(f"{kind}: effectiveness out_of_spec mismatch")

    if cases:
        complete = cases.get("complete", {})
        required = set(registry["workflow_rules"]["required_evidence_ids"])
        if not required.issubset(_evidence_map(complete)):
            errors.append("complete: required evidence missing")
        missing = cases.get("missing_evidence", {})
        if set(_evidence_map(complete)) - set(_evidence_map(missing)) != {"EV-SUPPLIER"}:
            errors.append("missing_evidence must remove only EV-SUPPLIER")
        conflict = cases.get("conflict", {})
        if set(_evidence_map(conflict)) - set(_evidence_map(complete)) != {"EV-CONFLICT"}:
            errors.append("conflict must add only EV-CONFLICT")
        wrong = cases.get("wrong_object", {})
        for evidence_id in set(_evidence_map(complete)) - {"EV-BATCH"}:
            if not _same_evidence(complete, wrong, evidence_id):
                errors.append(f"wrong_object changed {evidence_id}")
        recovery = cases.get("tool_failure_recovery", {})
        for evidence_id in _evidence_map(complete):
            if not _same_evidence(complete, recovery, evidence_id):
                errors.append(f"tool_failure_recovery changed {evidence_id}")

    history = bundle.get("history", [])
    if len(history) != 3 or any(item.get("data_origin") != "synthetic_demo" for item in history):
        errors.append("history must contain exactly three synthetic cases")
    return errors


def generate_dataset(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    data_root = project_root / "data"
    generated_root = data_root / "generated"
    spec = _read_json(data_root / "generation_spec.json")
    registry = _read_json(data_root / "rule_registry.json")
    bundle = build_dataset(spec, registry)
    generated_root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for relative, content in sorted(bundle["evidence_files"].items()):
        path = project_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="")
        written.append(path)

    cases_path = generated_root / "cases.json"
    cases_path.write_text(_json_text({
        "schema_version": bundle["schema_version"],
        "dataset_id": bundle["dataset_id"],
        "generator_version": bundle["generator_version"],
        "seed": bundle["seed"],
        "policy_set_id": bundle["policy_set_id"],
        "cases": bundle["cases"],
    }), encoding="utf-8", newline="")
    written.append(cases_path)

    history_path = generated_root / "history_cases.json"
    history_path.write_text(_json_text({
        "schema_version": 1,
        "dataset_id": bundle["dataset_id"],
        "history": bundle["history"],
    }), encoding="utf-8", newline="")
    written.append(history_path)

    input_paths = [
        data_root / "generation_spec.json",
        data_root / "rule_registry.json",
        data_root / "source_register.json",
        data_root / "schemas" / "qualitytrace_case.schema.json",
        Path(__file__),
    ]
    input_paths.extend(data_root / item["file"] for item in registry["policies"])
    manifest = {
        "schema_version": 2,
        "dataset_id": bundle["dataset_id"],
        "generator_version": bundle["generator_version"],
        "seed": bundle["seed"],
        "origin": "synthetic_demo",
        "not_real_customer_data": True,
        "not_production_deployment": True,
        "case_count": len(bundle["cases"]),
        "history_case_count": len(bundle["history"]),
        "evidence_file_count": len(bundle["evidence_files"]),
        "inputs": [
            {"path": path.relative_to(project_root).as_posix(), "sha256": _sha256(path)}
            for path in sorted(input_paths)
        ],
        "generated_files": [
            {"path": path.relative_to(project_root).as_posix(), "sha256": _sha256(path)}
            for path in sorted(written)
        ],
        "generation_contract": spec["generation_contract"],
    }
    manifest_path = generated_root / "manifest.json"
    manifest_path.write_text(_json_text(manifest), encoding="utf-8", newline="")
    return manifest


def validate_persisted_dataset(project_root: Path = PROJECT_ROOT) -> dict[str, Any]:
    data_root = project_root / "data"
    spec = _read_json(data_root / "generation_spec.json")
    registry = _read_json(data_root / "rule_registry.json")
    expected = build_dataset(spec, registry)
    persisted = _read_json(data_root / "generated" / "cases.json")
    history = _read_json(data_root / "generated" / "history_cases.json")
    manifest = _read_json(data_root / "generated" / "manifest.json")

    errors: list[str] = []
    if persisted.get("cases") != expected["cases"]:
        errors.append("persisted cases differ from deterministic generation")
    if history.get("history") != expected["history"]:
        errors.append("persisted history differs from deterministic generation")
    for row in manifest.get("inputs", []) + manifest.get("generated_files", []):
        path = project_root / row["path"]
        if not path.is_file():
            errors.append(f"missing manifest file: {row['path']}")
        elif _sha256(path) != row["sha256"]:
            errors.append(f"hash mismatch: {row['path']}")
    for relative, content in expected["evidence_files"].items():
        path = project_root / relative
        if not path.is_file() or path.read_text(encoding="utf-8") != content:
            errors.append(f"evidence content mismatch: {relative}")

    return {
        "valid": not errors,
        "errors": errors,
        "dataset_id": expected["dataset_id"],
        "case_count": len(expected["cases"]),
        "history_case_count": len(expected["history"]),
        "evidence_file_count": len(expected["evidence_files"]),
    }
