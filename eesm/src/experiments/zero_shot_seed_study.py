"""Seed-averaged zero-shot lambda_f ablation. Train rows only for the gauge."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from experiments import equal_budget
from experiments.energy_seed_study import ThreeChannelFemmTruth, _summarize, _write_json
from experiments.phase2_strengthen import model_replicate_seeds
from metrics import field_gauge
from scheduler.copper_loss_scheduler import electromagnetic_torque_eesm
from surrogates.registry import build_surrogate


def run_zero_shot_seed_study(
    manifest: Mapping[str, Any],
    truth_provider: ThreeChannelFemmTruth,
    selection_ids: Sequence[str],
    selection_X: np.ndarray,
    output_dir: str | Path,
    n_seeds: int = 8,
) -> dict[str, Any]:
    strategies, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    model_seeds = model_replicate_seeds(seeds["model"], n_seeds)
    config = dict(manifest.get("surrogate_configs", {}).get("energy_gradient_net", {}))
    config["field_supervision"] = False
    config.setdefault("num_threads", 1)

    selection_truth = truth_provider.evaluate(selection_X)
    truth_torque = electromagnetic_torque_eesm(
        selection_X[:, 0],
        selection_X[:, 1],
        selection_truth[:, 0],
        selection_truth[:, 1],
        pole_pairs,
    )
    lambda_f_std = float(selection_truth[:, 2].std())

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
            for model_seed in model_seeds:
                model = build_surrogate("energy_gradient_net", model_seed, config)
                model.fit(train_X, train_y[:, :2])
                pred = model.predict(selection_X)
                torque_rmse = float(
                    np.sqrt(
                        np.mean(
                            (
                                electromagnetic_torque_eesm(
                                    selection_X[:, 0],
                                    selection_X[:, 1],
                                    pred[:, 0],
                                    pred[:, 1],
                                    pole_pairs,
                                )
                                - truth_torque
                            )
                            ** 2
                        )
                    )
                )
                raw_train = model.predict_field(train_X)
                raw_sel = model.predict_field(selection_X)
                gauge = field_gauge.fit_gauge(
                    train_X[:, 2], raw_train, train_y[:, 2]
                )
                corrected = gauge.apply(raw_sel, selection_X[:, 2])
                control = field_gauge.field_only_control(
                    train_X[:, 2], train_y[:, 2], selection_X[:, 2]
                )
                lf_fixed = float(np.sqrt(np.mean((corrected - selection_truth[:, 2]) ** 2)))
                lf_control = float(np.sqrt(np.mean((control - selection_truth[:, 2]) ** 2)))
                runs.append(
                    {
                        "strategy": strategy,
                        "budget": int(budget),
                        "model_seed": int(model_seed),
                        "sample_seed": int(sample_seed),
                        "lambda_f_rmse_gauge_fixed": lf_fixed,
                        "lambda_f_rmse_if_only_control": lf_control,
                        "lambda_f_rmse_uncalibrated": float(
                            np.sqrt(np.mean((raw_sel - selection_truth[:, 2]) ** 2))
                        ),
                        "control_ratio": lf_control / lf_fixed if lf_fixed > 0 else float("nan"),
                        "gauge_r2_oos": field_gauge.gauge_dimensionality_r2(
                            gauge, selection_X[:, 2], raw_sel, selection_truth[:, 2]
                        ),
                        "torque_rmse_nm_unsupervised": torque_rmse,
                        "lambda_f_as_fraction_of_std": lf_fixed / lambda_f_std
                        if lambda_f_std > 0
                        else float("nan"),
                        "gauge": gauge.to_dict(),
                    }
                )

    groups: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in runs:
        key = f"{row['strategy']}|{row['budget']}"
        for metric in (
            "lambda_f_rmse_gauge_fixed",
            "lambda_f_rmse_if_only_control",
            "control_ratio",
            "gauge_r2_oos",
            "torque_rmse_nm_unsupervised",
            "lambda_f_as_fraction_of_std",
        ):
            groups[key][metric].append(row[metric])

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "family": "energy_gradient_net",
        "field_supervision": False,
        "gauge_fitted_on": "train_role_only",
        "selection_used_for_gauge": False,
        "model_seeds": model_seeds,
        "lambda_f_truth_std_wb": lambda_f_std,
        "runs": runs,
        "by_cell": {
            key: {metric: _summarize(values) for metric, values in metrics.items()}
            for key, metrics in sorted(groups.items())
        },
        "status": "completed",
    }
    _write_json(Path(output_dir) / "zero_shot_seed_study.json", summary)
    return summary
