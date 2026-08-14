"""Zero-shot seed-study contract. Gauge must not see selection."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experiments import equal_budget
from experiments.zero_shot_seed_study import run_zero_shot_seed_study
from synthetic.synthetic_map import SyntheticEESMMap


EESM_ROOT = Path(__file__).resolve().parents[1]


class _ToyThreeChannel:
    def evaluate(self, X):
        ld, lq = SyntheticEESMMap().flux(X[:, 0], X[:, 1], X[:, 2])
        return np.column_stack([ld, lq, 0.02 * X[:, 2] + 0.001 * X[:, 0]])


def test_zero_shot_seed_study_smoke(tmp_path: Path):
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
        "field_supervision": False,
    }
    domain = equal_budget._domain_from_manifest(manifest)
    selection = equal_budget.latin_hypercube_samples(domain, n=16, seed=5)
    summary = run_zero_shot_seed_study(
        manifest,
        _ToyThreeChannel(),
        [str(value) for value in selection["point_id"]],
        equal_budget._sample_matrix(selection),
        tmp_path,
        n_seeds=2,
    )
    assert summary["status"] == "completed"
    assert summary["selection_used_for_gauge"] is False
    assert summary["field_supervision"] is False
    assert len(summary["runs"]) == 2
    assert "tensor_grid|16" in summary["by_cell"]
    assert summary["runs"][0]["gauge"]["fitted_on"] == "train_role_only"
