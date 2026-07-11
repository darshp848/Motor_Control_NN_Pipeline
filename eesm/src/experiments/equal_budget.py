"""Equal-budget EESM baseline study orchestration."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from sampling.sample_designs import (
    latin_hypercube_samples,
    random_samples,
    tensor_grid_samples,
)
from surrogates.registry import build_surrogate
from synthetic.synthetic_map import MapDomain


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _point_ids_sha256(point_ids: list[str]) -> str:
    payload = "\n".join(sorted(point_ids)).encode("ascii")
    return _sha256_bytes(payload)


def _derived_seed(base_seed: int, *parts: object) -> int:
    payload = ":".join([str(int(base_seed)), *(str(part) for part in parts)])
    return int(hashlib.sha256(payload.encode("ascii")).hexdigest()[:8], 16)


def _require_unique_strings(manifest: Mapping[str, Any], key: str) -> list[str]:
    values = manifest.get(key)
    if not isinstance(values, list) or not values or not all(
        isinstance(value, str) and value for value in values
    ):
        raise ValueError(f"missing {key}")
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate {key}")
    return list(values)


def _validate_manifest(manifest: Mapping[str, Any]) -> tuple[list[str], list[int], list[str], dict[str, int]]:
    sampling = manifest.get("sampling")
    if not isinstance(sampling, Mapping):
        raise ValueError("missing sampling configuration")
    strategies = sampling.get("baseline_strategies")
    if not isinstance(strategies, list) or not strategies:
        raise ValueError("missing baseline strategies")
    strategies = [str(value) for value in strategies]
    if len(strategies) != len(set(strategies)):
        raise ValueError("duplicate baseline strategies")
    supported = {"tensor_grid", "random", "latin_hypercube"}
    unknown = sorted(set(strategies) - supported)
    if unknown:
        raise ValueError(f"unknown baseline strategies: {unknown}")

    raw_budgets = manifest.get("budgets")
    if not isinstance(raw_budgets, list) or not raw_budgets:
        raise ValueError("missing budgets")
    if not all(
        isinstance(value, int) and not isinstance(value, bool) and value > 0
        for value in raw_budgets
    ):
        raise ValueError("budgets must be positive integers")
    budgets = [int(value) for value in raw_budgets]
    if len(budgets) != len(set(budgets)):
        raise ValueError("duplicate budgets")

    families = _require_unique_strings(manifest, "surrogates")
    raw_seeds = manifest.get("seeds")
    required_seeds = ("split", "model", "scheduler_audit")
    if not isinstance(raw_seeds, Mapping) or any(
        key not in raw_seeds
        or not isinstance(raw_seeds[key], int)
        or isinstance(raw_seeds[key], bool)
        for key in required_seeds
    ):
        raise ValueError("unfrozen role seeds")
    seeds = {key: int(raw_seeds[key]) for key in required_seeds}
    return strategies, budgets, families, seeds


def _build_run_matrix(
    manifest: Mapping[str, Any],
) -> list[tuple[str, int, str]]:
    """Return the manifest's ordered, duplicate-free baseline run matrix."""
    strategies, budgets, families, _ = _validate_manifest(manifest)
    matrix = [
        (strategy, budget, family)
        for strategy in strategies
        for budget in budgets
        for family in families
    ]
    if len(matrix) != len(set(matrix)):
        raise ValueError("duplicate run keys")
    return matrix


def _domain_from_manifest(manifest: Mapping[str, Any]) -> MapDomain:
    domains = manifest.get("domains")
    map_domain = domains.get("map") if isinstance(domains, Mapping) else None
    if not isinstance(map_domain, Mapping):
        raise ValueError("missing map domain")

    def bounds(name: str) -> tuple[float, float]:
        values = map_domain.get(name)
        if not isinstance(values, list) or len(values) != 2:
            raise ValueError(f"invalid map domain for {name}")
        low, high = float(values[0]), float(values[1])
        if not math.isfinite(low) or not math.isfinite(high) or low >= high:
            raise ValueError(f"invalid map domain for {name}")
        return low, high

    id_bounds = bounds("id_a")
    iq_bounds = bounds("iq_a")
    if_bounds = bounds("if_a")
    return MapDomain(
        id_min_a=id_bounds[0],
        id_max_a=id_bounds[1],
        iq_min_a=iq_bounds[0],
        iq_max_a=iq_bounds[1],
        if_min_a=if_bounds[0],
        if_max_a=if_bounds[1],
    )


def _tensor_shape(budget: int) -> tuple[int, int, int]:
    candidates: list[tuple[int, int, int]] = []
    for n_id in range(2, budget + 1):
        if budget % n_id:
            continue
        remaining = budget // n_id
        for n_iq in range(2, remaining + 1):
            if remaining % n_iq:
                continue
            n_if = remaining // n_iq
            if n_if >= 2:
                candidates.append((n_id, n_iq, n_if))
    if not candidates:
        raise ValueError(
            f"tensor_grid budget {budget} cannot form a three-axis grid"
        )
    balanced = min(
        candidates,
        key=lambda shape: (
            max(shape) - min(shape),
            -shape[0],
            -shape[1],
            -shape[2],
        ),
    )
    return balanced


