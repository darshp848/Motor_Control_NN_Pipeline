"""CPU Torch determinism and same-seed energy-net identity. No FEMM."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch

from experiments.energy_seed_study import run_energy_seed_study
from surrogates.registry import build_surrogate
from surrogates.torch_determinism import configure_torch_determinism
from synthetic.synthetic_map import SyntheticEESMMap


EESM_ROOT = Path(__file__).resolve().parents[1]


def _toy_data(n: int = 24, seed: int = 1):
    rng = np.random.default_rng(seed)
    X = rng.uniform([-80.0, 10.0, 1.0], [-10.0, 80.0, 10.0], size=(n, 3))
    y = np.column_stack(
        [0.004 * X[:, 0] + 0.005 * X[:, 2], 0.002 * X[:, 1], 0.02 * X[:, 2]]
    )
    return X, y


def test_configure_torch_determinism_sets_single_thread():
    payload = configure_torch_determinism(1701, num_threads=1)
    assert payload["torch_deterministic_algorithms"] is True
    assert payload["num_threads"] == 1
    assert payload["device"] == "cpu"
    assert torch.are_deterministic_algorithms_enabled()


def test_energy_net_same_seed_matches_exactly():
    X, y = _toy_data()
    config = {"epochs": 40, "hidden_width": 16, "num_threads": 1}
    first = build_surrogate("energy_gradient_net", 7, config)
    first.fit(X, y)
    pred_a = first.predict(X)
    second = build_surrogate("energy_gradient_net", 7, config)
    second.fit(X, y)
    pred_b = second.predict(X)
    assert pred_a == pytest.approx(pred_b, abs=0.0, rel=0.0)


def test_energy_net_different_seeds_differ():
    X, y = _toy_data()
    config = {"epochs": 40, "hidden_width": 16, "num_threads": 1}
    a = build_surrogate("energy_gradient_net", 1, config)
    b = build_surrogate("energy_gradient_net", 2, config)
    a.fit(X, y)
    b.fit(X, y)
    assert not np.allclose(a.predict(X), b.predict(X))


def test_v2_2_manifest_adds_determinism_without_retuning_gates():
    v21 = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2_1.json").read_text(
            encoding="utf-8"
        )
    )
    v22 = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2_2.json").read_text(
            encoding="utf-8"
        )
    )
    assert v21["gates"]["thresholds"] == v22["gates"]["thresholds"]
    assert v22["determinism"]["torch_deterministic_algorithms"] is True
    assert v22["determinism"]["report_seeds"] == 8
    assert v22["determinism"]["rank_on"] == "median_torque_rmse_nm"
    assert "determinism" not in v21


class _ToyThreeChannel:
    def __init__(self):
        self.oracle = SyntheticEESMMap()

    def evaluate(self, X):
        ld, lq = self.oracle.flux(X[:, 0], X[:, 1], X[:, 2])
        lf = 0.02 * X[:, 2]
        return np.column_stack([ld, lq, lf])


def test_energy_seed_study_smoke(tmp_path: Path):
    manifest = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2_2.json").read_text(
            encoding="utf-8"
        )
    )
    manifest["budgets"] = [16]
    manifest["sampling"] = {"baseline_strategies": ["tensor_grid"]}
    manifest["surrogate_configs"]["energy_gradient_net"] = {
        "epochs": 8,
        "hidden_width": 8,
        "num_threads": 1,
    }
    from experiments import equal_budget

    domain = equal_budget._domain_from_manifest(manifest)
    selection = equal_budget.latin_hypercube_samples(domain, n=16, seed=3)
    summary = run_energy_seed_study(
        manifest,
        _ToyThreeChannel(),
        [str(value) for value in selection["point_id"]],
        equal_budget._sample_matrix(selection),
        tmp_path,
        n_seeds=2,
    )
    assert summary["status"] == "completed"
    assert len(summary["runs"]) == 2
    assert "tensor_grid|16" in summary["by_cell"]
    assert summary["by_cell"]["tensor_grid|16"]["torque_rmse_nm"]["n"] == 2
