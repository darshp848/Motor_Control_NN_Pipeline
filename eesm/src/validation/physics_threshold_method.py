"""Propose Paper 2 physics gates from IDW. Does not fit a competing family."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from metrics import ldiff
from metrics import reciprocity as recip
from metrics.reciprocity import FIELD_SECTOR_TO_TERMINAL
from validation.threshold_method import (
    DESIGN_KEYS,
    FORBIDDEN_ROLES,
    ThresholdMethodRefusal,
    _normalize,
    _rows_by_id,
    idw_predict,
)


PHYSICS_GATES = (
    "R_dq_rms_h",
    "R_fd_rms_h",
    "R_fq_rms_h",
    "ldiff_frobenius_rel",
    "ldiff_offdiag_rel",
)

LDIFF_REL_FLOOR = 0.05

COMPETING_FAMILIES = (
    "physics_polynomial",
    "rbf_or_gp",
    "tree_ensemble",
    "compact_mlp",
    "energy_gradient_net",
    "pwa",
)


def _three_channel_flux(rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    currents = np.array(
        [[float(row["id_a"]), float(row["iq_a"]), float(row["if_a"])] for row in rows],
        dtype=np.float64,
    )
    flux = np.array(
        [
            [
                float(row["lambda_d_wb"]),
                float(row["lambda_q_wb"]),
                FIELD_SECTOR_TO_TERMINAL * float(row["lambda_field_wb"]),
            ]
            for row in rows
        ],
        dtype=np.float64,
    )
    return currents, flux


def make_idw_predictor(
    train_rows: Sequence[Mapping[str, Any]],
):
    """Return predict(X_phys) -> (n, 3) from a 3-output IDW fit."""
    if any(row.get("role") in FORBIDDEN_ROLES for row in train_rows):
        raise ThresholdMethodRefusal("instrument train includes a forbidden role")
    train_x, train_y = _three_channel_flux(train_rows)
    train_n = _normalize(train_x)

    def predict(query: np.ndarray) -> np.ndarray:
        return idw_predict(train_n, train_y, _normalize(np.asarray(query)))

    return predict


def instrument_physics_values(
    train_rows: Sequence[Mapping[str, Any]],
    holdout_rows: Sequence[Mapping[str, Any]],
    anchors: Mapping[str, Any],
) -> dict[str, float]:
    if any(row.get("role") in FORBIDDEN_ROLES for row in holdout_rows):
        raise ThresholdMethodRefusal("instrument holdout includes a forbidden role")
    predict = make_idw_predictor(train_rows)
    holdout_x, _ = _three_channel_flux(holdout_rows)
    residuals = recip.reciprocity_residuals(predict, holdout_x)
    summary = recip.summarize(residuals)
    ldiff_metrics = ldiff.ldiff_error(predict, anchors)
    offdiag = ldiff_metrics["off_diagonal_mean_rel_rmse"]
    if offdiag is None:
        raise ThresholdMethodRefusal("IDW off-diagonal L_diff is unavailable")
    return {
        "R_dq_rms_h": float(summary["R_dq"]["rms_h"]),
        "R_fd_rms_h": float(summary["R_fd"]["rms_h"]),
        "R_fq_rms_h": float(summary["R_fq"]["rms_h"]),
        "R_fd_naive_rms_h": float(summary["R_fd_naive"]["rms_h"]),
        "n_reciprocity_eval": int(summary["n_eval"]),
        "ldiff_frobenius_rel": float(ldiff_metrics["frobenius_rel_rmse"]),
        "ldiff_offdiag_rel": float(offdiag),
    }


def propose_physics_thresholds(
    campaign_rows: Sequence[Mapping[str, str]],
    designs: Mapping[str, Sequence[str]],
    anchors: Mapping[str, Any],
) -> dict[str, Any]:
    if set(designs) != set(DESIGN_KEYS):
        raise ThresholdMethodRefusal("designs must be exactly the three 64-point sets")
    by_id = _rows_by_id(campaign_rows)
    train_rows = [row for row in campaign_rows if row["role"] == "train"]
    if not train_rows:
        raise ThresholdMethodRefusal("no train rows")

    floors = recip.fem_reciprocity_floors(anchors)
    physics_floors = {
        "R_dq_rms_h": float(floors["R_dq"]),
        "R_fd_rms_h": float(floors["R_fd"]),
        "R_fq_rms_h": float(floors["R_fq"]),
        "ldiff_frobenius_rel": LDIFF_REL_FLOOR,
        "ldiff_offdiag_rel": LDIFF_REL_FLOOR,
    }

    per_design: dict[str, dict[str, float]] = {}
    for key in DESIGN_KEYS:
        train_ids = [point_id for point_id in designs[key] if point_id in by_id]
        holdout = [row for row in train_rows if row["point_id"] not in set(train_ids)]
        fitted = [by_id[point_id] for point_id in train_ids]
        if len(fitted) < 8 or len(holdout) < 8:
            raise ThresholdMethodRefusal(f"{key} has too few train/holdout rows")
        per_design[key] = instrument_physics_values(fitted, holdout, anchors)

    raw = {
        gate: max(per_design[key][gate] for key in DESIGN_KEYS)
        for gate in PHYSICS_GATES
    }
    proposed = {
        gate: float(max(raw[gate], physics_floors[gate])) for gate in PHYSICS_GATES
    }
    return {
        "status": "proposal_frozen_as_physics_gates",
        "instrument": "idw_power_2_normalized_currents_three_output",
        "not_a_competing_family": True,
        "competing_families_excluded": list(COMPETING_FAMILIES),
        "designs": list(DESIGN_KEYS),
        "steps_a": list(recip.DEFAULT_STEPS),
        "floors": physics_floors,
        "fem_reciprocity_floors_h": floors,
        "per_design": per_design,
        "raw_max": raw,
        "proposed_thresholds": proposed,
        "selection_used": False,
        "scheduler_audit_used": False,
        "family_fits_used": False,
        "contamination_disclosure": (
            "Phase 1 family reciprocity/L_diff tables were already visible. "
            "They did not set these numbers. The IDW reciprocity residual "
            "was computed for the first time in this proposal."
        ),
    }


def write_proposal(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