def _sample_training(
    strategy: str, domain: MapDomain, budget: int, seed: int
) -> dict[str, np.ndarray]:
    if strategy == "tensor_grid":
        n_id, n_iq, n_if = _tensor_shape(budget)
        return tensor_grid_samples(domain, n_id, n_iq, n_if, seed=seed)
    if strategy == "random":
        return random_samples(domain, n=budget, seed=seed)
    if strategy == "latin_hypercube":
        return latin_hypercube_samples(domain, n=budget, seed=seed)
    raise ValueError(f"unknown baseline strategy: {strategy}")


def _sample_matrix(samples: Mapping[str, np.ndarray]) -> np.ndarray:
    return np.column_stack(
        [samples["id_a"], samples["iq_a"], samples["if_a"]]
    ).astype(np.float64)


def _evaluate_truth(truth_provider: object, X: np.ndarray) -> np.ndarray:
    if hasattr(truth_provider, "flux"):
        lambda_d, lambda_q = truth_provider.flux(X[:, 0], X[:, 1], X[:, 2])
        values = np.column_stack([lambda_d, lambda_q])
    elif hasattr(truth_provider, "evaluate"):
        values = truth_provider.evaluate(X)
    elif callable(truth_provider):
        values = truth_provider(X)
    else:
        raise TypeError("truth_provider must expose flux/evaluate or be callable")
    truth = np.asarray(values, dtype=np.float64)
    if truth.shape != (X.shape[0], 2) or not np.isfinite(truth).all():
        raise ValueError("truth_provider must return finite shape (n, 2)")
    return truth


def _assert_role_disjointness(
    train_ids: list[str], selection_ids: list[str], audit_ids: list[str]
) -> None:
    train = set(train_ids)
    selection = set(selection_ids)
    audit = set(audit_ids)
    if len(train) != len(train_ids):
        raise ValueError("duplicate training point IDs")
    if len(selection) != len(selection_ids) or len(audit) != len(audit_ids):
        raise ValueError("duplicate reserved role point IDs")
    if train & selection or train & audit or selection & audit:
        raise ValueError("point overlap between experiment roles")


def _flux_metrics(truth: np.ndarray, predicted: np.ndarray) -> dict[str, Any]:
    error = predicted - truth
    return {
        "n_selection": int(truth.shape[0]),
        "lambda_d_wb": {
            "mae": float(np.mean(np.abs(error[:, 0]))),
            "rmse": float(np.sqrt(np.mean(error[:, 0] ** 2))),
            "max_abs": float(np.max(np.abs(error[:, 0]))),
        },
        "lambda_q_wb": {
            "mae": float(np.mean(np.abs(error[:, 1]))),
            "rmse": float(np.sqrt(np.mean(error[:, 1] ** 2))),
            "max_abs": float(np.max(np.abs(error[:, 1]))),
        },
        "rmse_flux_mean": float(np.sqrt(np.mean(error**2))),
    }


def _write_predictions(
    path: Path,
    point_ids: list[str],
    X: np.ndarray,
    truth: np.ndarray,
    predicted: np.ndarray,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "point_id",
                "id_a",
                "iq_a",
                "if_a",
                "lambda_d_truth_wb",
                "lambda_q_truth_wb",
                "lambda_d_predicted_wb",
                "lambda_q_predicted_wb",
            ]
        )
        for point_id, currents, actual, estimate in zip(
            point_ids, X, truth, predicted
        ):
            writer.writerow(
                [
                    point_id,
                    *(f"{float(value):.17g}" for value in currents),
                    *(f"{float(value):.17g}" for value in actual),
                    *(f"{float(value):.17g}" for value in estimate),
                ]
            )


