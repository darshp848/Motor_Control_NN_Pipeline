"""Rescore the 54-cell matrix under frozen physics gates. No FEMM. No retune."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from experiments import equal_budget
from experiments.energy_seed_study import ThreeChannelFemmTruth, _summarize
from experiments.phase2_strengthen import model_replicate_seeds
from metrics import ldiff
from metrics import reciprocity as recip
from scheduler.copper_loss_scheduler import electromagnetic_torque_eesm
from surrogates.registry import build_surrogate
from validation.physics_threshold_method import PHYSICS_GATES


STOCHASTIC_FAMILIES = ("compact_mlp", "tree_ensemble", "energy_gradient_net")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def physics_gate_values(
    predict, selection_X: np.ndarray, anchors: Mapping[str, Any]
) -> dict[str, float]:
    summary = recip.summarize(recip.reciprocity_residuals(predict, selection_X))
    ldiff_metrics = ldiff.ldiff_error(predict, anchors)
    offdiag = ldiff_metrics["off_diagonal_mean_rel_rmse"]
    if offdiag is None:
        raise ValueError("off-diagonal L_diff unavailable")
    return {
        "R_dq_rms_h": float(summary["R_dq"]["rms_h"]),
        "R_fd_rms_h": float(summary["R_fd"]["rms_h"]),
        "R_fq_rms_h": float(summary["R_fq"]["rms_h"]),
        "ldiff_frobenius_rel": float(ldiff_metrics["frobenius_rel_rmse"]),
        "ldiff_offdiag_rel": float(offdiag),
    }


def evaluate_physics_gates(
    values: Mapping[str, float], thresholds: Mapping[str, float]
) -> dict[str, Any]:
    gates = {}
    for name in PHYSICS_GATES:
        value = float(values[name])
        threshold = float(thresholds[name])
        gates[name] = {
            "value": value,
            "threshold": threshold,
            "pass": value <= threshold,
        }
    return {
        "all_required_pass": all(item["pass"] for item in gates.values()),
        "gates": gates,
    }


def run_physics_gate_study(
    manifest: Mapping[str, Any],
    truth_provider: ThreeChannelFemmTruth,
    selection_ids: Sequence[str],
    selection_X: np.ndarray,
    anchors: Mapping[str, Any],
    output_dir: str | Path,
    n_seeds: int | None = None,
) -> dict[str, Any]:
    strategies, budgets, families, seeds = equal_budget._validate_manifest(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    physics = manifest["physics_gates"]
    if physics.get("status") != "frozen":
        raise ValueError("physics_gates are not frozen")
    thresholds = dict(physics["thresholds"])
    report_seeds = int(
        n_seeds
        if n_seeds is not None
        else manifest.get("determinism", {}).get("report_seeds", 1)
    )
    model_seeds = model_replicate_seeds(seeds["model"], report_seeds)
    selection_truth = truth_provider.evaluate(selection_X)
    truth_torque = electromagnetic_torque_eesm(
        selection_X[:, 0],
        selection_X[:, 1],
        selection_truth[:, 0],
        selection_truth[:, 1],
        pole_pairs,
    )

    runs: list[dict[str, Any]] = []
    for strategy in strategies:
        for budget in budgets:
            sample_seed = equal_budget._derived_seed(
                seeds["split"], strategy, budget
            )
            train_samples = equal_budget._sample_training(
                strategy, domain, budget, sample_seed
            )
            train_ids = [str(value) for value in train_samples["point_id"]]
            equal_budget._assert_role_disjointness(
                train_ids, list(selection_ids), []
            )
            train_X = equal_budget._sample_matrix(train_samples)
            train_y = truth_provider.evaluate(train_X)
            for family in families:
                config = dict(manifest.get("surrogate_configs", {}).get(family, {}))
                seed_list = (
                    model_seeds if family in STOCHASTIC_FAMILIES else [seeds["model"]]
                )
                for model_seed in seed_list:
                    model = build_surrogate(family, model_seed, config)
                    model.fit(train_X, train_y)
                    predicted = model.predict(selection_X)
                    torque_rmse = float(
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
                                    - truth_torque
                                )
                                ** 2
                            )
                        )
                    )
                    gate_values = physics_gate_values(
                        model.predict, selection_X, anchors
                    )
                    gates = evaluate_physics_gates(gate_values, thresholds)
                    runs.append(
                        {
                            "strategy": strategy,
                            "budget": int(budget),
                            "family": family,
                            "sample_seed": int(sample_seed),
                            "model_seed": int(model_seed),
                            "torque_rmse_nm": torque_rmse,
                            "physics_gate_values": gate_values,
                            "physics_gates": gates,
                            "n_train": int(train_X.shape[0]),
                        }
                    )

    cells: dict[str, dict[str, Any]] = {}
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in runs:
        grouped[(row["strategy"], row["budget"], row["family"])].append(row)
    for key, group in grouped.items():
        strategy, budget, family = key
        torque = [row["torque_rmse_nm"] for row in group]
        median_values = {
            gate: float(
                np.median([row["physics_gate_values"][gate] for row in group])
            )
            for gate in PHYSICS_GATES
        }
        median_gates = evaluate_physics_gates(median_values, thresholds)
        cell_id = f"{strategy}|{budget}|{family}"
        cells[cell_id] = {
            "strategy": strategy,
            "budget": budget,
            "family": family,
            "n_seeds": len(group),
            "torque_rmse_nm": _summarize(torque),
            "physics_gate_values_median": median_values,
            "physics_gates": median_gates,
            "n_seeds_all_required_pass": int(
                sum(row["physics_gates"]["all_required_pass"] for row in group)
            ),
        }

    passing = [
        cell
        for cell in cells.values()
        if cell["physics_gates"]["all_required_pass"]
    ]
    passing.sort(key=lambda cell: cell["torque_rmse_nm"]["median"])
    ranking = {
        "policy": "all_physics_gates_then_median_torque_rmse",
        "n_cells": len(cells),
        "n_pass": len(passing),
        "ranked_passers": [
            {
                "candidate_id": f"{cell['strategy']}|{cell['budget']}|{cell['family']}",
                "median_torque_rmse_nm": cell["torque_rmse_nm"]["median"],
            }
            for cell in passing
        ],
        "promotion": {
            "status": "not_attempted",
            "reason": (
                "Physics-gate rescore only. Phase 0/1 promotion is unchanged."
            ),
        },
    }

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": manifest.get("experiment_id"),
        "physics_thresholds": thresholds,
        "contamination_disclosure": physics.get("contamination_disclosure"),
        "model_seeds_stochastic": model_seeds,
        "runs": runs,
        "cells": cells,
        "ranking": ranking,
        "status": "completed",
    }
    _write_json(Path(output_dir) / "physics_gate_study.json", summary)
    return summary
