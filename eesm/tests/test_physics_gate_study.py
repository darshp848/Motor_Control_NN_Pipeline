"""Physics-gate rescore contract. Tiny synthetic matrix. No FEMM."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experiments import equal_budget
from experiments.physics_gate_study import (
    evaluate_physics_gates,
    run_physics_gate_study,
)
from synthetic.synthetic_map import SyntheticEESMMap


EESM_ROOT = Path(__file__).resolve().parents[1]


class _ToyThreeChannel:
    def evaluate(self, X):
        ld, lq = SyntheticEESMMap().flux(X[:, 0], X[:, 1], X[:, 2])
        return np.column_stack([ld, lq, 0.02 * X[:, 2]])


def _tiny_anchors():
    return {
        "anchors": [
            {
                "centre": {"id_a": -40.0, "iq_a": 40.0, "if_a": 6.0},
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
                    "reciprocity_dq": 1e-8,
                    "reciprocity_fd_terminal_minus_1p5_Ldf": 1e-6,
                    "reciprocity_fq_terminal_minus_1p5_Lqf": 1e-6,
                    "reciprocity_fd_naive": 0.01,
                },
            }
        ]
    }


def test_evaluate_physics_gates_all_must_pass():
    thresholds = {
        "R_dq_rms_h": 1.0,
        "R_fd_rms_h": 1.0,
        "R_fq_rms_h": 1.0,
        "ldiff_frobenius_rel": 1.0,
        "ldiff_offdiag_rel": 1.0,
    }
    values = dict(thresholds)
    values["R_dq_rms_h"] = 2.0
    result = evaluate_physics_gates(values, thresholds)
    assert result["all_required_pass"] is False
    assert result["gates"]["R_dq_rms_h"]["pass"] is False


def test_physics_gate_study_smoke(tmp_path: Path):
    manifest = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2_3.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["budgets"] = [16]
    manifest["sampling"] = {"baseline_strategies": ["tensor_grid"]}
    manifest["surrogates"] = ["physics_polynomial", "compact_mlp"]
    manifest["surrogate_configs"] = {
        "compact_mlp": {"epochs": 5, "hidden_width": 8, "num_threads": 1}
    }
    domain = equal_budget._domain_from_manifest(manifest)
    selection = equal_budget.latin_hypercube_samples(domain, n=16, seed=4)
    summary = run_physics_gate_study(
        manifest,
        _ToyThreeChannel(),
        [str(value) for value in selection["point_id"]],
        equal_budget._sample_matrix(selection),
        _tiny_anchors(),
        tmp_path,
        n_seeds=2,
    )
    assert summary["status"] == "completed"
    assert summary["ranking"]["n_cells"] == 2
    assert summary["ranking"]["promotion"]["status"] == "not_attempted"
    poly = summary["cells"]["tensor_grid|16|physics_polynomial"]
    mlp = summary["cells"]["tensor_grid|16|compact_mlp"]
    assert poly["n_seeds"] == 1
    assert mlp["n_seeds"] == 2
