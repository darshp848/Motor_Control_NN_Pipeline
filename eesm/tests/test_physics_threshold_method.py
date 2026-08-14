"""Paper 2 physics-gate freeze: IDW instrument, no family fits."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

EESM_ROOT = Path(__file__).resolve().parents[1]

from validation.physics_threshold_method import (
    COMPETING_FAMILIES,
    PHYSICS_GATES,
    instrument_physics_values,
    make_idw_predictor,
    propose_physics_thresholds,
)
from validation.threshold_method import DESIGN_KEYS, ThresholdMethodRefusal


def _row(pid, role, id_a, iq_a, if_a):
    return {
        "point_id": pid,
        "role": role,
        "region": "interior",
        "id_a": str(id_a),
        "iq_a": str(iq_a),
        "if_a": str(if_a),
        "lambda_d_wb": str(0.002 * id_a + 0.01 * if_a),
        "lambda_q_wb": str(0.003 * iq_a),
        "lambda_field_wb": str(0.005 * if_a),
    }


def _anchors():
    centre = {"id_a": -40.0, "iq_a": 40.0, "if_a": 6.0}
    return {
        "anchors": [
            {
                "centre": centre,
                "inductance": {
                    "Ldd": 0.002,
                    "Ldq": 0.0,
                    "Ldf": 0.01,
                    "Lqd": 0.0,
                    "Lqq": 0.003,
                    "Lqf": 0.0,
                    "Lfd": 0.005,
                    "Lfd_terminal": 0.02,
                    "Lfq": 0.0,
                    "Lfq_terminal": 0.0,
                    "Lff": 0.005,
                    "Lff_terminal": 0.02,
                    "reciprocity_dq": 1.0e-8,
                    "reciprocity_fd_terminal_minus_1p5_Ldf": 1.0e-6,
                    "reciprocity_fq_terminal_minus_1p5_Lqf": 1.0e-6,
                    "reciprocity_fd_naive": 0.01,
                },
            }
        ]
    }


def test_idw_three_output_reproduces_exact_neighbour():
    rows = [_row("a", "train", -40.0, 40.0, 6.0), _row("b", "train", -30.0, 50.0, 7.0)]
    predict = make_idw_predictor(rows)
    pred = predict(np.array([[-40.0, 40.0, 6.0]]))
    assert pred.shape == (1, 3)
    assert pred[0, 0] == pytest.approx(0.002 * -40.0 + 0.01 * 6.0)


def test_instrument_refuses_selection_holdout():
    train = [_row("a", "train", -40.0, 40.0, 6.0)]
    hold = [_row("b", "selection", -30.0, 50.0, 7.0)]
    with pytest.raises(ThresholdMethodRefusal, match="forbidden role"):
        instrument_physics_values(train, hold, _anchors())


def test_proposal_excludes_competitors_and_forbidden_roles():
    campaign = []
    designs = {key: [] for key in DESIGN_KEYS}
    for name, prefix, id0 in (
        ("tensor_grid_64", "t", -50.0),
        ("random_64", "r", -60.0),
        ("latin_hypercube_64", "l", -70.0),
    ):
        for i in range(8):
            pid = f"{prefix}{i:03d}"
            campaign.append(_row(pid, "train", id0 - i, 20.0 + i, 4.0 + 0.2 * i))
            designs[name].append(pid)
    for i in range(12):
        campaign.append(_row(f"h{i:03d}", "train", -40.0 + i, 30.0 + i, 5.0))

    payload = propose_physics_thresholds(campaign, designs, _anchors())
    assert payload["selection_used"] is False
    assert payload["scheduler_audit_used"] is False
    assert payload["family_fits_used"] is False
    assert "energy_gradient_net" in COMPETING_FAMILIES
    assert set(payload["proposed_thresholds"]) == set(PHYSICS_GATES)
    assert "family" in payload["contamination_disclosure"].lower()
    for gate in PHYSICS_GATES:
        assert payload["proposed_thresholds"][gate] >= payload["floors"][gate]


def test_v2_3_physics_gates_do_not_retune_phase0():
    v22 = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2_2.json").read_text(
            encoding="utf-8"
        )
    )
    v23 = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2_3.json").read_text(
            encoding="utf-8"
        )
    )
    assert v22["gates"]["thresholds"] == v23["gates"]["thresholds"]
    assert v23["physics_gates"]["status"] == "frozen"
    assert set(v23["physics_gates"]["required"]) == set(PHYSICS_GATES)
