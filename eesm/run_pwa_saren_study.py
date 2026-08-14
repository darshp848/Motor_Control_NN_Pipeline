#!/usr/bin/env python
"""PWA physical-vs-normalized rescore and Sárén MTPA residual vs FEM anchors."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
REPO_ROOT = os.path.dirname(EESM_ROOT)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from experiments import equal_budget  # noqa: E402
from experiments.energy_seed_study import ThreeChannelFemmTruth  # noqa: E402
from experiments.phase2_strengthen import reserved_role_ids  # noqa: E402
from experiments.physics_gate_study import (  # noqa: E402
    evaluate_physics_gates,
    physics_gate_values,
)
from metrics.saren_mtpa import compare_at_anchors  # noqa: E402
from scheduler.copper_loss_scheduler import electromagnetic_torque_eesm  # noqa: E402
from surrogates.registry import build_surrogate  # noqa: E402


DEFAULT_MANIFEST = os.path.join(
    EESM_ROOT, "configs", "eesm_experiment_manifest_v2_3.json"
)
DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_ANCHORS = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_fd_anchors_20260813", "fd_anchors.json"
)
DEFAULT_OUT = os.path.join(REPO_ROOT, "out", "eesm", "pwa_saren_study_20260813")


def _score_cell(model, selection_X, selection_truth, pole_pairs, anchors, thresholds):
    predicted = model.predict(selection_X)
    torque = float(
        np.sqrt(
            np.mean(
                (
                    electromagnetic_torque_eesm(
                        selection_X[:, 0],
                        selection_X[:, 1],
                        predicted[:, 0],
                        predicted[:, 1],
                        pole_pairs,
                    )
                    - electromagnetic_torque_eesm(
                        selection_X[:, 0],
                        selection_X[:, 1],
                        selection_truth[:, 0],
                        selection_truth[:, 1],
                        pole_pairs,
                    )
                )
                ** 2
            )
        )
    )
    gates = evaluate_physics_gates(
        physics_gate_values(model.predict, selection_X, anchors), thresholds
    )
    saren = compare_at_anchors(model.predict, anchors)
    return {
        "torque_rmse_nm": torque,
        "physics_gates": gates,
        "saren": {
            "delta_e_rms_wba": saren["delta_e_rms_wba"],
            "newton_di_rms_a": saren["newton_di_rms_a"],
            "newton_di_max_a": saren["newton_di_max_a"],
        },
    }


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--anchors", default=DEFAULT_ANCHORS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    if out_root.exists() and any(out_root.iterdir()):
        print("REFUSED: non-empty output root %s" % out_root, file=sys.stderr)
        return 2
    out_root.mkdir(parents=True)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    thresholds = manifest["physics_gates"]["thresholds"]
    reserved = reserved_role_ids(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    strategies, budgets, families, seeds = equal_budget._validate_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    selection = equal_budget.latin_hypercube_samples(
        domain,
        n=max(budgets),
        seed=equal_budget._derived_seed(seeds["split"], "selection", max(budgets)),
    )
    selection_ids = [str(value) for value in selection["point_id"]]
    if selection_ids != reserved["selection"]:
        print("REFUSED: selection mismatch", file=sys.stderr)
        return 2
    selection_X = equal_budget._sample_matrix(selection)
    truth = ThreeChannelFemmTruth(args.campaign)
    selection_truth = truth.evaluate(selection_X)
    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8"))

    pwa_rows = []
    saren_rows = []
    for strategy in strategies:
        for budget in budgets:
            sample_seed = equal_budget._derived_seed(
                seeds["split"], strategy, budget
            )
            train = equal_budget._sample_training(
                strategy, domain, budget, sample_seed
            )
            train_X = equal_budget._sample_matrix(train)
            train_y = truth.evaluate(train_X)
            for space in ("normalized", "physical"):
                model = build_surrogate(
                    "pwa", seeds["model"], {"delaunay_space": space}
                )
                model.fit(train_X, train_y)
                scored = _score_cell(
                    model,
                    selection_X,
                    selection_truth,
                    pole_pairs,
                    anchors,
                    thresholds,
                )
                pwa_rows.append(
                    {
                        "strategy": strategy,
                        "budget": budget,
                        "delaunay_space": space,
                        "n_simplices": model.hyperparameters_.get("n_simplices"),
                        **scored,
                    }
                )
            for family in families:
                config = dict(manifest.get("surrogate_configs", {}).get(family, {}))
                model = build_surrogate(family, seeds["model"], config)
                model.fit(train_X, train_y)
                scored = _score_cell(
                    model,
                    selection_X,
                    selection_truth,
                    pole_pairs,
                    anchors,
                    thresholds,
                )
                saren_rows.append(
                    {
                        "strategy": strategy,
                        "budget": budget,
                        "family": family,
                        **scored,
                    }
                )

    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "not_electromagnetic_truth": False,
        "pwa_construction": "as_described_reimplementation",
        "saren_metric": "stator_mtpa_residual_and_one_step_current_vs_fem_anchors",
        "pwa": pwa_rows,
        "saren": saren_rows,
        "status": "completed",
    }
    (out_root / "pwa_saren_study.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "pwa/saren study: pwa_rows=%d saren_rows=%d out=%s"
        % (len(pwa_rows), len(saren_rows), out_root)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