def run_equal_budget_study(
    manifest_path: str, output_dir: str, truth_provider: object
) -> dict[str, Any]:
    """Fit every manifest strategy-budget-family combination exactly once."""
    manifest_file = Path(manifest_path).resolve()
    manifest_bytes = manifest_file.read_bytes()
    manifest = json.loads(manifest_bytes)
    strategies, budgets, families, seeds = _validate_manifest(manifest)
    expected_matrix = _build_run_matrix(manifest)
    domain = _domain_from_manifest(manifest)

    output_root = Path(output_dir).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    role_budget = max(budgets)
    selection_seed = _derived_seed(seeds["split"], "selection", role_budget)
    selection_samples = latin_hypercube_samples(
        domain, n=role_budget, seed=selection_seed
    )
    audit_samples = latin_hypercube_samples(
        domain, n=role_budget, seed=seeds["scheduler_audit"]
    )
    selection_ids = [str(value) for value in selection_samples["point_id"]]
    audit_ids = [str(value) for value in audit_samples["point_id"]]
    _assert_role_disjointness([], selection_ids, audit_ids)
    selection_X = _sample_matrix(selection_samples)
    selection_truth = _evaluate_truth(truth_provider, selection_X)

    manifest_hash = _sha256_bytes(manifest_bytes)
    run_summaries: list[dict[str, Any]] = []
    run_keys: set[tuple[str, int, str]] = set()
    surrogate_configs = manifest.get("surrogate_configs", {})
    if not isinstance(surrogate_configs, Mapping):
        raise ValueError("surrogate_configs must be an object")
    family_configs: dict[str, Mapping[str, Any]] = {}
    for family in families:
        config = surrogate_configs.get(family, {})
        if not isinstance(config, Mapping):
            raise ValueError(f"surrogate config for {family} must be an object")
        family_configs[family] = config

    training_designs: dict[
        tuple[str, int], tuple[int, list[str], np.ndarray]
    ] = {}
    for strategy in strategies:
        for budget in budgets:
            sample_seed = _derived_seed(seeds["split"], strategy, budget)
            training_samples = _sample_training(
                strategy, domain, budget, sample_seed
            )
            train_ids = [str(value) for value in training_samples["point_id"]]
            _assert_role_disjointness(train_ids, selection_ids, audit_ids)
            training_designs[(strategy, budget)] = (
                sample_seed,
                train_ids,
                _sample_matrix(training_samples),
            )

    for strategy in strategies:
        for budget in budgets:
            sample_seed, train_ids, train_X = training_designs[
                (strategy, budget)
            ]
            train_y = _evaluate_truth(truth_provider, train_X)

            for family in families:
                run_key = (strategy, budget, family)
                if run_key in run_keys:
                    raise ValueError(f"duplicate run key: {run_key}")
                run_keys.add(run_key)
                run_dir = output_root / "runs" / strategy / str(budget) / family
                run_dir.mkdir(parents=True, exist_ok=True)

                model = build_surrogate(
                    family, seeds["model"], family_configs[family]
                )
                model.fit(train_X, train_y)
                predicted = model.predict(selection_X)
                metrics = _flux_metrics(selection_truth, predicted)

                model_metadata = model.save(str(run_dir / "model"))
                metrics_path = run_dir / "metrics.json"
                predictions_path = run_dir / "predictions.csv"
                model_metadata_path = run_dir / "model_metadata.json"
                run_metadata_path = run_dir / "metadata.json"
                _write_json(metrics_path, metrics)
                _write_predictions(
                    predictions_path,
                    selection_ids,
                    selection_X,
                    selection_truth,
                    predicted,
                )
                _write_json(model_metadata_path, model_metadata)

                artifacts = {
                    "metrics": metrics_path.relative_to(output_root).as_posix(),
                    "model": Path(model_metadata["artifact_path"])
                    .relative_to(output_root)
                    .as_posix(),
                    "model_metadata": model_metadata_path
                    .relative_to(output_root)
                    .as_posix(),
                    "predictions": predictions_path
                    .relative_to(output_root)
                    .as_posix(),
                    "run_metadata": run_metadata_path
                    .relative_to(output_root)
                    .as_posix(),
                }
                run_metadata = {
                    "strategy": strategy,
                    "budget": budget,
                    "family": family,
                    "sample_seed": sample_seed,
                    "model_seed": seeds["model"],
                    "manifest_sha256": manifest_hash,
                    "training_point_ids": train_ids,
                    "training_point_ids_sha256": _point_ids_sha256(train_ids),
                    "selection_point_ids_sha256": _point_ids_sha256(selection_ids),
                    "scheduler_audit_point_ids_sha256": _point_ids_sha256(audit_ids),
                    "training_data_sha256": model_metadata[
                        "training_data_sha256"
                    ],
                    "artifacts": artifacts,
                }
                _write_json(run_metadata_path, run_metadata)
                run_summaries.append(
                    {
                        "strategy": strategy,
                        "budget": budget,
                        "family": family,
                        "status": "completed",
                        "n_train": int(train_X.shape[0]),
                        "sample_seed": sample_seed,
                        "model_seed": seeds["model"],
                        "training_point_ids_sha256": run_metadata[
                            "training_point_ids_sha256"
                        ],
                        "metrics": metrics,
                        "artifacts": artifacts,
                    }
                )

    if (
        len(run_summaries) != len(expected_matrix)
        or run_keys != set(expected_matrix)
    ):
        raise RuntimeError("incomplete equal-budget run matrix")
    summary: dict[str, Any] = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": manifest.get("experiment_id"),
        "manifest_sha256": manifest_hash,
        "strategies": strategies,
        "budgets": budgets,
        "families": families,
        "role_point_ids": {
            "selection": selection_ids,
            "scheduler_audit": audit_ids,
        },
        "runs": run_summaries,
        "status": "completed",
    }
    _write_json(output_root / "equal_budget_summary.json", summary)
    return summary
