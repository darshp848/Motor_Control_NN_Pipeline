"""Tests for the Phase 1 diagnostics: reciprocity, L_diff, and the field gauge.

The conventions under test are fixed in `eesm/docs/DQ_CONVENTIONS.md`. Several
tests deliberately pin the WRONG form as well, because the naive identity is
off by roughly three orders of magnitude on the measured anchors and a silent
regression to it would be hard to see in aggregate numbers.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from metrics import field_gauge, ldiff  # noqa: E402
from metrics import reciprocity as recip  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402


# ----------------------------------------------------------------------
# an exactly conservative analytic machine
# ----------------------------------------------------------------------
def _potential_flux(X: np.ndarray) -> np.ndarray:
    """Gradient of W' = a*id^2 + b*iq^2 + c*If^2 + d*id*iq + e*id*If + f*iq*If.

    Returns (lambda_d, lambda_q, lambda_f_terminal) in the amplitude-invariant
    convention, so every reciprocity identity holds exactly by construction.
    """
    id_a, iq_a, if_a = X[:, 0], X[:, 1], X[:, 2]
    a, b, c, d, e, f = 1e-3, 8e-4, 2e-2, 3e-4, 5e-3, 2e-3
    dW_did = 2 * a * id_a + d * iq_a + e * if_a
    dW_diq = 2 * b * iq_a + d * id_a + f * if_a
    dW_dif = 2 * c * if_a + e * id_a + f * iq_a
    return np.column_stack([(2 / 3) * dW_did, (2 / 3) * dW_diq, dW_dif])


def _non_conservative_flux(X: np.ndarray) -> np.ndarray:
    """Same shape, but lambda_f's id-dependence is deliberately inconsistent."""
    out = _potential_flux(X)
    out[:, 2] = out[:, 2] + 0.01 * X[:, 0]
    return out


@pytest.fixture
def points() -> np.ndarray:
    rng = np.random.default_rng(20260710)
    return np.column_stack([
        rng.uniform(-110.0, -10.0, 40),
        rng.uniform(10.0, 110.0, 40),
        rng.uniform(1.0, 14.0, 40),
    ])


# ----------------------------------------------------------------------
# central_jacobian
# ----------------------------------------------------------------------
def test_central_jacobian_matches_analytic_derivative(points):
    J = recip.central_jacobian(_potential_flux, points)
    assert J.shape == (len(points), 3, 3)
    # d lambda_d / d id = (2/3) * 2a
    assert J[:, 0, 0] == pytest.approx((2 / 3) * 2e-3, rel=1e-9)
    # d lambda_f / d If = 2c
    assert J[:, 2, 2] == pytest.approx(4e-2, rel=1e-9)


def test_central_jacobian_rejects_bad_shapes():
    with pytest.raises(ValueError):
        recip.central_jacobian(_potential_flux, np.zeros((4, 2)))
    with pytest.raises(ValueError):
        recip.central_jacobian(_potential_flux, np.zeros((0, 3)))


def test_steps_match_the_fd_anchor_design():
    """A surrogate Jacobian must use the same secant as the FEM anchors."""
    assert recip.DEFAULT_STEPS == (1.0, 1.0, 0.2)


# ----------------------------------------------------------------------
# reciprocity
# ----------------------------------------------------------------------
def test_conservative_model_satisfies_every_identity(points):
    r = recip.reciprocity_residuals(_potential_flux, points)
    assert np.abs(r["R_dq"]).max() < 1e-12
    assert np.abs(r["R_fd"]).max() < 1e-12
    assert np.abs(r["R_fq"]).max() < 1e-12


def test_naive_identity_is_violated_by_a_correct_model(points):
    """The 3/2 is real: a correct model must FAIL the naive equality."""
    r = recip.reciprocity_residuals(_potential_flux, points)
    assert np.abs(r["R_fd_naive"]).max() > 1e-4
    assert np.abs(r["R_fd"]).max() < 1e-12


def test_non_conservative_model_is_caught(points):
    r = recip.reciprocity_residuals(_non_conservative_flux, points)
    assert np.abs(r["R_dq"]).max() < 1e-12          # stator block still fine
    assert np.abs(r["R_fd"]).max() == pytest.approx(0.01, rel=1e-6)


