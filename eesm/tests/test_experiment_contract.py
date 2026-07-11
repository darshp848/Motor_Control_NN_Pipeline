"""Contract tests for the foundry-first EESM experiment protocol."""

from __future__ import annotations

import json
from pathlib import Path


EESM_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = EESM_ROOT / "configs" / "eesm_experiment_manifest.json"
POINT_SCHEMA_PATH = EESM_ROOT / "schemas" / "eesm_point.schema.json"
RESULT_BUNDLE_SCHEMA_PATH = EESM_ROOT / "schemas" / "result_bundle.schema.json"

EXPECTED_POINT_COLUMNS = {
    "point_id",
    "role",
    "source",
    "region",
    "id_a",
    "iq_a",
    "if_a",
    "lambda_d_wb",
    "lambda_q_wb",
    "solver_status",
    "converged",
    "provenance_id",
}

EXPECTED_BUNDLE_KEYS = {
    "bundle_version",
    "experiment_id",
    "foundry_commit",
    "manifest_sha256",
    "created_utc",
    "inputs",
    "environment",
    "stages",
    "decisions",
    "artifacts",
    "gates",
}


def _load_contract(path: Path) -> dict:
    assert path.is_file(), f"missing contract file: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_declares_frozen_roles_and_baselines():
    manifest = _load_contract(MANIFEST_PATH)

    assert manifest["roles"] == [
        "train",
        "selection",
        "scheduler_audit",
        "reference",
    ]
    assert manifest["sampling"]["baseline_strategies"] == [
        "tensor_grid",
        "random",
        "latin_hypercube",
    ]
    assert manifest["sampling"]["sequential_enabled"] is False
    assert set(manifest["surrogates"]) == {
        "physics_polynomial",
        "rbf_or_gp",
        "tree_ensemble",
        "compact_mlp",
    }


def test_manifest_freezes_regions_budgets_seeds_and_problem_definition():
    manifest = _load_contract(MANIFEST_PATH)

    assert manifest["regions"] == [
        "interior",
        "boundary",
        "saturation",
        "field_weakening",
        "unsupported",
    ]
    assert manifest["budgets"] == [64, 128, 256]
    assert manifest["seeds"] == {
        "split": 20260710,
        "model": 1701,
        "scheduler_audit": 2909,
    }
    assert manifest["metrics"]["prediction_inputs"] == ["id_a", "iq_a", "if_a"]
    assert manifest["metrics"]["prediction_outputs"] == [
        "lambda_d_wb",
        "lambda_q_wb",
    ]
    assert manifest["metrics"]["optimization_objective"] == (
        "1.5 * rs_ohm * (id_a^2 + iq_a^2) + rf_ohm * if_a^2"
    )


def test_manifest_distinguishes_required_roles_and_isolates_scheduler_audit():
    manifest = _load_contract(MANIFEST_PATH)
    role_policy = manifest["role_policy"]

    assert role_policy["required"] == ["train", "selection", "scheduler_audit"]
    assert role_policy["optional"] == ["reference"]
    assert role_policy["scheduler_audit"] == {
        "available_only_after": "promotion",
        "prohibited_influences": [
            "sampling",
            "fitting",
            "hyperparameters",
            "budget_choice",
            "promotion",
        ],
        "allowed_influence": "release_acceptance",
    }


def test_manifest_blocks_promotion_until_required_thresholds_are_frozen():
    manifest = _load_contract(MANIFEST_PATH)
    gates = manifest["gates"]

    assert gates["status"] == "baseline_required"
    assert gates["promotion_blocked_until_frozen"] is True
    assert gates["required"] == [
        "data_qa",
        "interior",
        "boundary",
        "saturation",
        "field_weakening",
        "torque",
        "voltage",
        "feasibility",
    ]
    assert set(gates["thresholds"]) == set(gates["required"])
    assert all(value is None for value in gates["thresholds"].values())
    assert gates["promotion_policy"] == {
        "unfrozen_threshold_action": "reject",
        "required_gate_policy": "all_must_pass",
    }


def test_point_schema_requires_canonical_columns():
    point_schema = _load_contract(POINT_SCHEMA_PATH)

    assert set(point_schema["required"]) == EXPECTED_POINT_COLUMNS
    assert EXPECTED_POINT_COLUMNS <= set(point_schema["properties"])


def test_point_schema_freezes_role_and_region_vocabulary():
    point_schema = _load_contract(POINT_SCHEMA_PATH)

    assert point_schema["properties"]["role"]["enum"] == [
        "train",
        "selection",
        "scheduler_audit",
        "reference",
    ]
    assert point_schema["properties"]["region"]["enum"] == [
        "interior",
        "boundary",
        "saturation",
        "field_weakening",
        "unsupported",
    ]


def test_point_schema_reserves_future_flux_and_parallel_role_fields():
    point_schema = _load_contract(POINT_SCHEMA_PATH)

    assert point_schema["properties"]["lambda_f_wb"] is False
    assert point_schema["properties"]["roles"] is False


def test_result_bundle_schema_requires_frozen_root_keys_and_hashes():
    bundle_schema = _load_contract(RESULT_BUNDLE_SCHEMA_PATH)

    assert set(bundle_schema["required"]) == EXPECTED_BUNDLE_KEYS
    assert EXPECTED_BUNDLE_KEYS == set(bundle_schema["properties"])
    assert bundle_schema["properties"]["foundry_commit"]["pattern"] == (
        "^[0-9a-f]{40}$"
    )
    assert bundle_schema["properties"]["manifest_sha256"]["pattern"] == (
        "^[0-9a-f]{64}$"
    )


def test_result_bundle_schema_blocks_promotion_with_unfrozen_thresholds():
    bundle_schema = _load_contract(RESULT_BUNDLE_SCHEMA_PATH)
    promotion_guard = bundle_schema["allOf"][0]

    assert (
        promotion_guard["if"]["properties"]["gates"]["properties"]
        ["threshold_status"]["const"]
        == "baseline_required"
    )
    blocked_promotion = (
        promotion_guard["then"]["properties"]["decisions"]["properties"]
        ["promotion"]["properties"]
    )
    assert blocked_promotion["status"]["const"] == "blocked"
    assert blocked_promotion["candidate"]["type"] == "null"
