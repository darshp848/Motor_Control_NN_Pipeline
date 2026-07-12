"""Manifest and clean motor params schema tests."""

import os

from pipeline.manifest import (
    MOTOR_PARAMS_REQUIRED_KEYS,
    load_experiment_manifest,
    load_json,
    validate_motor_params,
    clean_motor_params_from_raw,
)


def test_manifest_required_keys():
    path = os.path.join("configs", "ipm_experiment_manifest.json")
    assert os.path.exists(path)
    m = load_experiment_manifest(path)
    for key in ("seeds", "paths", "training_domain", "machine", "inference_selection"):
        assert key in m
    assert m["seeds"]["train_val_test_split"] == 0
    assert m["inference_selection"] == "off_grid_in_domain"


def test_ipm_freeze_manifest_remains_stage0_specific():
    manifest = load_experiment_manifest("configs/ipm_experiment_manifest.json")
    assert manifest["machine"]["type"] == "IPM"
    assert manifest["freeze_status"] == "offline_frozen_audit_ready"


def test_motor_params_clean_schema():
    path = os.path.join("data", "motor_params_clean.json")
    params = load_json(path)
    missing = validate_motor_params(params, strict=False)
    assert missing == []
    assert params["pole_pairs"] == 2
    assert params["poles"] == 4
    assert params["flux_scale"] > 1.0


def test_clean_from_raw_strips_noise():
    raw = {
        "poles": 4,
        "pole_pairs": 2,
        "rs_ohm": 2.1,
        "vdc_v": 311,
        "i_max_peak_a": 6,
        "i_rated_peak_a": 4.0,
        "rated_current_rms_a": 2.8,
        "t_rated_nm": 2.9,
        "flux_scale": 11.8,
        "omega_mech_base_rpm": 1800,
        "omega_mech_max_rpm": None,
        "poststate": {"messages_after": {"global_errors": {"value": ["noise"]}}},
    }
    clean = clean_motor_params_from_raw(raw)
    assert "poststate" not in clean
    assert clean["omega_mech_max_rpm"] == 6000.0
    for k in MOTOR_PARAMS_REQUIRED_KEYS:
        assert k in clean
