"""Tests for Stage 1 validation helpers (metrics + domain labels)."""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pytest

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from synthetic.synthetic_map import MapDomain, SyntheticEESMMap  # noqa: E402
from validation.synthetic_validation import (  # noqa: E402
    DOMAIN_LABELS,
    METRIC_KEYS,
    TORQUE_ERR_KEYS,
    VOLTAGE_ERR_KEYS,
    flux_rmse,
    label_domain_3d,
    torque_error,
    voltage_error,
    write_json_summary,
)


def test_flux_rmse_zero_on_identity():
    m = SyntheticEESMMap()
    id_ = np.array([-10.0, -50.0, -80.0])
    iq = np.array([20.0, 40.0, 90.0])
    if_ = np.array([1.0, 5.0, 10.0])
    ld, lq = m.flux(id_, iq, if_)
    metrics = flux_rmse(ld, lq, ld, lq)
    assert set(metrics.keys()) == set(METRIC_KEYS)
    assert metrics["n"] == 3
    assert metrics["rmse_lambda_d"] == 0.0
    assert metrics["rmse_lambda_q"] == 0.0
    assert metrics["rmse_flux_mean"] == 0.0
    assert all(np.isfinite(metrics[k]) for k in METRIC_KEYS if k != "n")


def test_flux_rmse_detects_bias():
    true = np.array([1.0, 2.0, 3.0])
    pred = true + 0.1
    metrics = flux_rmse(true, true, pred, pred)
    assert metrics["rmse_lambda_d"] == pytest.approx(0.1)
    assert metrics["rmse_flux_mean"] == pytest.approx(0.1)
    assert np.isfinite(metrics["rmse_lambda_q"])


def test_torque_and_voltage_error_keys_and_finite():
    t_true = np.array([10.0, 20.0, 30.0])
    t_pred = np.array([10.5, 19.0, 30.0])
    te = torque_error(t_true, t_pred)
    assert set(te.keys()) == set(TORQUE_ERR_KEYS)
    assert te["n"] == 3
    assert all(np.isfinite(te[k]) for k in TORQUE_ERR_KEYS if k != "n")
    assert te["mae_torque_nm"] == pytest.approx((0.5 + 1.0 + 0.0) / 3.0)

    v_true = np.array([100.0, 200.0])
    v_pred = np.array([110.0, 190.0])
    ve = voltage_error(v_true, v_pred)
    assert set(ve.keys()) == set(VOLTAGE_ERR_KEYS)
    assert ve["n"] == 2
    assert all(np.isfinite(ve[k]) for k in VOLTAGE_ERR_KEYS if k != "n")
    assert ve["max_abs_v_mag_v"] == pytest.approx(10.0)


def test_label_domain_3d_three_classes():
    domain = MapDomain(
        id_min_a=-100.0,
        id_max_a=0.0,
        iq_min_a=0.0,
        iq_max_a=100.0,
        if_min_a=0.0,
        if_max_a=10.0,
    )
    # Center-ish → interpolation; near edge → boundary; outside → extrapolation
    id_ = np.array([-50.0, -2.0, 50.0])
    iq = np.array([50.0, 2.0, 10.0])
    if_ = np.array([5.0, 0.2, 5.0])
    labels = label_domain_3d(id_, iq, if_, domain, boundary_fraction=0.05)
    assert labels[0] == "in_domain_interpolation"
    assert labels[1] == "boundary"
    assert labels[2] == "extrapolation"
    assert all(lab in DOMAIN_LABELS for lab in labels)


def test_write_json_summary(tmp_path):
    path = tmp_path / "summary.json"
    payload = {"ok": True, "n": 3, "keys": list(METRIC_KEYS)}
    write_json_summary(str(path), payload)
    with open(path, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == payload