def test_two_output_model_reports_only_the_stator_identity(points):
    r = recip.reciprocity_residuals(lambda X: _potential_flux(X)[:, :2], points)
    assert "R_dq" in r
    assert "R_fd" not in r


def test_interior_mask_excludes_points_without_step_room():
    X = np.array([
        [-60.0, 60.0, 7.0],     # interior
        [-0.5, 60.0, 7.0],      # id too close to 0
        [-60.0, 60.0, 14.9],    # If too close to 15
        [-119.5, 60.0, 7.0],    # id too close to -120
    ])
    assert recip.interior_mask(X).tolist() == [True, False, False, False]


def test_summarize_reports_ratio_to_the_fem_floor(points):
    r = recip.reciprocity_residuals(_non_conservative_flux, points)
    s = recip.summarize(r, floors={"R_fd": 4.0e-6})
    assert s["n_eval"] == len(points)
    assert s["R_fd"]["ratio_to_fem_floor"] > 1000.0


def test_fem_floors_read_the_terminal_not_the_raw_field_row():
    anchors = {"anchors": [{"inductance": {
        "reciprocity_dq": -1e-8,
        "reciprocity_fd_terminal_minus_1p5_Ldf": -2e-6,
        "reciprocity_fq_terminal_minus_1p5_Lqf": 1e-7,
        "reciprocity_fd_naive": -1e-2,
    }}]}
    floors = recip.fem_reciprocity_floors(anchors)
    assert floors["R_fd"] == pytest.approx(2e-6)
    assert floors["R_fd_naive"] == pytest.approx(1e-2)


# ----------------------------------------------------------------------
# L_diff
# ----------------------------------------------------------------------
def _synthetic_anchors() -> dict:
    centres = np.array([[-40.0, 50.0, 6.0], [-80.0, 20.0, 3.0]])
    J = recip.central_jacobian(_potential_flux, centres)
    records = []
    for row, centre in enumerate(centres):
        inductance = {}
        for name, o, i in ldiff.COMPONENTS:
            inductance[name] = float(J[row, o, i])
        records.append({
            "centre": {"id_a": centre[0], "iq_a": centre[1], "if_a": centre[2]},
            "inductance": inductance,
        })
    return {"anchors": records}


def test_ldiff_is_zero_against_its_own_generating_model():
    result = ldiff.ldiff_error(_potential_flux, _synthetic_anchors())
    assert result["frobenius_rel_rmse"] < 1e-12
    assert result["n_anchors"] == 2
    assert result["per_component"]["Lfd_terminal"]["available"] is True


def test_ldiff_penalizes_a_wrong_field_row():
    result = ldiff.ldiff_error(_non_conservative_flux, _synthetic_anchors())
    assert result["per_component"]["Lfd_terminal"]["abs_rmse_h"] == pytest.approx(
        0.01, rel=1e-6
    )


def test_ldiff_marks_the_field_row_unavailable_for_a_two_output_model():
    result = ldiff.ldiff_error(
        lambda X: _potential_flux(X)[:, :2], _synthetic_anchors()
    )
    assert result["n_outputs"] == 2
    assert result["per_component"]["Lfd_terminal"]["available"] is False
    assert result["per_component"]["Ldd"]["available"] is True


# ----------------------------------------------------------------------
# field gauge
# ----------------------------------------------------------------------
def test_gauge_recovers_a_known_offset_exactly():
    rng = np.random.default_rng(7)
    if_train = rng.uniform(0.5, 14.5, 200)
    truth = np.sin(if_train)
    offset = 0.3 + 0.05 * if_train - 0.002 * if_train ** 2
    gauge = field_gauge.fit_gauge(if_train, truth + offset, truth)
    assert np.allclose(gauge(if_train), offset, atol=1e-9)
    assert np.allclose(gauge.apply(truth + offset, if_train), truth, atol=1e-9)


def test_gauge_dimensionality_r2_is_one_for_a_pure_1d_offset():
    rng = np.random.default_rng(11)
    if_a = rng.uniform(0.5, 14.5, 300)
    truth = np.cos(if_a) + 0.1 * rng.standard_normal(300)
    offset = 0.2 + 0.03 * if_a
    gauge = field_gauge.fit_gauge(if_a, truth + offset, truth)
    r2 = field_gauge.gauge_dimensionality_r2(gauge, if_a, truth + offset, truth)
    assert r2 > 0.999


