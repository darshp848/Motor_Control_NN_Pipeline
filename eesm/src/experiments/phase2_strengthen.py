"""Phase 2 paper-strengthening identities and offline seed replication.

Phase 0 identities, thresholds, and result bundles are read-only inputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np

from data.experiment_points import canonical_point_id
from experiments import equal_budget
from scheduler.copper_loss_scheduler import electromagnetic_torque_eesm
from surrogates.registry import build_surrogate
from synthetic.synthetic_map import MapDomain

FEMM_POINT_FIELDS = (
    "point_name",
    "point_id",
    "role",
    "region",
    "id_a",
    "iq_a",
    "if_a",
)


def is_origin(id_a: float, iq_a: float, if_a: float, atol: float = 1.0e-12) -> bool:
    return (
        abs(float(id_a)) <= atol
        and abs(float(iq_a)) <= atol
        and abs(float(if_a)) <= atol
    )


def classify_region(
    id_a: float,
    iq_a: float,
    if_a: float,
    domain: Mapping[str, tuple[float, float]],
) -> str:
    id_a = float(id_a)
    iq_a = float(iq_a)
    if_a = float(if_a)
    if id_a <= -96.0:
        return "field_weakening"
    if if_a >= 12.0 or (abs(id_a) + iq_a) >= 180.0:
        return "saturation"
    id_bounds = domain["id_a"]
    iq_bounds = domain["iq_a"]
    if_bounds = domain["if_a"]
    on_face = (
        abs(id_a - id_bounds[0]) <= 1.0e-9
        or abs(id_a - id_bounds[1]) <= 1.0e-9
        or abs(iq_a - iq_bounds[0]) <= 1.0e-9
        or abs(iq_a - iq_bounds[1]) <= 1.0e-9
        or abs(if_a - if_bounds[0]) <= 1.0e-9
        or abs(if_a - if_bounds[1]) <= 1.0e-9
    )
    return "boundary" if on_face else "interior"


def render_femm_points(rows: Iterable[Mapping[str, Any]]) -> bytes:
    from io import StringIO

    stream = StringIO(newline="")
    writer = csv.DictWriter(
        stream,
        fieldnames=list(FEMM_POINT_FIELDS),
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "point_name": row["point_name"],
                "point_id": row["point_id"],
                "role": row["role"],
                "region": row["region"],
                "id_a": "%.9f" % float(row["id_a"]),
                "iq_a": "%.9f" % float(row["iq_a"]),
                "if_a": "%.9f" % float(row["if_a"]),
            }
        )
    return stream.getvalue().encode("ascii")


PHASE2_ID = "eesm_phase2_strengthen_20260813"
N_DESIGN_REPLICATES = 5
N_MODEL_SEEDS = 5
N_BOUNDARY = 48
N_WST360 = 40
STOCHASTIC_FAMILIES = ("compact_mlp", "tree_ensemble")
DETERMINISTIC_FAMILIES = ("physics_polynomial", "rbf_or_gp")
REPLICATED_STRATEGIES = ("random", "latin_hypercube")

PHASE2_THRESHOLDS = {
    "data_qa": 0.0,
    "interior": 0.01,
    "boundary": 0.01,
    "saturation": 0.01,
    "field_weakening": 0.01,
    "torque": 1.5915,
    "voltage": 4.618802153517006,
    "feasibility": 0.02,
}

SCHEDULER_RPM = (500.0, 1000.0, 2000.0, 3000.0, 4500.0, 6000.0, 7500.0, 9000.0)
SCHEDULER_TORQUE_NM = (2.0, 5.0, 10.0, 15.0, 20.0, 25.0, 28.0, 31.83)


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _domain_dict(domain: MapDomain) -> dict[str, tuple[float, float]]:
    return {
        "id_a": (float(domain.id_min_a), float(domain.id_max_a)),
        "iq_a": (float(domain.iq_min_a), float(domain.iq_max_a)),
        "if_a": (float(domain.if_min_a), float(domain.if_max_a)),
    }


def phase0_sample_seed(split_seed: int, strategy: str, budget: int) -> int:
    return equal_budget._derived_seed(split_seed, strategy, budget)


def design_replicate_seed(
    split_seed: int, strategy: str, budget: int, replicate: int
) -> int:
    if int(replicate) < 0:
        raise ValueError("replicate must be >= 0")
    if int(replicate) == 0:
        return phase0_sample_seed(split_seed, strategy, budget)
    return equal_budget._derived_seed(
        split_seed, strategy, budget, f"phase2_replicate={int(replicate)}"
    )


def model_replicate_seeds(base_seed: int, n_seeds: int = N_MODEL_SEEDS) -> list[int]:
    if n_seeds < 1:
        raise ValueError("n_seeds must be >= 1")
    seeds = [int(base_seed)]
    for index in range(1, n_seeds):
        seeds.append(
            equal_budget._derived_seed(base_seed, "phase2_model", index)
        )
    if len(set(seeds)) != len(seeds):
        raise ValueError("derived model seeds collided")
    return seeds


def load_campaign_rows(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def campaign_id_set(rows: Sequence[Mapping[str, str]]) -> set[str]:
    return {str(row["point_id"]) for row in rows}


def reserved_role_ids(manifest: Mapping[str, Any]) -> dict[str, list[str]]:
    domain = equal_budget._domain_from_manifest(manifest)
    _, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    role_budget = max(budgets)
    selection = equal_budget.latin_hypercube_samples(
        domain,
        n=role_budget,
        seed=equal_budget._derived_seed(seeds["split"], "selection", role_budget),
    )
    audit = equal_budget.latin_hypercube_samples(
        domain, n=role_budget, seed=seeds["scheduler_audit"]
    )
    return {
        "selection": [str(value) for value in selection["point_id"]],
        "scheduler_audit": [str(value) for value in audit["point_id"]],
    }


def build_design_replicates(
    manifest: Mapping[str, Any],
    n_replicates: int = N_DESIGN_REPLICATES,
    existing_ids: set[str] | None = None,
) -> dict[str, Any]:
    strategies, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    domain_obj = equal_budget._domain_from_manifest(manifest)
    domain = _domain_dict(domain_obj)
    reserved = reserved_role_ids(manifest)
    reserved_ids = set(reserved["selection"]) | set(reserved["scheduler_audit"])
    known = set(existing_ids or ())
    designs: dict[str, Any] = {}
    new_rows: list[dict[str, Any]] = []
    seen_new: set[str] = set()
    reuse = 0
    blocked = 0

    for strategy in strategies:
        max_replicate = n_replicates if strategy in REPLICATED_STRATEGIES else 0
        for budget in budgets:
            for replicate in range(max_replicate + 1):
                seed = design_replicate_seed(
                    seeds["split"], strategy, budget, replicate
                )
                samples = equal_budget._sample_training(
                    strategy, domain_obj, budget, seed
                )
                point_ids = [str(value) for value in samples["point_id"]]
                overlap = set(point_ids) & reserved_ids
                if overlap:
                    raise ValueError(
                        f"{strategy}|{budget}|r{replicate} overlaps reserved roles"
                    )
                n_reuse = 0
                n_new = 0
                for index, point_id in enumerate(point_ids):
                    id_a = float(samples["id_a"][index])
                    iq_a = float(samples["iq_a"][index])
                    if_a = float(samples["if_a"][index])
                    if is_origin(id_a, iq_a, if_a):
                        continue
                    if point_id in known:
                        n_reuse += 1
                        continue
                    n_new += 1
                    if point_id in seen_new:
                        continue
                    seen_new.add(point_id)
                    new_rows.append(
                        {
                            "point_name": point_id,
                            "point_id": point_id,
                            "role": "train",
                            "region": classify_region(id_a, iq_a, if_a, domain),
                            "id_a": id_a,
                            "iq_a": iq_a,
                            "if_a": if_a,
                            "strategy": strategy,
                            "budget": budget,
                            "replicate": replicate,
                            "seed": seed,
                        }
                    )
                key = f"{strategy}|{budget}|r{replicate}"
                designs[key] = {
                    "strategy": strategy,
                    "budget": budget,
                    "replicate": replicate,
                    "seed": seed,
                    "n": len(point_ids),
                    "n_already_solved": n_reuse,
                    "n_new_solvable": n_new,
                    "point_ids_sha256": _sha256_bytes(
                        "\n".join(point_ids).encode("ascii")
                    ),
                }
                reuse += n_reuse
                blocked += n_new

    new_rows.sort(key=lambda row: row["point_id"])
    return {
        "designs": designs,
        "reserved": reserved,
        "new_femm_rows": new_rows,
        "n_new_unique_femm": len(new_rows),
        "n_reuse_slots": reuse,
        "n_new_slots": blocked,
        "domain": domain,
        "seeds": dict(seeds),
    }


def build_boundary_set(
    domain: MapDomain,
    reserved_ids: set[str],
    n_points: int = N_BOUNDARY,
) -> list[dict[str, Any]]:
    bounds = _domain_dict(domain)
    id_face = np.linspace(-90.0, 0.0, 8)
    iq_face = np.linspace(0.0, 110.0, 8)
    if_face = np.linspace(0.0, 11.0, 6)
    candidates: list[tuple[float, float, float]] = []
    for iq_a in iq_face:
        for if_a in if_face:
            candidates.append((0.0, float(iq_a), float(if_a)))
    for id_a in id_face:
        for if_a in if_face:
            candidates.append((float(id_a), 0.0, float(if_a)))
    for id_a in id_face:
        for iq_a in iq_face:
            candidates.append((float(id_a), float(iq_a), 0.0))
    for id_a in np.linspace(-50.0, 0.0, 5):
        for if_a in np.linspace(0.0, 10.0, 4):
            candidates.append((float(id_a), 120.0, float(if_a)))

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for id_a, iq_a, if_a in candidates:
        if not domain.contains(id_a, iq_a, if_a):
            continue
        region = classify_region(id_a, iq_a, if_a, bounds)
        if region != "boundary":
            continue
        point_id = canonical_point_id(id_a, iq_a, if_a)
        if point_id in reserved_ids or point_id in seen or is_origin(id_a, iq_a, if_a):
            continue
        seen.add(point_id)
        rows.append(
            {
                "point_name": point_id,
                "point_id": point_id,
                "role": "reference",
                "region": "boundary",
                "id_a": float(id_a),
                "iq_a": float(iq_a),
                "if_a": float(if_a),
            }
        )
    rows.sort(key=lambda row: row["point_id"])
    if len(rows) < n_points:
        raise ValueError(
            f"boundary generator produced {len(rows)} points, need {n_points}"
        )
    return rows[:n_points]


def build_wst360_set(
    campaign_rows: Sequence[Mapping[str, str]],
    n_points: int = N_WST360,
) -> list[dict[str, Any]]:
    by_region: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in campaign_rows:
        by_region[str(row["region"])].append(row)
    for rows in by_region.values():
        rows.sort(key=lambda row: str(row["point_id"]))

    targets = {
        "interior": 12,
        "field_weakening": 10,
        "saturation": 10,
        "boundary": 8,
    }
    chosen: list[Mapping[str, str]] = []
    seen: set[str] = set()

    def take(region: str, count: int) -> None:
        pool = [row for row in by_region.get(region, []) if row["point_id"] not in seen]
        if not pool or count <= 0:
            return
        if len(pool) <= count:
            picked = pool
        else:
            stride = max(len(pool) / count, 1.0)
            picked = [pool[int(index * stride)] for index in range(count)]
        for row in picked:
            if row["point_id"] in seen:
                continue
            seen.add(row["point_id"])
            chosen.append(row)

    for region, count in targets.items():
        take(region, count)
    leftover = n_points - len(chosen)
    if leftover > 0:
        take("interior", leftover)

    if len(chosen) < n_points:
        extras = [
            row
            for row in campaign_rows
            if row["point_id"] not in seen
        ]
        extras.sort(key=lambda row: str(row["point_id"]))
        for row in extras:
            chosen.append(row)
            seen.add(row["point_id"])
            if len(chosen) >= n_points:
                break
    if len(chosen) < n_points:
        raise ValueError("campaign does not contain enough points for the 360 set")

    out: list[dict[str, Any]] = []
    for row in chosen[:n_points]:
        out.append(
            {
                "point_name": row["point_id"],
                "point_id": row["point_id"],
                "role": "reference",
                "region": row["region"],
                "id_a": float(row["id_a"]),
                "iq_a": float(row["iq_a"]),
                "if_a": float(row["if_a"]),
                "source_90deg_campaign": True,
            }
        )
    return out


def build_scheduler_commands(
    rpm_values: Sequence[float] = SCHEDULER_RPM,
    torque_values: Sequence[float] = SCHEDULER_TORQUE_NM,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for rpm in rpm_values:
        for torque in torque_values:
            if float(rpm) <= 2000.0 and float(torque) >= 20.0:
                regime = "high_torque"
            elif float(rpm) >= 6000.0 and float(torque) <= 10.0:
                regime = "field_weakening"
            elif float(rpm) >= 6000.0 and float(torque) >= 20.0:
                regime = "voltage_boundary"
            elif float(torque) >= 28.0:
                regime = "near_rated"
            else:
                regime = "mtpa_like"
            commands.append(
                {
                    "command_id": f"rpm{int(rpm)}_T{torque:.2f}".replace(".", "p"),
                    "rpm_mech": float(rpm),
                    "torque_nm": float(torque),
                    "regime": regime,
                }
            )
    ids = [row["command_id"] for row in commands]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scheduler command ids")
    if len(commands) != 64:
        raise ValueError(f"expected 64 scheduler commands, got {len(commands)}")
    return commands


def identity_torque_rmse(
    id_a: np.ndarray,
    iq_a: np.ndarray,
    truth: np.ndarray,
    predicted: np.ndarray,
    pole_pairs: int,
) -> float:
    truth_t = electromagnetic_torque_eesm(
        id_a, iq_a, truth[:, 0], truth[:, 1], pole_pairs
    )
    pred_t = electromagnetic_torque_eesm(
        id_a, iq_a, predicted[:, 0], predicted[:, 1], pole_pairs
    )
    return float(np.sqrt(np.mean((pred_t - truth_t) ** 2)))


def flux_rmse_mean(truth: np.ndarray, predicted: np.ndarray) -> float:
    err_d = np.sqrt(np.mean((predicted[:, 0] - truth[:, 0]) ** 2))
    err_q = np.sqrt(np.mean((predicted[:, 1] - truth[:, 1]) ** 2))
    return float((err_d + err_q) / 2.0)


class FittedSurrogateMap:
    """Adapt a fitted FluxSurrogate to the copper-loss scheduler map API."""

    def __init__(self, model: Any, domain: MapDomain):
        self.model = model
        self.domain = domain

    def flux(self, id_, iq, if_):
        id_a = np.asarray(id_, dtype=np.float64).ravel()
        iq_a = np.asarray(iq, dtype=np.float64).ravel()
        if_a = np.asarray(if_, dtype=np.float64).ravel()
        predicted = self.model.predict(np.column_stack([id_a, iq_a, if_a]))
        return predicted[:, 0], predicted[:, 1]

    def is_in_domain(self, id_, iq, if_):
        return self.domain.contains(id_, iq, if_)


def _summarize_group(values: Sequence[float]) -> dict[str, float]:
    array = np.asarray(values, dtype=np.float64)
    return {
        "n": int(array.size),
        "min": float(np.min(array)),
        "median": float(np.median(array)),
        "max": float(np.max(array)),
        "iqr": float(np.subtract(*np.percentile(array, [75, 25]))),
        "mean": float(np.mean(array)),
    }


def run_seed_replication(
    manifest: Mapping[str, Any],
    truth_provider: Any,
    selection_ids: Sequence[str],
    selection_X: np.ndarray,
    output_dir: str | Path,
    families: Sequence[str] = STOCHASTIC_FAMILIES,
    n_model_seeds: int = N_MODEL_SEEDS,
    include_deterministic: bool = True,
) -> dict[str, Any]:
    _, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    strategies = list(manifest["sampling"]["baseline_strategies"])
    domain = equal_budget._domain_from_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    family_configs = manifest.get("surrogate_configs", {})
    if not isinstance(family_configs, Mapping):
        raise ValueError("surrogate_configs must be an object")
    model_seeds = model_replicate_seeds(seeds["model"], n_model_seeds)
    selection_truth = equal_budget._evaluate_truth(truth_provider, selection_X)
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    run_rows: list[dict[str, Any]] = []
    planned_families = list(families)
    if include_deterministic:
        for family in DETERMINISTIC_FAMILIES:
            if family not in planned_families:
                planned_families.append(family)

    for strategy in strategies:
        for budget in budgets:
            train_seed = phase0_sample_seed(seeds["split"], strategy, budget)
            train_samples = equal_budget._sample_training(
                strategy, domain, budget, train_seed
            )
            train_ids = [str(value) for value in train_samples["point_id"]]
            equal_budget._assert_role_disjointness(
                train_ids, list(selection_ids), []
            )
            train_X = equal_budget._sample_matrix(train_samples)
            train_y = equal_budget._evaluate_truth(truth_provider, train_X)
            for family in planned_families:
                seed_list = (
                    model_seeds
                    if family in STOCHASTIC_FAMILIES
                    else [seeds["model"]]
                )
                config = family_configs.get(family, {})
                if not isinstance(config, Mapping):
                    raise ValueError(f"surrogate config for {family} must be an object")
                for model_seed in seed_list:
                    model = build_surrogate(family, model_seed, config)
                    model.fit(train_X, train_y)
                    predicted = model.predict(selection_X)
                    torque = identity_torque_rmse(
                        selection_X[:, 0],
                        selection_X[:, 1],
                        selection_truth,
                        predicted,
                        pole_pairs,
                    )
                    flux = flux_rmse_mean(selection_truth, predicted)
                    run_rows.append(
                        {
                            "strategy": strategy,
                            "budget": int(budget),
                            "family": family,
                            "design_replicate": 0,
                            "sample_seed": int(train_seed),
                            "model_seed": int(model_seed),
                            "torque_rmse_nm": torque,
                            "flux_rmse_wb": flux,
                            "n_train": int(train_X.shape[0]),
                            "clears_phase0_torque": torque < 9.65519376554659,
                            "clears_phase2_torque": torque
                            < PHASE2_THRESHOLDS["torque"],
                        }
                    )

    groups: dict[str, list[float]] = defaultdict(list)
    for row in run_rows:
        if row["family"] not in STOCHASTIC_FAMILIES:
            continue
        key = f"{row['strategy']}|{row['budget']}|{row['family']}"
        groups[key].append(row["torque_rmse_nm"])
    group_summary = {
        key: _summarize_group(values) for key, values in sorted(groups.items())
    }

    win_counts: dict[str, dict[str, int]] = {}
    for budget in budgets:
        names = [f"{strategy}|{family}" for strategy in strategies for family in planned_families]
        counts = {name: 0 for name in names}
        # One comparison per (strategy design, model seed). Deterministic
        # families are repeated across seeds so each seed has a complete
        # 12-cell ranking on the same design.
        for strategy in strategies:
            seed_values = model_seeds
            for model_seed in seed_values:
                cell_errors: dict[str, float] = {}
                for family in planned_families:
                    matches = [
                        row
                        for row in run_rows
                        if row["strategy"] == strategy
                        and row["budget"] == budget
                        and row["family"] == family
                        and (
                            row["family"] not in STOCHASTIC_FAMILIES
                            or row["model_seed"] == model_seed
                        )
                    ]
                    if not matches:
                        continue
                    cell_errors[f"{strategy}|{family}"] = min(
                        row["torque_rmse_nm"] for row in matches
                    )
                if not cell_errors:
                    continue
                winner = min(cell_errors, key=cell_errors.get)
                counts[winner] += 1
        win_counts[str(budget)] = counts

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": PHASE2_ID,
        "selection_n": int(selection_X.shape[0]),
        "selection_point_ids_sha256": _sha256_bytes(
            "\n".join(selection_ids).encode("ascii")
        ),
        "model_seeds": model_seeds,
        "phase2_thresholds": PHASE2_THRESHOLDS,
        "runs": run_rows,
        "stochastic_group_summary": group_summary,
        "win_counts_by_budget": win_counts,
        "status": "completed",
    }
    _write_json(output_root / "seed_replication.json", summary)
    return summary


def run_existing_map_schedules(
    study_dir: str | Path,
    manifest: Mapping[str, Any],
    output_dir: str | Path,
    n_grid: int = 21,
    n_random_refine: int = 150,
) -> dict[str, Any]:
    """Re-optimize frozen (rpm, T) commands on each Phase 0 candidate map."""
    from scheduler.copper_loss_scheduler import CopperLossScheduler, SchedulerLimits
    from surrogates.registry import load_surrogate

    study_root = Path(study_dir)
    summary = json.loads(
        (study_root / "equal_budget_summary.json").read_text(encoding="utf-8")
    )
    commands = build_scheduler_commands()
    domain = equal_budget._domain_from_manifest(manifest)
    machine = manifest["machine"]
    limits = SchedulerLimits(
        rs_ohm=float(machine["rs_ohm"]),
        rf_ohm=float(machine["rf_ohm"]),
        vdc_v=float(machine["vdc_v"]),
        i_s_max_peak_a=float(machine["i_s_max_peak_a"]),
        i_f_min_a=float(machine["i_f_min_a"]),
        i_f_max_a=float(machine["i_f_max_a"]),
        pole_pairs=int(machine["pole_pairs"]),
        torque_tolerance_nm=0.5,
    )
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    candidate_rows: list[dict[str, Any]] = []
    unique_currents: dict[str, dict[str, float]] = {}
    for run in summary["runs"]:
        meta_path = study_root / run["artifacts"]["model_metadata"]
        model = load_surrogate(json.loads(meta_path.read_text(encoding="utf-8")))
        flux_map = FittedSurrogateMap(model, domain)
        scheduler = CopperLossScheduler(
            flux_map,
            limits=limits,
            n_grid_id=n_grid,
            n_grid_iq=n_grid,
            n_grid_if=max(8, n_grid // 2),
            n_random_refine=n_random_refine,
            seed=int(manifest["seeds"]["model"]),
        )
        for command in commands:
            result = scheduler.schedule(command["rpm_mech"], command["torque_nm"])
            payload = result.to_dict()
            payload.update(
                {
                    "candidate_id": "%s|%s|%s"
                    % (run["strategy"], run["budget"], run["family"]),
                    "strategy": run["strategy"],
                    "budget": run["budget"],
                    "family": run["family"],
                    "command_id": command["command_id"],
                    "regime": command["regime"],
                }
            )
            candidate_rows.append(payload)
            if (
                result.id_ref_a is not None
                and result.iq_ref_a is not None
                and result.if_ref_a is not None
            ):
                point_id = canonical_point_id(
                    result.id_ref_a, result.iq_ref_a, result.if_ref_a
                )
                unique_currents[point_id] = {
                    "point_id": point_id,
                    "id_a": float(result.id_ref_a),
                    "iq_a": float(result.iq_ref_a),
                    "if_a": float(result.if_ref_a),
                }

    current_rows = [
        {
            "point_name": row["point_id"],
            "point_id": row["point_id"],
            "role": "reference",
            "region": classify_region(
                row["id_a"],
                row["iq_a"],
                row["if_a"],
                _domain_dict(domain),
            ),
            "id_a": row["id_a"],
            "iq_a": row["iq_a"],
            "if_a": row["if_a"],
        }
        for row in unique_currents.values()
    ]
    current_rows.sort(key=lambda row: row["point_id"])
    current_bytes = render_femm_points(current_rows)
    (output_root / "scheduler_selected_currents.csv").write_bytes(current_bytes)

    feasible = [
        row
        for row in candidate_rows
        if row["status"] in {"feasible", "saturated_to_boundary"}
    ]
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": PHASE2_ID,
        "n_candidates": len(summary["runs"]),
        "n_commands": len(commands),
        "n_schedules": len(candidate_rows),
        "n_feasible_or_boundary": len(feasible),
        "n_unique_selected_currents": len(current_rows),
        "selected_currents_sha256": _sha256_bytes(current_bytes),
        "schedules": candidate_rows,
        "status": "completed",
    }
    _write_json(output_root / "scheduler_commands_offline.json", payload)
    return payload


def merge_campaign_csvs(
    sources: Sequence[str | Path], dest: str | Path
) -> dict[str, Any]:
    """Concatenate finished FEMM result CSVs. Duplicate IDs must match."""
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    by_id: dict[str, dict[str, str]] = {}
    fieldnames: list[str] | None = None
    collisions = 0
    for source in sources:
        with Path(source).open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            if reader.fieldnames is None:
                raise ValueError(f"empty campaign CSV: {source}")
            if fieldnames is None:
                fieldnames = list(reader.fieldnames)
            for row in reader:
                point_id = row["point_id"]
                if point_id in by_id:
                    old = by_id[point_id]
                    if (
                        old.get("lambda_d_wb") != row.get("lambda_d_wb")
                        or old.get("lambda_q_wb") != row.get("lambda_q_wb")
                    ):
                        raise ValueError(
                            "conflicting FEMM truth for %s" % point_id
                        )
                    collisions += 1
                    continue
                by_id[point_id] = row
    if fieldnames is None:
        raise ValueError("no campaign rows to merge")
    with dest_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for point_id in sorted(by_id):
            writer.writerow(by_id[point_id])
    return {
        "n_unique": len(by_id),
        "n_identical_collisions": collisions,
        "sources": [str(Path(path)) for path in sources],
        "dest": str(dest_path),
    }


def load_equal_tuning_configs(study_path: str | Path) -> dict[str, dict[str, Any]]:
    """Map 'strategy|budget|family' to the equal-tuning selected_config."""
    payload = json.loads(Path(study_path).read_text(encoding="utf-8"))
    configs: dict[str, dict[str, Any]] = {}
    for row in payload.get("results", []):
        key = "%s|%s|%s" % (row["strategy"], int(row["budget"]), row["family"])
        configs[key] = dict(row.get("selected_config") or {})
    if not configs:
        raise ValueError("equal-tuning study has no selected configs")
    return configs


def run_design_replicate_fit(
    manifest: Mapping[str, Any],
    truth_provider: Any,
    selection_ids: Sequence[str],
    selection_X: np.ndarray,
    output_dir: str | Path,
    equal_tuning_configs: Mapping[str, Mapping[str, Any]],
    families: Sequence[str] | None = None,
    n_replicates: int = N_DESIGN_REPLICATES,
    model_seed: int | None = None,
) -> dict[str, Any]:
    """Fit every Phase 2 design replicate with frozen equal-tuning configs.

    Model-seed variance was already measured on replicate 0. This study
    isolates design-replicate variance. Tensor grids have only replicate 0.
    """
    output_root = Path(output_dir).resolve()
    bundle_path = output_root / "result_bundle.json"
    if bundle_path.is_file():
        raise RuntimeError(
            "REFUSED: %s already exists; choose a new dated root" % bundle_path
        )
    output_root.mkdir(parents=True, exist_ok=True)

    strategies, budgets, default_families, seeds = equal_budget._validate_manifest(
        manifest
    )
    planned = list(families) if families is not None else list(default_families)
    domain = equal_budget._domain_from_manifest(manifest)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    fit_seed = int(seeds["model"] if model_seed is None else model_seed)
    selection_truth = equal_budget._evaluate_truth(truth_provider, selection_X)
    reserved = reserved_role_ids(manifest)

    run_rows: list[dict[str, Any]] = []
    for strategy in strategies:
        max_rep = n_replicates if strategy in REPLICATED_STRATEGIES else 0
        for budget in budgets:
            for replicate in range(max_rep + 1):
                train_seed = design_replicate_seed(
                    seeds["split"], strategy, int(budget), replicate
                )
                train_samples = equal_budget._sample_training(
                    strategy, domain, int(budget), train_seed
                )
                train_ids = [str(value) for value in train_samples["point_id"]]
                equal_budget._assert_role_disjointness(
                    train_ids, list(selection_ids), reserved["scheduler_audit"]
                )
                train_X = equal_budget._sample_matrix(train_samples)
                train_y = equal_budget._evaluate_truth(truth_provider, train_X)
                for family in planned:
                    cfg_key = "%s|%s|%s" % (strategy, int(budget), family)
                    if cfg_key not in equal_tuning_configs:
                        raise KeyError(
                            "no equal-tuning config for %s" % cfg_key
                        )
                    config = dict(equal_tuning_configs[cfg_key])
                    model = build_surrogate(family, fit_seed, config)
                    model.fit(train_X, train_y)
                    predicted = model.predict(selection_X)
                    torque = identity_torque_rmse(
                        selection_X[:, 0],
                        selection_X[:, 1],
                        selection_truth,
                        predicted,
                        pole_pairs,
                    )
                    flux = flux_rmse_mean(selection_truth, predicted)
                    run_dir = (
                        output_root
                        / "runs"
                        / strategy
                        / str(int(budget))
                        / family
                        / ("r%d" % replicate)
                    )
                    run_dir.mkdir(parents=True, exist_ok=True)
                    model_metadata = model.save(str(run_dir / "model"))
                    model_metadata_path = run_dir / "model_metadata.json"
                    _write_json(model_metadata_path, model_metadata)
                    artifacts = {
                        "model": Path(model_metadata["artifact_path"])
                        .resolve()
                        .relative_to(output_root)
                        .as_posix(),
                        "model_metadata": model_metadata_path.resolve().relative_to(
                            output_root
                        ).as_posix(),
                    }
                    run_rows.append(
                        {
                            "strategy": strategy,
                            "budget": int(budget),
                            "family": family,
                            "design_replicate": int(replicate),
                            "sample_seed": int(train_seed),
                            "model_seed": fit_seed,
                            "selected_config": config,
                            "torque_rmse_nm": torque,
                            "flux_rmse_wb": flux,
                            "n_train": int(train_X.shape[0]),
                            "clears_phase0_torque": torque < 9.65519376554659,
                            "clears_phase2_torque": torque
                            < PHASE2_THRESHOLDS["torque"],
                            "artifacts": artifacts,
                        }
                    )
                    print(
                        "fit %d %s|r%d torque=%.4f nm flux=%.5f Wb"
                        % (
                            len(run_rows),
                            cfg_key,
                            replicate,
                            torque,
                            flux,
                        ),
                        flush=True,
                    )

    groups: dict[str, list[float]] = defaultdict(list)
    for row in run_rows:
        key = "%s|%s|%s" % (row["strategy"], row["budget"], row["family"])
        groups[key].append(row["torque_rmse_nm"])
    group_summary = {
        key: _summarize_group(values) for key, values in sorted(groups.items())
    }

    sampler_wins: dict[str, dict[str, int]] = {}
    for budget in budgets:
        counts = {strategy: 0 for strategy in strategies}
        families_here = planned
        n_compare = 0
        for family in families_here:
            # Compare strategies on each shared replicate index. Tensor only
            # has r0, so r0 is the only all-strategy comparison; r1..r5
            # compare random vs latin_hypercube.
            max_shared = max(
                (
                    row["design_replicate"]
                    for row in run_rows
                    if row["budget"] == int(budget) and row["family"] == family
                ),
                default=-1,
            )
            for replicate in range(max_shared + 1):
                cell = {
                    row["strategy"]: row["torque_rmse_nm"]
                    for row in run_rows
                    if row["budget"] == int(budget)
                    and row["family"] == family
                    and row["design_replicate"] == replicate
                }
                if len(cell) < 2:
                    continue
                winner = min(cell, key=cell.get)
                counts[winner] += 1
                n_compare += 1
        sampler_wins[str(int(budget))] = {"n_comparisons": n_compare, **counts}

    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "eesm_phase2_design_replicate_fit_20260814",
        "not_a_phase0_revision": True,
        "protocol": (
            "Fit every frozen Phase 2 design replicate with the equal-tuning "
            "selected_config for that strategy|budget|family. Score on the "
            "sealed Phase 0 selection set. One model seed (1701). Does not "
            "promote."
        ),
        "selection_n": int(selection_X.shape[0]),
        "selection_point_ids_sha256": _sha256_bytes(
            "\n".join(selection_ids).encode("ascii")
        ),
        "model_seed": fit_seed,
        "n_replicates_additional": int(n_replicates),
        "families": list(planned),
        "phase2_thresholds": PHASE2_THRESHOLDS,
        "runs": run_rows,
        "group_summary": group_summary,
        "sampler_wins_by_budget": sampler_wins,
        "status": "completed",
    }
    _write_json(output_root / "design_replicate_fit.json", summary)
    return summary


def write_no_promotion_bundle(
    output_dir: str | Path,
    summary: Mapping[str, Any],
    manifest: Mapping[str, Any],
    foundry_commit: str,
    manifest_sha256: str,
    extra_artifacts: Sequence[Mapping[str, str]] | None = None,
    working_tree_may_be_dirty: bool = True,
) -> Path:
    """Write a schema-valid bundle. status is no_promotion, never not_attempted."""
    output_root = Path(output_dir)
    study_path = output_root / "design_replicate_fit.json"
    artifacts = [
        {
            "path": "design_replicate_fit.json",
            "sha256": _sha256_bytes(study_path.read_bytes()),
        }
    ]
    if extra_artifacts:
        artifacts.extend(list(extra_artifacts))
    bundle = {
        "bundle_version": "1.0.0",
        "experiment_id": summary["experiment_id"],
        "foundry_commit": foundry_commit,
        "manifest_sha256": manifest_sha256,
        "created_utc": summary["created_utc"],
        "inputs": {
            "study": "design_replicate_fit.json",
        },
        "environment": {
            "working_tree_may_be_dirty": bool(working_tree_may_be_dirty),
        },
        "stages": {"design_replicate_fit": summary["status"]},
        "decisions": {
            "promotion": {
                "status": "no_promotion",
                "candidate": None,
                "reason": "design-replicate comparison; Phase 0 stays frozen",
            }
        },
        "artifacts": artifacts,
        "gates": {
            "threshold_status": "frozen",
            "thresholds": manifest["gates"]["thresholds"],
        },
    }
    path = output_root / "result_bundle.json"
    _write_json(path, bundle)
    return path


def campaign_arrays(
    path: str | Path,
) -> dict[str, Any]:
    """Load finished FEMM rows as arrays. Incomplete campaigns are allowed."""
    rows = load_campaign_rows(path)
    usable: list[dict[str, str]] = []
    for row in rows:
        try:
            lambda_d = float(row["lambda_d_wb"])
            lambda_q = float(row["lambda_q_wb"])
        except (KeyError, TypeError, ValueError):
            continue
        if not np.isfinite(lambda_d) or not np.isfinite(lambda_q):
            continue
        if str(row.get("converged", "True")).lower() in {"false", "0"}:
            continue
        usable.append(row)
    if not usable:
        return {
            "path": str(Path(path)),
            "n_rows": len(rows),
            "n_usable": 0,
            "point_ids": [],
            "X": np.zeros((0, 3), dtype=np.float64),
            "y": np.zeros((0, 2), dtype=np.float64),
            "regions": [],
        }
    return {
        "path": str(Path(path)),
        "n_rows": len(rows),
        "n_usable": len(usable),
        "point_ids": [row["point_id"] for row in usable],
        "X": np.asarray(
            [[float(row["id_a"]), float(row["iq_a"]), float(row["if_a"])] for row in usable],
            dtype=np.float64,
        ),
        "y": np.asarray(
            [[float(row["lambda_d_wb"]), float(row["lambda_q_wb"])] for row in usable],
            dtype=np.float64,
        ),
        "regions": [str(row.get("region") or "unknown") for row in usable],
    }


def score_model_on_arrays(
    model: Any,
    X: np.ndarray,
    y: np.ndarray,
    regions: Sequence[str],
    pole_pairs: int,
) -> dict[str, Any]:
    if X.shape[0] == 0:
        return {"n": 0, "torque_rmse_nm": None, "flux_rmse_wb": None, "by_region": {}}
    predicted = model.predict(X)
    by_region: dict[str, dict[str, Any]] = {}
    for region in sorted(set(regions)):
        mask = np.asarray([name == region for name in regions], dtype=bool)
        by_region[region] = {
            "n": int(mask.sum()),
            "torque_rmse_nm": identity_torque_rmse(
                X[mask, 0], X[mask, 1], y[mask], predicted[mask], pole_pairs
            ),
            "flux_rmse_wb": flux_rmse_mean(y[mask], predicted[mask]),
        }
    return {
        "n": int(X.shape[0]),
        "torque_rmse_nm": identity_torque_rmse(
            X[:, 0], X[:, 1], y, predicted, pole_pairs
        ),
        "flux_rmse_wb": flux_rmse_mean(y, predicted),
        "by_region": by_region,
    }


def recommend_cell(summary: Mapping[str, Any], budget: int = 256) -> str:
    """Lowest-median torque cell at the given budget. Ties break on IQR then name."""
    best_key = ""
    best = (float("inf"), float("inf"), "")
    for key, stats in summary.get("group_summary", {}).items():
        parts = str(key).split("|")
        if len(parts) != 3 or int(parts[1]) != int(budget):
            continue
        candidate = (float(stats["median"]), float(stats["iqr"]), str(key))
        if candidate < best:
            best = candidate
            best_key = str(key)
    if not best_key:
        raise ValueError("no group_summary rows for budget %s" % budget)
    return best_key


def select_control_test_runs(
    summary: Mapping[str, Any], budget: int = 256
) -> list[dict[str, Any]]:
    """r0 maps at `budget` plus extra replicates of the recommended family."""
    recommended = recommend_cell(summary, budget=budget)
    rec_strategy, rec_budget, rec_family = recommended.split("|")
    chosen: list[dict[str, Any]] = []
    for row in summary.get("runs", []):
        if int(row["budget"]) != int(budget):
            continue
        extra_of_winner = (
            row["strategy"] == rec_strategy
            and row["family"] == rec_family
            and int(row["design_replicate"]) > 0
        )
        if int(row["design_replicate"]) == 0 or extra_of_winner:
            chosen.append(row)
    return chosen


def run_fitted_map_schedules(
    fit_root: str | Path,
    manifest: Mapping[str, Any],
    output_dir: str | Path,
    runs: Sequence[Mapping[str, Any]],
    n_grid: int = 21,
    n_random_refine: int = 150,
) -> dict[str, Any]:
    """Schedule the frozen 64 (rpm, T) commands on selected fitted maps."""
    from scheduler.copper_loss_scheduler import CopperLossScheduler, SchedulerLimits
    from surrogates.registry import load_surrogate

    study_root = Path(fit_root)
    commands = build_scheduler_commands()
    domain = equal_budget._domain_from_manifest(manifest)
    machine = manifest["machine"]
    limits = SchedulerLimits(
        rs_ohm=float(machine["rs_ohm"]),
        rf_ohm=float(machine["rf_ohm"]),
        vdc_v=float(machine["vdc_v"]),
        i_s_max_peak_a=float(machine["i_s_max_peak_a"]),
        i_f_min_a=float(machine["i_f_min_a"]),
        i_f_max_a=float(machine["i_f_max_a"]),
        pole_pairs=int(machine["pole_pairs"]),
        torque_tolerance_nm=0.5,
    )
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    candidate_rows: list[dict[str, Any]] = []
    unique_currents: dict[str, dict[str, float]] = {}
    for run in runs:
        meta_path = study_root / run["artifacts"]["model_metadata"]
        model = load_surrogate(json.loads(meta_path.read_text(encoding="utf-8")))
        flux_map = FittedSurrogateMap(model, domain)
        scheduler = CopperLossScheduler(
            flux_map,
            limits=limits,
            n_grid_id=n_grid,
            n_grid_iq=n_grid,
            n_grid_if=max(8, n_grid // 2),
            n_random_refine=n_random_refine,
            seed=int(manifest["seeds"]["model"]),
        )
        candidate_id = "%s|%s|%s|r%s" % (
            run["strategy"],
            run["budget"],
            run["family"],
            run["design_replicate"],
        )
        for command in commands:
            result = scheduler.schedule(command["rpm_mech"], command["torque_nm"])
            payload = result.to_dict()
            payload.update(
                {
                    "candidate_id": candidate_id,
                    "strategy": run["strategy"],
                    "budget": run["budget"],
                    "family": run["family"],
                    "design_replicate": run["design_replicate"],
                    "command_id": command["command_id"],
                    "regime": command["regime"],
                }
            )
            candidate_rows.append(payload)
            if (
                result.id_ref_a is not None
                and result.iq_ref_a is not None
                and result.if_ref_a is not None
            ):
                point_id = canonical_point_id(
                    result.id_ref_a, result.iq_ref_a, result.if_ref_a
                )
                unique_currents[point_id] = {
                    "point_id": point_id,
                    "id_a": float(result.id_ref_a),
                    "iq_a": float(result.iq_ref_a),
                    "if_a": float(result.if_ref_a),
                }

    current_rows = [
        {
            "point_name": row["point_id"],
            "point_id": row["point_id"],
            "role": "reference",
            "region": classify_region(
                row["id_a"],
                row["iq_a"],
                row["if_a"],
                _domain_dict(domain),
            ),
            "id_a": row["id_a"],
            "iq_a": row["iq_a"],
            "if_a": row["if_a"],
        }
        for row in unique_currents.values()
    ]
    current_rows.sort(key=lambda row: row["point_id"])
    current_bytes = render_femm_points(current_rows)
    (output_root / "scheduler_selected_currents.csv").write_bytes(current_bytes)
    feasible = [
        row
        for row in candidate_rows
        if row["status"] in {"feasible", "saturated_to_boundary"}
    ]
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "eesm_phase2_model_test_20260814",
        "n_maps": len(list(runs)),
        "n_commands": len(commands),
        "n_schedules": len(candidate_rows),
        "n_feasible_or_boundary": len(feasible),
        "n_unique_selected_currents": len(current_rows),
        "selected_currents_sha256": _sha256_bytes(current_bytes),
        "schedules": candidate_rows,
        "status": "completed",
        "not_electromagnetic_truth": True,
    }
    _write_json(output_root / "scheduler_commands_offline.json", payload)
    return payload


def missing_audit_points(
    scheduled_csv: str | Path,
    known_csvs: Sequence[str | Path],
    dest: str | Path,
) -> dict[str, Any]:
    """Write scheduled currents that are not already in known FEMM truth."""
    known: set[str] = set()
    for path in known_csvs:
        if Path(path).is_file():
            known |= campaign_id_set(load_campaign_rows(path))
    scheduled = load_campaign_rows(scheduled_csv)
    missing = [row for row in scheduled if row["point_id"] not in known]
    dest_path = Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    payload_bytes = render_femm_points(missing)
    dest_path.write_bytes(payload_bytes)
    return {
        "n_scheduled": len(scheduled),
        "n_known": len(known),
        "n_missing": len(missing),
        "dest": str(dest_path),
        "sha256": _sha256_bytes(payload_bytes),
    }


def run_model_tests(
    fit_root: str | Path,
    manifest: Mapping[str, Any],
    output_dir: str | Path,
    holdout_campaigns: Mapping[str, str | Path],
    known_truth_csvs: Sequence[str | Path],
) -> dict[str, Any]:
    """Score saved maps on holdouts and schedule control tests. No FEMM."""
    from surrogates.registry import load_surrogate

    fit_path = Path(fit_root)
    summary = json.loads(
        (fit_path / "design_replicate_fit.json").read_text(encoding="utf-8")
    )
    output_root = Path(output_dir)
    if (output_root / "model_test.json").is_file():
        raise RuntimeError(
            "REFUSED: %s already exists; choose a new dated root"
            % (output_root / "model_test.json")
        )
    output_root.mkdir(parents=True, exist_ok=True)
    pole_pairs = int(manifest["machine"]["pole_pairs"])
    recommended = recommend_cell(summary, budget=256)

    holdouts: dict[str, Any] = {}
    for label, campaign in holdout_campaigns.items():
        campaign_path = Path(campaign)
        if not campaign_path.is_file():
            holdouts[label] = {"status": "missing", "path": str(campaign_path)}
            continue
        arrays = campaign_arrays(campaign_path)
        scores = []
        for run in summary["runs"]:
            meta_path = fit_path / run["artifacts"]["model_metadata"]
            model = load_surrogate(json.loads(meta_path.read_text(encoding="utf-8")))
            scored = score_model_on_arrays(
                model, arrays["X"], arrays["y"], arrays["regions"], pole_pairs
            )
            scores.append(
                {
                    "strategy": run["strategy"],
                    "budget": run["budget"],
                    "family": run["family"],
                    "design_replicate": run["design_replicate"],
                    "selection_torque_rmse_nm": run["torque_rmse_nm"],
                    **scored,
                }
            )
        holdouts[label] = {
            "status": "scored" if arrays["n_usable"] else "empty",
            "path": arrays["path"],
            "n_rows": arrays["n_rows"],
            "n_usable": arrays["n_usable"],
            "scores": scores,
        }

    control_runs = select_control_test_runs(summary, budget=256)
    schedule_dir = output_root / "scheduler"
    schedule = run_fitted_map_schedules(
        fit_path, manifest, schedule_dir, control_runs
    )
    missing = missing_audit_points(
        schedule_dir / "scheduler_selected_currents.csv",
        known_truth_csvs,
        output_root / "points" / "new_map_scheduler_audit.csv",
    )
    payload = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "experiment_id": "eesm_phase2_model_test_20260814",
        "fit_root": str(fit_path),
        "recommended_cell_budget256": recommended,
        "n_control_maps": len(control_runs),
        "holdouts": {
            label: {
                key: value
                for key, value in info.items()
                if key != "scores"
            }
            | {"n_scored_maps": len(info.get("scores") or [])}
            for label, info in holdouts.items()
        },
        "holdout_scores": {
            label: info.get("scores")
            for label, info in holdouts.items()
            if info.get("scores")
        },
        "scheduler": {
            "n_maps": schedule["n_maps"],
            "n_schedules": schedule["n_schedules"],
            "n_feasible_or_boundary": schedule["n_feasible_or_boundary"],
            "n_unique_selected_currents": schedule["n_unique_selected_currents"],
            "selected_currents_sha256": schedule["selected_currents_sha256"],
        },
        "new_audit_points": missing,
        "status": "completed",
        "not_a_phase0_revision": True,
        "not_electromagnetic_truth": True,
    }
    _write_json(output_root / "model_test.json", payload)
    _write_json(output_root / "holdout_scores.json", payload["holdout_scores"])
    return payload


def write_freeze(
    output_dir: str | Path,
    manifest: Mapping[str, Any],
    campaign_rows: Sequence[Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    existing_ids = campaign_id_set(campaign_rows) if campaign_rows else set()
    designs = build_design_replicates(manifest, existing_ids=existing_ids)
    domain = equal_budget._domain_from_manifest(manifest)
    reserved_ids = set(designs["reserved"]["selection"]) | set(
        designs["reserved"]["scheduler_audit"]
    )
    boundary = build_boundary_set(domain, reserved_ids)
    wst = (
        build_wst360_set(campaign_rows)
        if campaign_rows
        else []
    )
    commands = build_scheduler_commands()

    points_dir = output_root / "points"
    points_dir.mkdir(parents=True, exist_ok=True)
    design_bytes = render_femm_points(designs["new_femm_rows"])
    boundary_bytes = render_femm_points(boundary)
    (points_dir / "design_replicate_new_femm.csv").write_bytes(design_bytes)
    (points_dir / "boundary_set.csv").write_bytes(boundary_bytes)
    wst_sha = None
    if wst:
        wst_bytes = render_femm_points(wst)
        (points_dir / "wst360_set.csv").write_bytes(wst_bytes)
        wst_sha = _sha256_bytes(wst_bytes)

    _write_json(output_root / "designs" / "replicates.json", designs["designs"])
    _write_json(output_root / "commands" / "scheduler_commands.json", {
        "n": len(commands),
        "commands": commands,
    })

    freeze = {
        "experiment_id": PHASE2_ID,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "not_a_phase0_revision": True,
        "phase2_thresholds": PHASE2_THRESHOLDS,
        "n_design_replicates_additional": N_DESIGN_REPLICATES,
        "n_model_seeds": N_MODEL_SEEDS,
        "n_new_unique_femm_train": designs["n_new_unique_femm"],
        "n_boundary": len(boundary),
        "n_wst360": len(wst),
        "n_scheduler_commands": len(commands),
        "reserved_selection_n": len(designs["reserved"]["selection"]),
        "reserved_audit_n": len(designs["reserved"]["scheduler_audit"]),
        "hashes": {
            "design_replicate_new_femm_csv": _sha256_bytes(design_bytes),
            "boundary_set_csv": _sha256_bytes(boundary_bytes),
            "wst360_set_csv": wst_sha,
            "selection_ids": _sha256_bytes(
                "\n".join(designs["reserved"]["selection"]).encode("ascii")
            ),
            "scheduler_audit_ids": _sha256_bytes(
                "\n".join(designs["reserved"]["scheduler_audit"]).encode("ascii")
            ),
        },
        "existing_campaign_rows": len(existing_ids),
    }
    _write_json(output_root / "freeze.json", freeze)
    return freeze
