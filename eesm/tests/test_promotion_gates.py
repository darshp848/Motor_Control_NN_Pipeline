"""Task 6 controller metrics, frozen gates, and promotion contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from synthetic.synthetic_map import SyntheticEESMMap
from validation.controller_metrics import evaluate_controller_metrics
from validation.gates import REQUIRED_GATES, evaluate_gates
from validation.promotion import promote_candidate


EESM_ROOT = Path(__file__).resolve().parents[1]


def _ranking_metrics(
    family: str,
    scheduler_loss_regret_w: float,
    torque_rmse_nm: float,
    flux_rmse_wb: float,
    training_runtime_s: float,
) -> dict:
    return {
        "family": family,
        "scheduler_loss_regret_w": scheduler_loss_regret_w,
        "torque_rmse_nm": torque_rmse_nm,
        "flux_rmse_wb": flux_rmse_wb,
        "training_runtime_s": training_runtime_s,
    }


def test_low_average_rmse_cannot_override_failed_boundary_gate() -> None:
    runs = [
        _ranking_metrics("good_interior_bad_boundary", 0.1, 0.1, 0.1, 1.0),
        _ranking_metrics("slightly_worse_all_gates_pass", 0.2, 0.2, 0.2, 2.0),
    ]
    gates = {
        "good_interior_bad_boundary": {"all_required_pass": False},
        "slightly_worse_all_gates_pass": {"all_required_pass": True},
    }

    decision = promote_candidate(
        runs, gates, policy="all_required_then_loss"
    )

    assert decision["status"] == "promoted"
    assert decision["family"] == "slightly_worse_all_gates_pass"


@pytest.fixture
def machine() -> dict:
    return {
        "pole_pairs": 2,
        "rs_ohm": 0.05,
        "rf_ohm": 8.0,
        "vdc_v": 400.0,
        "i_s_max_peak_a": 120.0,
        "i_f_min_a": 0.0,
        "i_f_max_a": 15.0,
    }


def test_controller_metrics_keep_unsupported_errors_out_of_interior(
    machine: dict,
) -> None:
    points = pd.DataFrame(
        {
            "id_a": [-20.0, -30.0, -40.0],
            "iq_a": [30.0, 40.0, 50.0],
            "if_a": [3.0, 4.0, 5.0],
            "region": ["interior", "interior", "unsupported"],
        }
    )
    fmap = SyntheticEESMMap()
    truth = np.column_stack(
        fmap.flux(points["id_a"], points["iq_a"], points["if_a"])
    )
    predicted = truth.copy()
    predicted[2, 0] += 0.1

    metrics = evaluate_controller_metrics(
        points, truth, predicted, machine, speeds_rpm=[0.0, 3000.0]
    )

    assert metrics["by_region"]["interior"]["n"] == 2
    assert metrics["by_region"]["interior"]["flux"]["lambda_d_wb"][
        "rmse"
    ] == 0.0
    unsupported = metrics["by_region"]["unsupported"]
    assert unsupported["n"] == 1
    assert unsupported["flux"]["lambda_d_wb"]["mae"] == pytest.approx(0.1)
    assert unsupported["flux"]["lambda_q_wb"]["rmse"] == 0.0
    assert unsupported["torque_nm"]["rmse"] > 0.0
    assert set(unsupported["voltage_magnitude_v"]) == {"0", "3000"}
    assert metrics["by_region"]["saturation"]["n"] == 0
    assert np.isnan(
        metrics["by_region"]["saturation"]["flux"]["lambda_d_wb"][
            "rmse"
        ]
    )
    # Empty regional slices are a vacuous pass (0.0), not NaN-fail.
    assert metrics["gate_values"]["saturation"] == 0.0
    assert np.isnan(metrics["gate_values"]["data_qa"])


def test_controller_metrics_report_feasibility_confusion_and_loss_regret(
    machine: dict,
) -> None:
    points = pd.DataFrame(
        {
            "id_a": [-20.0, -30.0, -40.0, -50.0],
            "iq_a": [30.0, 40.0, 50.0, 60.0],
            "if_a": [3.0, 4.0, 5.0, 6.0],
            "region": ["interior"] * 4,
            "truth_feasible": [True, True, False, False],
            "predicted_feasible": [True, False, True, False],
            "data_qa_passed": [True, True, True, False],
            "truth_id_a": [0.0, 0.0, np.nan, np.nan],
            "truth_iq_a": [0.0, 0.0, np.nan, np.nan],
            "truth_if_a": [1.0, 2.0, np.nan, np.nan],
            "predicted_id_a": [0.0, 0.0, np.nan, np.nan],
            "predicted_iq_a": [0.0, 0.0, np.nan, np.nan],
            "predicted_if_a": [1.1, 2.1, np.nan, np.nan],
        }
    )
    fmap = SyntheticEESMMap()
    truth = np.column_stack(
        fmap.flux(points["id_a"], points["iq_a"], points["if_a"])
    )

    metrics = evaluate_controller_metrics(
        points, truth, truth, machine, speeds_rpm=[1500.0]
    )

    assert metrics["feasibility_confusion"]["matrix"] == [[1, 1], [1, 1]]
    assert metrics["feasibility_confusion"]["error_rate"] == pytest.approx(0.5)
    regret = metrics["copper_loss_regret_w"]
    assert regret["n"] == 2
    assert regret["mean"] == pytest.approx((1.68 + 3.28) / 2.0)
    assert regret["max_abs"] == pytest.approx(3.28)
    assert metrics["data_qa"]["failure_rate"] == pytest.approx(0.25)
    assert metrics["gate_values"]["data_qa"] == pytest.approx(0.25)


def test_copper_loss_regret_rejects_unverified_caller_values(
    machine: dict,
) -> None:
    points = pd.DataFrame(
        {
            "id_a": [-20.0],
            "iq_a": [30.0],
            "if_a": [3.0],
            "region": ["interior"],
            "truth_p_cu_w": [10.0],
            "predicted_p_cu_w": [11.0],
        }
    )
    truth = np.array([[0.2, 0.1]])

    with pytest.raises(ValueError, match="scheduler current columns"):
        evaluate_controller_metrics(
            points, truth, truth, machine, speeds_rpm=[1500.0]
        )


def test_gate_evaluation_reports_unavailable_and_exceeded_metrics() -> None:
    thresholds = {gate: 1.0 for gate in REQUIRED_GATES}
    values = {gate: 0.1 for gate in REQUIRED_GATES}
    values["saturation"] = float("nan")
    values["boundary"] = 1.1

    result = evaluate_gates({"gate_values": values}, thresholds)

    assert result["all_required_pass"] is False
    saturation = result["gates"]["saturation"]
    assert np.isnan(saturation["value"])
    assert saturation["threshold"] == 1.0
    assert saturation["available"] is False
    assert saturation["passed"] is False
    assert saturation["reason"] == "metric_unavailable"
    assert result["gates"]["boundary"]["passed"] is False
    assert result["gates"]["boundary"]["reason"] == "threshold_exceeded"


def test_canonical_frozen_manifest_can_evaluate_gates() -> None:
    manifest = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    values = {gate: 0.0 for gate in REQUIRED_GATES}
    result = evaluate_gates({"gate_values": values}, manifest["gates"])
    assert result["all_required_pass"] is True

    unfrozen = dict(manifest["gates"])
    unfrozen["status"] = "baseline_required"
    with pytest.raises(ValueError, match="thresholds not frozen"):
        evaluate_gates({"gate_values": values}, unfrozen)


def test_promotion_uses_family_name_as_the_final_stable_tie_break() -> None:
    runs = [
        _ranking_metrics("z_family", 1.0, 1.0, 1.0, 1.0),
        _ranking_metrics("a_family", 1.0, 1.0, 1.0, 1.0),
    ]
    gates = {
        "z_family": {"all_required_pass": True},
        "a_family": {"all_required_pass": True},
    }

    decision = promote_candidate(
        runs, gates, policy="all_required_then_loss"
    )

    assert decision["family"] == "a_family"


def test_repeated_family_requires_candidate_specific_gate_results() -> None:
    runs = [
        {
            **_ranking_metrics("physics_polynomial", 1.0, 1.0, 1.0, 1.0),
            "strategy": "random",
            "budget": 64,
        },
        {
            **_ranking_metrics("physics_polynomial", 2.0, 2.0, 2.0, 2.0),
            "strategy": "tensor_grid",
            "budget": 64,
        },
    ]

    with pytest.raises(ValueError, match="candidate-specific gate result"):
        promote_candidate(
            runs,
            {"physics_polynomial": {"all_required_pass": True}},
            policy="all_required_then_loss",
        )


def test_no_promotion_is_recorded_when_every_candidate_fails() -> None:
    run = _ranking_metrics("compact_mlp", 1.0, 1.0, 1.0, 1.0)

    decision = promote_candidate(
        [run],
        {"compact_mlp": {"all_required_pass": False}},
        policy="all_required_then_loss",
    )

    assert decision["status"] == "no_promotion"
    assert decision["family"] is None
    assert decision["rejected_candidates"] == ["compact_mlp"]
