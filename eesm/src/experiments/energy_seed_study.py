"""Seed-averaged energy-gradient study on frozen FEM truth. No FEMM launch."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

import csv

from data.experiment_points import canonical_point_id
from data.femm_truth import ORIGIN_ID
from experiments import equal_budget
from experiments.phase2_strengthen import model_replicate_seeds
from metrics.reciprocity import FIELD_SECTOR_TO_TERMINAL
from scheduler.copper_loss_scheduler import electromagnetic_torque_eesm
from surrogates.registry import build_surrogate


class ThreeChannelFemmTruth:
    """Exact (id, iq, if) -> (λd, λq, λf_terminal) from a FEMM campaign."""

    def __init__(self, results_csv: str | Path):
        self._flux: dict[str, np.ndarray] = {}
        with Path(results_csv).open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                self._flux[row["point_id"]] = np.array(
                    [
                        float(row["lambda_d_wb"]),
                        float(row["lambda_q_wb"]),
                        FIELD_SECTOR_TO_TERMINAL * float(row["lambda_field_wb"]),
                    ],
                    dtype=np.float64,
                )
        if not self._flux:
            raise ValueError("FEMM campaign CSV has no rows")

    def evaluate(self, X: np.ndarray) -> np.ndarray:
        out = np.empty((X.shape[0], 3), dtype=np.float64)
        for index, currents in enumerate(X):
            point_id = canonical_point_id(*map(float, currents))
            if point_id == ORIGIN_ID:
                out[index] = 0.0
                continue
            try:
                out[index] = self._flux[point_id]
            except KeyError as exc:
                raise KeyError(
                    f"no FEMM truth for {point_id} at {tuple(currents)}"
                ) from exc
        return out


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _summarize(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": int(array.size),
        "min": float(np.min(array)),
        "median": float(np.median(array)),
        "max": float(np.max(array)),
        "iqr": float(np.subtract(*np.percentile(array, [75, 25]))),
        "mean": float(np.mean(array)),
        "rel_spread": float(
            (np.max(array) - np.min(array)) / np.median(array)
        )
        if np.median(array) > 0
        else float("nan"),
    }


def run_energy_seed_study(
    manifest: Mapping[str, Any],
    truth_provider: Any,
    selection_ids: Sequence[str],
    selection_X: np.ndarray,
    output_dir: str | Path,
    n_seeds: int = 8,
    family: str = "energy_gradient_net",
) -> dict[str, Any]:
    """Fit one family on the nine frozen designs at several model seeds."""
    strategies, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    model_seeds = model_replicate_seeds(seeds["model"], n_seeds)
    family_config = dict(manifest.get("surrogate_configs", {}).get(family, {}))
    family_config.setdefault("num_threads", 1)

    if not hasattr(truth_provider, "evaluate"):
        raise TypeError("truth_provider must expose evaluate(X) -> (n, 3)")
    selection_truth = np.asarray(truth_provider.evaluate(selection_X), dtype=np.float64)
    if selection_truth.shape != (selection_X.shape[0], 3) or not np.isfinite(
        selection_truth
    ).all():
        raise ValueError("energy seed study requires finite three-output FEM truth")

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
            train_y = np.asarray(truth_provider.evaluate(train_X), dtype=np.float64)
            if train_y.shape != (train_X.shape[0], 3) or not np.isfinite(train_y).all():
                raise ValueError("training truth must be finite shape (n, 3)")
            for model_seed in model_seeds:
                model = build_surrogate(family, model_seed, family_config)
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
                flux_rmse = {
                    "lambda_d_wb": float(
                        np.sqrt(
                            np.mean((predicted[:, 0] - selection_truth[:, 0]) ** 2)
                        )
                    ),
                    "lambda_q_wb": float(
                        np.sqrt(
                            np.mean((predicted[:, 1] - selection_truth[:, 1]) ** 2)
                        )
                    ),
                    "lambda_f_terminal_wb": float(
                        np.sqrt(
                            np.mean((predicted[:, 2] - selection_truth[:, 2]) ** 2)
                        )
                    ),
                }
                runs.append(
                    {
                        "strategy": strategy,
                        "budget": int(budget),
                        "family": family,
                        "sample_seed": int(sample_seed),
                        "model_seed": int(model_seed),
                        "torque_rmse_nm": torque_rmse,
                        "flux_rmse": flux_rmse,
                        "n_train": int(train_X.shape[0]),
                    }
                )

    groups: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in runs:
        key = f"{row['strategy']}|{row['budget']}"
        groups[key]["torque_rmse_nm"].append(row["torque_rmse_nm"])
        groups[key]["lambda_f_rmse_wb"].append(
            row["flux_rmse"]["lambda_f_terminal_wb"]
        )

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": manifest.get("experiment_id"),
        "family": family,
        "model_seeds": model_seeds,
        "n_seeds": len(model_seeds),
        "rank_on": "median_torque_rmse_nm",
        "determinism": manifest.get("determinism", {}),
        "runs": runs,
        "by_cell": {
            key: {metric: _summarize(values) for metric, values in metrics.items()}
            for key, metrics in sorted(groups.items())
        },
        "status": "completed",
    }
    _write_json(Path(output_dir) / "energy_seed_study.json", summary)
    return summary
