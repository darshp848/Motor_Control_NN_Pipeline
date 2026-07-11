"""Synthetic EESM validation helpers (metrics, domain labels, smoke checks)."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional, Sequence, Union

import numpy as np

from scheduler.copper_loss_scheduler import (
    CopperLossScheduler,
    SchedulerLimits,
    electromagnetic_torque_eesm,
)
from synthetic.synthetic_map import MapDomain, SyntheticEESMMap, load_map_from_manifest
from validation.controller_metrics import evaluate_controller_metrics

ArrayLike = Union[float, Sequence[float], np.ndarray]

DOMAIN_LABELS = (
    "in_domain_interpolation",
    "boundary",
    "extrapolation",
)

METRIC_KEYS = (
    "rmse_lambda_d",
    "rmse_lambda_q",
    "rmse_flux_mean",
    "n",
)

TORQUE_ERR_KEYS = (
    "mae_torque_nm",
    "rmse_torque_nm",
    "max_abs_torque_nm",
    "n",
)

VOLTAGE_ERR_KEYS = (
    "mae_v_mag_v",
    "rmse_v_mag_v",
    "max_abs_v_mag_v",
    "n",
)


def flux_rmse(
    lambda_d_true: ArrayLike,
    lambda_q_true: ArrayLike,
    lambda_d_pred: ArrayLike,
    lambda_q_pred: ArrayLike,
) -> Dict[str, float]:
    """Flux linkage RMSE for lambda_d, lambda_q, and their mean."""
    ld_t = np.asarray(lambda_d_true, dtype=np.float64).ravel()
    lq_t = np.asarray(lambda_q_true, dtype=np.float64).ravel()
    ld_p = np.asarray(lambda_d_pred, dtype=np.float64).ravel()
    lq_p = np.asarray(lambda_q_pred, dtype=np.float64).ravel()
    if not (ld_t.size == lq_t.size == ld_p.size == lq_p.size):
        raise ValueError("flux arrays must have matching lengths")
    n = int(ld_t.size)
    if n == 0:
        return {
            "rmse_lambda_d": float("nan"),
            "rmse_lambda_q": float("nan"),
            "rmse_flux_mean": float("nan"),
            "n": 0,
        }
    rmse_d = float(np.sqrt(np.mean((ld_p - ld_t) ** 2)))
    rmse_q = float(np.sqrt(np.mean((lq_p - lq_t) ** 2)))
    return {
        "rmse_lambda_d": rmse_d,
        "rmse_lambda_q": rmse_q,
        "rmse_flux_mean": 0.5 * (rmse_d + rmse_q),
        "n": n,
    }


def torque_error(
    t_true_nm: ArrayLike,
    t_pred_nm: ArrayLike,
) -> Dict[str, float]:
    """Torque absolute / RMSE errors (N.m)."""
    tt = np.asarray(t_true_nm, dtype=np.float64).ravel()
    tp = np.asarray(t_pred_nm, dtype=np.float64).ravel()
    if tt.size != tp.size:
        raise ValueError("torque arrays must have matching lengths")
    n = int(tt.size)
    if n == 0:
        return {
            "mae_torque_nm": float("nan"),
            "rmse_torque_nm": float("nan"),
            "max_abs_torque_nm": float("nan"),
            "n": 0,
        }
    err = np.abs(tp - tt)
    return {
        "mae_torque_nm": float(np.mean(err)),
        "rmse_torque_nm": float(np.sqrt(np.mean((tp - tt) ** 2))),
        "max_abs_torque_nm": float(np.max(err)),
        "n": n,
    }


def voltage_error(
    v_true_v: ArrayLike,
    v_pred_v: ArrayLike,
) -> Dict[str, float]:
    """Stator voltage magnitude absolute / RMSE errors (V)."""
    vt = np.asarray(v_true_v, dtype=np.float64).ravel()
    vp = np.asarray(v_pred_v, dtype=np.float64).ravel()
    if vt.size != vp.size:
        raise ValueError("voltage arrays must have matching lengths")
    n = int(vt.size)
    if n == 0:
        return {
            "mae_v_mag_v": float("nan"),
            "rmse_v_mag_v": float("nan"),
            "max_abs_v_mag_v": float("nan"),
            "n": 0,
        }
    err = np.abs(vp - vt)
    return {
        "mae_v_mag_v": float(np.mean(err)),
        "rmse_v_mag_v": float(np.sqrt(np.mean((vp - vt) ** 2))),
        "max_abs_v_mag_v": float(np.max(err)),
        "n": n,
    }


def label_domain_3d(
    id_: ArrayLike,
    iq: ArrayLike,
    if_: ArrayLike,
    domain: MapDomain,
    boundary_fraction: float = 0.05,
    atol: float = 1e-9,
) -> np.ndarray:
    """Label (id, iq, if) relative to an axis-aligned 3D current box.

    Labels:
      - in_domain_interpolation: strictly inside, outside boundary band
      - boundary: inside domain but within boundary_fraction of any edge span
      - extrapolation: outside the box

    boundary_fraction is relative to each axis span (default 5% of range).
    """
    id_a = np.asarray(id_, dtype=np.float64)
    iq_a = np.asarray(iq, dtype=np.float64)
    if_a = np.asarray(if_, dtype=np.float64)
    shape = np.broadcast_shapes(id_a.shape, iq_a.shape, if_a.shape)
    id_a = np.broadcast_to(id_a, shape)
    iq_a = np.broadcast_to(iq_a, shape)
    if_a = np.broadcast_to(if_a, shape)

    outside = ~domain.contains(id_a, iq_a, if_a, tol=atol)
    labels = np.full(shape, "in_domain_interpolation", dtype=object)
    labels[outside] = "extrapolation"

    span_id = max(domain.id_max_a - domain.id_min_a, 0.0)
    span_iq = max(domain.iq_max_a - domain.iq_min_a, 0.0)
    span_if = max(domain.if_max_a - domain.if_min_a, 0.0)
    m_id = boundary_fraction * span_id
    m_iq = boundary_fraction * span_iq
    m_if = boundary_fraction * span_if

    inside = ~outside
    if np.any(inside):
        near_id = (id_a - domain.id_min_a <= m_id + atol) | (
            domain.id_max_a - id_a <= m_id + atol
        )
        near_iq = (iq_a - domain.iq_min_a <= m_iq + atol) | (
            domain.iq_max_a - iq_a <= m_iq + atol
        )
        near_if = (if_a - domain.if_min_a <= m_if + atol) | (
            domain.if_max_a - if_a <= m_if + atol
        )
        boundary = inside & (near_id | near_iq | near_if)
        labels[boundary] = "boundary"

    return labels


def write_json_summary(path: str, payload: Dict[str, Any], indent: int = 2) -> str:
    """Write a JSON summary with stable UTF-8 encoding."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=indent)
        f.write("\n")
    return path


