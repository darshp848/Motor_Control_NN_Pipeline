"""Tests for the predictive-uncertainty leg: GP std + calibration metrics.

Two layers:
  1. The surrogate interface: the GP exposes a non-negative predictive std in
     physical units of the right shape; point-estimate families refuse.
  2. evaluate_calibration: on synthetic data with a KNOWN true noise sigma, a
     model whose predicted sigma equals the truth is well-calibrated (coverage
     ~= nominal, small calibration error), an overconfident model under-covers,
     and error-vs-sigma discrimination is detected when sigma tracks error.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from validation.uncertainty import evaluate_calibration, _z_for  # noqa: E402


# ---------------------------------------------------------------------------
# surrogate interface
# ---------------------------------------------------------------------------

def _toy_training():
    rng = np.random.default_rng(0)
    X = rng.uniform(-1.0, 1.0, size=(40, 3))
    y = np.column_stack([X[:, 0] + 0.1 * X[:, 2], X[:, 1] - 0.05 * X[:, 0]])
    return X, y


def test_gp_exposes_predictive_std_shape_and_units():
    from surrogates.kernel import RBFOrGPSurrogate

    X, y = _toy_training()
    gp = RBFOrGPSurrogate(seed=1).fit(X, y)
    assert gp.provides_uncertainty is True
    std = gp.predict_std(X[:5])
    assert std.shape == (5, 2)
    assert np.all(std >= 0.0)
    assert np.all(np.isfinite(std))
    # std must be de-normalized to physical units: same order as y_scale, not ~1
    assert np.all(std < 10.0 * gp.y_scale_.max() + 1.0)


def test_point_estimate_family_refuses_std():
    from surrogates.polynomial import PhysicsPolynomialSurrogate

    X, y = _toy_training()
    model = PhysicsPolynomialSurrogate(seed=1).fit(X, y)
    assert model.provides_uncertainty is False
    with pytest.raises(NotImplementedError):
        model.predict_std(X[:3])


# ---------------------------------------------------------------------------
# calibration metrics
# ---------------------------------------------------------------------------

def _synthetic_case(sigma_true, sigma_pred, n=6000, seed=7):
    rng = np.random.default_rng(seed)
    truth = {"lambda_d_wb": rng.normal(0, 1, n), "lambda_q_wb": rng.normal(0, 1, n)}
    # predicted = truth + Gaussian noise of std sigma_true (so |error| ~ sigma_true)
    pred = {c: truth[c] + rng.normal(0, sigma_true, n) for c in truth}
    std = {c: np.full(n, sigma_pred) for c in truth}
    return truth, pred, std


def test_perfectly_calibrated_model_matches_nominal_coverage():
    truth, pred, std = _synthetic_case(sigma_true=0.2, sigma_pred=0.2)
    out = evaluate_calibration(truth, pred, std)
    cd = out["components"]["lambda_d_wb"]
    # empirical coverage within 2% of nominal at every level
    for level_key, block in cd["coverage"].items():
        assert abs(block["deviation"]) < 0.02, (level_key, block)
    assert cd["calibration_error"] < 0.01
    # standardized residuals ~ N(0,1)
    assert abs(cd["std_z"] - 1.0) < 0.05
    assert out["worst_component_calibration_error"] < 0.01


def test_overconfident_model_undercovers():
    # predicted sigma too small (half the true error scale) -> under-coverage
    truth, pred, std = _synthetic_case(sigma_true=0.2, sigma_pred=0.1)
    out = evaluate_calibration(truth, pred, std)
    cov95 = out["components"]["lambda_d_wb"]["coverage"]["0.9545"]
    assert cov95["empirical"] < 0.90            # should badly miss 95.45%
    assert out["components"]["lambda_d_wb"]["calibration_error"] > 0.1
    assert out["components"]["lambda_d_wb"]["std_z"] > 1.5  # residuals too wide


def test_underconfident_model_overcovers():
    truth, pred, std = _synthetic_case(sigma_true=0.1, sigma_pred=0.3)
    out = evaluate_calibration(truth, pred, std)
    cov68 = out["components"]["lambda_d_wb"]["coverage"]["0.6827"]
    assert cov68["empirical"] > 0.90            # far over 68%
    assert out["components"]["lambda_d_wb"]["std_z"] < 0.6


def test_discrimination_detects_sigma_tracking_error():
    # sigma proportional to |error| -> strong positive rank correlation
    rng = np.random.default_rng(3)
    n = 4000
    scale = rng.uniform(0.05, 0.5, n)
    err = rng.normal(0, 1, n) * scale
    truth = {"lambda_d_wb": np.zeros(n), "lambda_q_wb": np.zeros(n)}
    pred = {"lambda_d_wb": err, "lambda_q_wb": err}
    std = {"lambda_d_wb": scale, "lambda_q_wb": scale}
    out = evaluate_calibration(truth, pred, std)
    assert out["components"]["lambda_d_wb"]["error_sigma_spearman"] > 0.3


def test_region_stratified_calibration_reported():
    truth, pred, std = _synthetic_case(sigma_true=0.2, sigma_pred=0.2, n=4000)
    regions = np.where(np.arange(4000) % 2 == 0, "interior", "saturation")
    out = evaluate_calibration(truth, pred, std, regions=regions)
    assert set(out["by_region"]) == {"interior", "saturation"}
    assert "worst_region_calibration_error" in out
    assert out["by_region"]["interior"]["lambda_d_wb"]["n"] == 2000


def test_report_only_flags_present():
    truth, pred, std = _synthetic_case(sigma_true=0.2, sigma_pred=0.2, n=500)
    out = evaluate_calibration(truth, pred, std)
    assert out["report_only"] is True and out["is_gate"] is False


def test_negative_std_rejected():
    truth, pred, std = _synthetic_case(sigma_true=0.2, sigma_pred=0.2, n=100)
    std["lambda_d_wb"][0] = -1.0
    with pytest.raises(ValueError):
        evaluate_calibration(truth, pred, std)


def test_z_multipliers_match_known_values():
    assert abs(_z_for(0.9545) - 2.0) < 1e-3
    assert abs(_z_for(0.6827) - 1.0) < 1e-3
    assert abs(_z_for(0.99) - 2.5758) < 1e-3
