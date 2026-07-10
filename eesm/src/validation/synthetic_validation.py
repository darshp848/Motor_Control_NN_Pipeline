"""Lightweight synthetic EESM validation helpers (callable from CLI/tests)."""

from __future__ import annotations

from typing import Any, Dict

import numpy as np

from scheduler.copper_loss_scheduler import (
    CopperLossScheduler,
    SchedulerLimits,
    electromagnetic_torque_eesm,
)
from synthetic.synthetic_map import SyntheticEESMMap, load_map_from_manifest


def run_smoke_validation(manifest_path: str | None = None) -> Dict[str, Any]:
    """Run a few smoke checks; returns a JSON-serializable report."""
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

    ld, lq = fmap.flux(-30.0, 50.0, 6.0)
    t = float(
        electromagnetic_torque_eesm(
            np.array([-30.0]),
            np.array([50.0]),
            np.asarray(ld),
            np.asarray(lq),
            pole_pairs=2,
        )[0]
    )
    report["checks"]["sample_torque_nm"] = t
    report["checks"]["torque_finite"] = bool(np.isfinite(t))
    if not np.isfinite(t):
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
    if not report["checks"]["huge_no_fake_refs"]:
        report["ok"] = False

    return report