def test_gauge_cannot_absorb_id_structure():
    """A cubic in If must not soak up armature reaction -- that is the point."""
    rng = np.random.default_rng(5)
    if_a = rng.uniform(0.5, 14.5, 300)
    id_a = rng.uniform(-110.0, -10.0, 300)
    truth = np.cos(if_a)
    contaminated = truth + 0.01 * id_a          # depends on id, not If
    gauge = field_gauge.fit_gauge(if_a, contaminated, truth)
    r2 = field_gauge.gauge_dimensionality_r2(gauge, if_a, contaminated, truth)
    assert r2 < 0.2


def test_gauge_needs_enough_rows():
    with pytest.raises(ValueError):
        field_gauge.fit_gauge(np.array([1.0, 2.0]), np.array([0.1, 0.2]),
                              np.array([0.0, 0.0]))


def test_field_only_control_tracks_a_pure_field_curve():
    if_train = np.linspace(0.5, 14.5, 60)
    lam = 0.4 * if_train - 0.01 * if_train ** 2
    out = field_gauge.field_only_control(if_train, lam, if_train)
    assert np.allclose(out, lam, atol=1e-9)


# ----------------------------------------------------------------------
# the energy net itself
# ----------------------------------------------------------------------
@pytest.fixture
def training_set() -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(20260813)
    X = np.column_stack([
        rng.uniform(-110.0, -10.0, 120),
        rng.uniform(10.0, 110.0, 120),
        rng.uniform(1.0, 14.0, 120),
    ])
    return X, _potential_flux(X)


def test_energy_net_is_reciprocal_to_machine_precision(training_set):
    X, Y = training_set
    model = build_surrogate("energy_gradient_net", seed=1701,
                            config={"epochs": 60, "hidden_width": 16})
    model.fit(X, Y)
    r = recip.reciprocity_residuals(model.predict, X)
    # holds regardless of fit quality -- it is structural, not learned
    assert np.abs(r["R_dq"]).max() < 1e-6
    assert np.abs(r["R_fd"]).max() < 1e-5


def test_energy_net_supervises_three_channels_by_default(training_set):
    X, Y = training_set
    model = build_surrogate("energy_gradient_net", seed=1701,
                            config={"epochs": 20, "hidden_width": 8})
    model.fit(X, Y)
    assert model.n_outputs == 3
    assert model.predict(X).shape == (len(X), 3)


def test_energy_net_zero_shot_mode_still_exposes_the_field_channel(training_set):
    X, Y = training_set
    model = build_surrogate("energy_gradient_net", seed=1701,
                            config={"epochs": 20, "hidden_width": 8,
                                    "field_supervision": False})
    model.fit(X, Y[:, :2])
    assert model.n_outputs == 2
    assert model.predict(X).shape == (len(X), 2)
    assert model.predict_field(X).shape == (len(X),)


def test_energy_net_records_its_supervision_mode(training_set):
    X, Y = training_set
    model = build_surrogate("energy_gradient_net", seed=1701,
                            config={"epochs": 10, "hidden_width": 8,
                                    "field_supervision": False})
    model.fit(X, Y[:, :2])
    assert model.hyperparameters_["field_supervision"] is False
    assert model.hyperparameters_["supervised_channels"] == [
        "lambda_d_wb", "lambda_q_wb"
    ]


# ----------------------------------------------------------------------
# every family must accept three outputs
# ----------------------------------------------------------------------
@pytest.mark.parametrize("family", [
    "physics_polynomial", "rbf_or_gp", "tree_ensemble",
    "compact_mlp", "pwa", "energy_gradient_net",
])
def test_every_family_supports_three_outputs(family, training_set):
    X, Y = training_set
    config = {"epochs": 20, "hidden_width": 8} if "net" in family or "mlp" in family else {}
    model = build_surrogate(family, seed=1701, config=config)
    model.fit(X, Y)
    assert model.predict(X[:5]).shape == (5, 3)
