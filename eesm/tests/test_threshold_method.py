"""Threshold-freeze method: roles, instrument, floors. No manifest edit."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from validation.gates import REQUIRED_GATES, evaluate_gates
from validation.threshold_method import (
    COMPETING_FAMILIES,
    DESIGN_KEYS,
    FLOORS,
    FORBIDDEN_ROLES,
    ThresholdMethodRefusal,
    campaign_data_qa,
    idw_predict,
    instrument_gate_values,
    propose_thresholds,
)


def test_idw_reproduces_an_exact_neighbour():
    train_x = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]])
    train_y = np.array([[0.1, 0.2], [0.3, 0.4]])
    pred = idw_predict(train_x, train_y, np.array([[0.0, 0.0, 0.0]]))
    assert pred[0] == pytest.approx(train_y[0])


def test_instrument_refuses_selection_and_audit():
    train = [{
        "role": "selection", "region": "interior",
        "id_a": -40, "iq_a": 40, "if_a": 6,
        "lambda_d_wb": 0.1, "lambda_q_wb": 0.05,
    }]
    hold = [{
        "role": "train", "region": "interior",
        "id_a": -30, "iq_a": 30, "if_a": 5,
        "lambda_d_wb": 0.1, "lambda_q_wb": 0.05,
    }]
    machine = {
        "pole_pairs": 2, "rs_ohm": 0.05, "rf_ohm": 8.0, "vdc_v": 400.0,
        "i_s_max_peak_a": 120.0, "i_f_min_a": 0.0, "i_f_max_a": 15.0,
    }
    with pytest.raises(ThresholdMethodRefusal, match="forbidden role"):
        instrument_gate_values(train, hold, machine)


def test_campaign_data_qa_is_zero_on_clean_rows():
    rows = [{
        "id_a": "-1", "iq_a": "2", "if_a": "3",
        "lambda_d_wb": "0.1", "lambda_q_wb": "0.2",
        "torque_identity_nm": "1.0", "converged": "True",
    }]
    assert campaign_data_qa(rows) == 0.0


def test_proposal_uses_floors_and_excludes_competitors():
    def row(pid, region, id_a, iq_a, if_a):
        return {
            "point_id": pid, "role": "train", "region": region,
            "id_a": str(id_a), "iq_a": str(iq_a), "if_a": str(if_a),
            "lambda_d_wb": "0.05", "lambda_q_wb": "0.04",
            "torque_identity_nm": "1.0", "converged": "True",
        }

    campaign = []
    designs = {key: [] for key in DESIGN_KEYS}
    # Two disjoint 8-point clouds plus holdout mass.
    for i in range(8):
        pid = f"t{i:015d}"
        campaign.append(row(pid, "interior", -10 - i, 10 + i, 2 + 0.1 * i))
        designs["tensor_grid_64"].append(pid)
    for i in range(8):
        pid = f"r{i:015d}"
        campaign.append(row(pid, "saturation", -20 - i, 20 + i, 12))
        designs["random_64"].append(pid)
    for i in range(8):
        pid = f"l{i:015d}"
        campaign.append(row(pid, "field_weakening", -100, 5 + i, 3))
        designs["latin_hypercube_64"].append(pid)
    for i in range(12):
        campaign.append(row(
            f"h{i:015d}", "boundary" if i < 3 else "interior",
            -50 - i, 40, 6,
        ))
    machine = {
        "pole_pairs": 2, "rs_ohm": 0.05, "rf_ohm": 8.0, "vdc_v": 400.0,
        "i_s_max_peak_a": 120.0, "i_f_min_a": 0.0, "i_f_max_a": 15.0,
    }
    payload = propose_thresholds(campaign, designs, machine)
    assert payload["status"] == "proposal_not_frozen"
    assert payload["selection_used"] is False
    assert payload["scheduler_audit_used"] is False
    assert "rbf_or_gp" in payload["competing_families_excluded"]
    for family in COMPETING_FAMILIES:
        assert family not in payload["instrument"]
    for role in FORBIDDEN_ROLES:
        assert role not in json.dumps(payload["designs"])
    proposed = payload["proposed_thresholds"]
    assert set(proposed) == set(REQUIRED_GATES)
    for gate, floor in FLOORS.items():
        assert proposed[gate] >= floor
    # The proposal is a valid frozen-threshold *shape* for evaluate_gates.
    gates = evaluate_gates(
        {"gate_values": {gate: 0.0 for gate in REQUIRED_GATES}},
        {"status": "frozen", "thresholds": proposed},
    )
    assert gates["all_required_pass"] is True
