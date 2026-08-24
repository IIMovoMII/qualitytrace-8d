import json
from pathlib import Path

from qualitytrace.data_factory import build_dataset, validate_bundle, validate_persisted_dataset
from qualitytrace.fixtures import all_cases


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_generation_is_deterministic_and_constraint_valid():
    spec = _load("generation_spec.json")
    registry = _load("rule_registry.json")
    first = build_dataset(spec, registry)
    second = build_dataset(spec, registry)
    assert first == second
    assert validate_bundle(first, spec, registry) == []
    assert len(first["cases"]) == 5
    assert len(first["history"]) == 3
    assert len(first["evidence_files"]) == 25


def test_persisted_dataset_matches_generator_and_hash_manifest():
    result = validate_persisted_dataset(ROOT)
    assert result["valid"], result["errors"]
    assert result["case_count"] == 5
    assert result["history_case_count"] == 3


def test_every_evidence_source_and_policy_reference_resolves_locally():
    registry = _load("rule_registry.json")
    policy_ids = {item["policy_id"] for item in registry["policies"]}
    for row in registry["policies"]:
        text = (DATA / row["file"]).read_text(encoding="utf-8")
        assert "not_real_company_policy: true" in text
    for case in all_cases().values():
        assert case.data_origin == "synthetic_demo"
        assert case.dataset_id == "QT8D-SYNTHETIC-20260821-A"
        for evidence in case.evidence:
            assert (ROOT / evidence.source).is_file()
            assert evidence.policy_refs
            assert set(evidence.policy_refs).issubset(policy_ids)


def test_generated_variants_change_only_the_declared_dimension():
    cases = all_cases()
    complete = {item.evidence_id: item for item in cases["complete"].evidence}
    missing = {item.evidence_id: item for item in cases["missing_evidence"].evidence}
    conflict = {item.evidence_id: item for item in cases["conflict"].evidence}
    wrong = {item.evidence_id: item for item in cases["wrong_object"].evidence}
    assert set(complete) - set(missing) == {"EV-SUPPLIER"}
    assert set(conflict) - set(complete) == {"EV-CONFLICT"}
    assert wrong["EV-BATCH"].attributes["lot_id"] != cases["wrong_object"].lot_id
    for evidence_id in set(complete) - {"EV-BATCH"}:
        assert wrong[evidence_id].text == complete[evidence_id].text
        assert wrong[evidence_id].attributes == complete[evidence_id].attributes