def run_smoke_validation(
    manifest_path: Optional[str] = None,
    fmap: Optional[SyntheticEESMMap] = None,
) -> Dict[str, Any]:
    """Run a few smoke checks; returns a JSON-serializable report."""
    if fmap is None:
        fmap = (
            load_map_from_manifest(manifest_path)
            if manifest_path
            else SyntheticEESMMap()
        )
    report: Dict[str, Any] = {"ok": True, "checks": {}}

    ld, lq = fmap.flux_point(-40.0, 60.0, 5.0)
    finite = bool(np.isfinite(ld) and np.isfinite(lq))
    report["checks"]["finite_flux"] = finite
    if not finite:
        report["ok"] = False

    ld0, _ = fmap.flux_point(-40.0, 60.0, 2.0)
    ld1, _ = fmap.flux_point(-40.0, 60.0, 8.0)
    if_increases_ld = bool(ld1 > ld0)
    report["checks"]["if_increases_lambda_d"] = if_increases_ld
    report["checks"]["lambda_d_at_if2"] = ld0
    report["checks"]["lambda_d_at_if8"] = ld1
    if not if_increases_ld:
        report["ok"] = False

    ld_arr, lq_arr = fmap.flux(-30.0, 50.0, 6.0)
    t = float(
        electromagnetic_torque_eesm(
            np.array([-30.0]),
            np.array([50.0]),
            np.asarray(ld_arr),
            np.asarray(lq_arr),
            pole_pairs=2,
        )[0]
    )
    report["checks"]["sample_torque_nm"] = t
    report["checks"]["torque_finite"] = bool(np.isfinite(t))
    if not np.isfinite(t):
        report["ok"] = False

    # Self-consistency: identical predictions → zero flux RMSE
    ld_t, lq_t = fmap.flux(
        np.array([-20.0, -40.0]),
        np.array([30.0, 50.0]),
        np.array([4.0, 8.0]),
    )
    z = flux_rmse(ld_t, lq_t, ld_t, lq_t)
    report["checks"]["self_flux_rmse"] = z
    if not (z["rmse_flux_mean"] == 0.0 and z["n"] == 2):
        report["ok"] = False

    controller = evaluate_controller_metrics(
        {
            "id_a": np.array([-20.0, -40.0]),
            "iq_a": np.array([30.0, 50.0]),
            "if_a": np.array([4.0, 8.0]),
            "region": np.array(["interior", "interior"]),
        },
        np.column_stack([ld_t, lq_t]),
        np.column_stack([ld_t, lq_t]),
        {
            "pole_pairs": 2,
            "rs_ohm": 0.05,
            "rf_ohm": 8.0,
            "vdc_v": 400.0,
            "i_s_max_peak_a": 120.0,
            "i_f_min_a": 0.0,
            "i_f_max_a": 15.0,
        },
        speeds_rpm=[0.0, 3000.0],
    )
    controller_identity = (
        controller["overall"]["torque_nm"]["rmse"] == 0.0
        and all(
            item["rmse"] == 0.0
            for item in controller["overall"]["voltage_magnitude_v"].values()
        )
    )
    report["checks"]["controller_metric_identity"] = controller_identity
    if not controller_identity:
        report["ok"] = False

    # Domain labels cover all three classes on a hand-picked set
    labels = label_domain_3d(
        np.array([-60.0, -1.0, 50.0]),
        np.array([60.0, 1.0, 10.0]),
        np.array([7.5, 0.1, 5.0]),
        fmap.domain,
        boundary_fraction=0.05,
    )
    report["checks"]["domain_label_example"] = [str(x) for x in labels.tolist()]
    report["checks"]["domain_labels_valid"] = all(
        lab in DOMAIN_LABELS for lab in labels
    )
    if not report["checks"]["domain_labels_valid"]:
        report["ok"] = False

    sched = CopperLossScheduler(
        fmap,
        limits=SchedulerLimits(
            rs_ohm=0.05,
            rf_ohm=8.0,
            vdc_v=400.0,
            i_s_max_peak_a=120.0,
            i_f_max_a=15.0,
            pole_pairs=2,
            torque_tolerance_nm=1.0,
        ),
        n_grid_id=20,
        n_grid_iq=20,
        n_grid_if=10,
        n_random_refine=100,
        seed=0,
    )
    modest = sched.schedule(omega_rpm=1500.0, t_ref_nm=20.0)
    report["checks"]["modest_torque_status"] = modest.status
    report["checks"]["modest_feasible"] = modest.status in (
        "feasible",
        "saturated_to_boundary",
    )
    report["checks"]["modest_flags"] = {
        "torque_ok": modest.torque_ok,
        "voltage_ok": modest.voltage_ok,
        "stator_current_ok": modest.stator_current_ok,
        "field_current_ok": modest.field_current_ok,
        "domain_ok": modest.domain_ok,
    }
    if modest.status not in ("feasible", "saturated_to_boundary"):
        report["ok"] = False

    huge = sched.schedule(omega_rpm=1500.0, t_ref_nm=1.0e6)
    report["checks"]["huge_torque_status"] = huge.status
    report["checks"]["huge_no_fake_refs"] = (
        huge.id_ref_a is None
        and huge.iq_ref_a is None
        and huge.if_ref_a is None
        and huge.status in ("infeasible", "out_of_domain", "search_failed")
    )
    report["checks"]["huge_flags_all_false"] = not any(
        [
            huge.torque_ok,
            huge.voltage_ok,
            huge.stator_current_ok,
            huge.field_current_ok,
            huge.domain_ok,
        ]
    )
    if not report["checks"]["huge_no_fake_refs"]:
        report["ok"] = False
    if not report["checks"]["huge_flags_all_false"]:
        report["ok"] = False

    return report
