"""Compute the Phase 0 threshold *proposal*. Does not edit the manifest."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from validation.controller_metrics import evaluate_controller_metrics
from validation.gates import REQUIRED_GATES

DESIGN_KEYS = ("tensor_grid_64", "random_64", "latin_hypercube_64")
IDW_POWER = 2.0
IDW_EXACT_EPS = 1.0e-12
SPEEDS_RPM = (3000.0, 9000.0)
DOMAIN = {
    "id_a": (-120.0, 0.0),
    "iq_a": (0.0, 120.0),
    "if_a": (0.0, 15.0),
}
FLOORS = {
    "data_qa": 0.0,
    "interior": 1.0e-3,
    "boundary": 1.0e-3,
    "saturation": 1.0e-3,
    "field_weakening": 1.0e-3,
    "torque": 0.5,
    "voltage": 2.0,
    "feasibility": 0.02,
}
COMPETING_FAMILIES = (
    "physics_polynomial",
    "rbf_or_gp",
    "tree_ensemble",
    "compact_mlp",
)
FORBIDDEN_ROLES = ("selection", "scheduler_audit")


class ThresholdMethodRefusal(RuntimeError):
    """A method invariant failed. No proposal was written."""


def _normalize(currents: np.ndarray) -> np.ndarray:
    scaled = np.empty_like(currents, dtype=np.float64)
    for axis, name in enumerate(("id_a", "iq_a", "if_a")):
        low, high = DOMAIN[name]
        scaled[:, axis] = (currents[:, axis] - low) / (high - low)
    return scaled


def idw_predict(
    train_x: np.ndarray,
    train_y: np.ndarray,
    query_x: np.ndarray,
    power: float = IDW_POWER,
) -> np.ndarray:
    """Predict (n, 2) fluxes. Currents must already be normalized."""
    if train_x.shape[0] == 0:
        raise ThresholdMethodRefusal("IDW train set is empty")
    out = np.empty((query_x.shape[0], train_y.shape[1]), dtype=np.float64)
    for i, query in enumerate(query_x):
        dist = np.linalg.norm(train_x - query, axis=1)
        nearest = int(np.argmin(dist))
        if dist[nearest] <= IDW_EXACT_EPS:
            out[i] = train_y[nearest]
            continue
        weights = 1.0 / np.power(dist, power)
        weights = weights / np.sum(weights)
        out[i] = weights @ train_y
    return out


def _machine_from_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    machine = manifest["machine"]
    return {
        "pole_pairs": int(machine["pole_pairs"]),
        "rs_ohm": float(machine["rs_ohm"]),
        "rf_ohm": float(machine["rf_ohm"]),
        "vdc_v": float(machine["vdc_v"]),
        "i_s_max_peak_a": float(machine["i_s_max_peak_a"]),
        "i_f_min_a": float(machine["i_f_min_a"]),
        "i_f_max_a": float(machine["i_f_max_a"]),
    }


def voltage_feasible(
    id_a: np.ndarray,
    iq_a: np.ndarray,
    if_a: np.ndarray,
    flux: np.ndarray,
    machine: Mapping[str, Any],
    rpm: float = 3000.0,
) -> np.ndarray:
    from scheduler.copper_loss_scheduler import (
        rpm_mech_to_we,
        stator_voltage_eesm,
    )

    omega_e = rpm_mech_to_we(rpm, int(machine["pole_pairs"]))
    vmag = stator_voltage_eesm(
        id_a, iq_a, flux[:, 0], flux[:, 1], omega_e, float(machine["rs_ohm"])
    )[2]
    v_max = float(machine["vdc_v"]) / math.sqrt(3.0)
    is_mag = np.hypot(id_a, iq_a)
    return (
        (vmag <= v_max)
        & (is_mag <= float(machine["i_s_max_peak_a"]))
        & (if_a >= float(machine["i_f_min_a"]))
        & (if_a <= float(machine["i_f_max_a"]))
    )


def load_campaign_rows(results_csv: Path) -> list[dict[str, str]]:
    with results_csv.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def load_design_ids(designs_dir: Path, key: str) -> list[str]:
    payload = json.loads((designs_dir / f"{key}.json").read_text(encoding="utf-8"))
    ids = [str(value) for value in payload["point_ids"]]
    if not ids:
        raise ThresholdMethodRefusal(f"empty design {key}")
    return ids


def _rows_by_id(rows: Sequence[Mapping[str, str]]) -> dict[str, Mapping[str, str]]:
    return {row["point_id"]: row for row in rows}


def _currents_and_flux(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    currents = np.array(
        [[float(row["id_a"]), float(row["iq_a"]), float(row["if_a"])] for row in rows],
        dtype=np.float64,
    )
    flux = np.array(
        [[float(row["lambda_d_wb"]), float(row["lambda_q_wb"])] for row in rows],
        dtype=np.float64,
    )
    return currents, flux


def campaign_data_qa(rows: Sequence[Mapping[str, str]]) -> float:
    if not rows:
        raise ThresholdMethodRefusal("campaign has no rows")
    failed = 0
    for row in rows:
        try:
            finite = all(
                math.isfinite(float(row[key]))
                for key in (
                    "id_a", "iq_a", "if_a", "lambda_d_wb", "lambda_q_wb",
                    "torque_identity_nm",
                )
            )
        except (TypeError, ValueError, KeyError):
            finite = False
        ok = finite and str(row.get("converged")) in ("True", "true", "1")
        if not ok:
            failed += 1
    return float(failed) / float(len(rows))


def instrument_gate_values(
    train_rows: Sequence[Mapping[str, Any]],
    holdout_rows: Sequence[Mapping[str, Any]],
    machine: Mapping[str, Any],
) -> dict[str, float]:
    if any(row.get("role") in FORBIDDEN_ROLES for row in train_rows):
        raise ThresholdMethodRefusal("instrument train includes a forbidden role")
    if any(row.get("role") in FORBIDDEN_ROLES for row in holdout_rows):
        raise ThresholdMethodRefusal("instrument holdout includes a forbidden role")
    train_x, train_y = _currents_and_flux(train_rows)
    query_x, truth_y = _currents_and_flux(holdout_rows)
    predicted = idw_predict(_normalize(train_x), train_y, _normalize(query_x))
    id_a = query_x[:, 0]
    iq_a = query_x[:, 1]
    if_a = query_x[:, 2]
    points = {
        "id_a": id_a,
        "iq_a": iq_a,
        "if_a": if_a,
        "region": np.array([row["region"] for row in holdout_rows], dtype=object),
        "data_qa_passed": np.ones(len(holdout_rows), dtype=bool),
        "truth_feasible": voltage_feasible(id_a, iq_a, if_a, truth_y, machine),
        "predicted_feasible": voltage_feasible(id_a, iq_a, if_a, predicted, machine),
    }
    metrics = evaluate_controller_metrics(
        points, truth_y, predicted, machine, speeds_rpm=list(SPEEDS_RPM)
    )
    values = {gate: float(metrics["gate_values"][gate]) for gate in REQUIRED_GATES}
    return values


def propose_thresholds(
    campaign_rows: Sequence[Mapping[str, str]],
    designs: Mapping[str, Sequence[str]],
    machine: Mapping[str, Any],
) -> dict[str, Any]:
    if set(designs) != set(DESIGN_KEYS):
        raise ThresholdMethodRefusal("designs must be exactly the three 64-point sets")
    by_id = _rows_by_id(campaign_rows)
    train_rows = [row for row in campaign_rows if row["role"] == "train"]
    if not train_rows:
        raise ThresholdMethodRefusal("no train rows")
    data_qa = campaign_data_qa(campaign_rows)
    per_design: dict[str, dict[str, float]] = {}
    for key in DESIGN_KEYS:
        train_ids = [point_id for point_id in designs[key] if point_id in by_id]
        holdout = [row for row in train_rows if row["point_id"] not in set(train_ids)]
        fitted = [by_id[point_id] for point_id in train_ids]
        if len(fitted) < 8 or len(holdout) < 8:
            raise ThresholdMethodRefusal(f"{key} has too few train/holdout rows")
        per_design[key] = instrument_gate_values(fitted, holdout, machine)
        per_design[key]["data_qa"] = data_qa

    raw = {
        gate: max(per_design[key][gate] for key in DESIGN_KEYS)
        for gate in REQUIRED_GATES
    }
    raw["data_qa"] = data_qa
    proposed = {
        gate: float(max(raw[gate], FLOORS[gate])) for gate in REQUIRED_GATES
    }
    return {
        "status": "proposal_not_frozen",
        "instrument": "idw_power_2_normalized_currents",
        "not_a_competing_family": True,
        "competing_families_excluded": list(COMPETING_FAMILIES),
        "designs": list(DESIGN_KEYS),
        "speeds_rpm": list(SPEEDS_RPM),
        "floors": dict(FLOORS),
        "v_max_phase_peak": float(machine["vdc_v"]) / math.sqrt(3.0),
        "data_qa_campaign": data_qa,
        "per_design": per_design,
        "raw_max": raw,
        "proposed_thresholds": proposed,
        "scheduler_audit_used": False,
        "selection_used": False,
    }


def write_proposal(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
