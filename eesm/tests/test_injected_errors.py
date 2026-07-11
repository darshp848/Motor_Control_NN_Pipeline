"""Task 3 contracts for injected-error sensitivity and physics invariants."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from scheduler.copper_loss_scheduler import (  # noqa: E402
    electromagnetic_torque_eesm,
)
from synthetic.error_models import inject_flux_error  # noqa: E402
from synthetic.synthetic_map import SyntheticEESMMap  # noqa: E402
from validation.physics_invariants import evaluate_invariants  # noqa: E402
from validation.synthetic_validation import flux_rmse, torque_error  # noqa: E402


@pytest.mark.parametrize(
    ("kind", "changed_component"),
    [
        ("d_bias", "d"),
        ("q_gain", "q"),
        ("saturation_local", "both"),
        ("cross_coupling", "both"),
    ],
)
def test_injected_error_changes_flux_and_worsens_downstream_metrics(
    kind, changed_component
):
    fmap = SyntheticEESMMap()
    currents = np.array(
        [
            [-110.0, 100.0, 13.0],
            [-90.0, 75.0, 10.0],
            [-60.0, 55.0, 7.0],
            [-25.0, 30.0, 4.0],
        ]
    )
    id_a, iq_a, if_a = currents.T
    ld_true, lq_true = fmap.flux(id_a, iq_a, if_a)
    ld_bad, lq_bad = inject_flux_error(
        ld_true, lq_true, kind=kind, magnitude=0.05, currents=currents
    )

    if changed_component in {"d", "both"}:
        assert not np.allclose(ld_bad, ld_true)
    if changed_component in {"q", "both"}:
        assert not np.allclose(lq_bad, lq_true)

    baseline_flux = flux_rmse(ld_true, lq_true, ld_true, lq_true)
    corrupted_flux = flux_rmse(ld_true, lq_true, ld_bad, lq_bad)
    torque_true = electromagnetic_torque_eesm(
        id_a, iq_a, ld_true, lq_true, pole_pairs=2
    )
    baseline_torque = torque_error(torque_true, torque_true)
    corrupted_torque = torque_error(
        torque_true,
        electromagnetic_torque_eesm(
            id_a, iq_a, ld_bad, lq_bad, pole_pairs=2
        ),
    )

    assert corrupted_flux["rmse_flux_mean"] > baseline_flux["rmse_flux_mean"]
    assert corrupted_torque["rmse_torque_nm"] > baseline_torque["rmse_torque_nm"]


def test_invariant_evaluation_covers_the_public_physics_contract():
    fmap = SyntheticEESMMap()
    points = {
        "id_a": np.array([-40.0, -40.0, -70.0, -100.0, 10.0]),
        "iq_a": np.array([50.0, 50.0, 65.0, 100.0, 20.0]),
        "if_a": np.array([2.0, 8.0, 7.0, 12.0, 5.0]),
        "rpm_mech": np.array([1500.0] * 5),
    }
    machine = {
        "pole_pairs": 2,
        "rs_ohm": 0.05,
        "i_s_max_peak_a": 120.0,
    }

    first = evaluate_invariants(fmap, points, machine)
    assert first["finite_flux"]
    assert first["deterministic_repeatability"]
    assert first["field_current_increases_lambda_d"]
    assert first["domain_containment"] == [True, True, True, True, False]
    assert first["finite_torque"]
    assert first["finite_voltage"]
    assert first["current_circle_labels"] == [
        "feasible",
        "feasible",
        "feasible",
        "infeasible",
        "feasible",
    ]
