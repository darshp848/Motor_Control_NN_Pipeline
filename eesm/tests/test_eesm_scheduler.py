"""Tests for EESM copper-loss scheduler and torque consistency."""

from __future__ import annotations

import os
import sys

import numpy as np
import pytest

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from scheduler.copper_loss_scheduler import (  # noqa: E402
    CopperLossScheduler,
    SchedulerLimits,
    copper_loss,
    electromagnetic_torque_eesm,
    stator_voltage_eesm,
)
from synthetic.synthetic_map import SyntheticEESMMap  # noqa: E402


@pytest.fixture
def fmap() -> SyntheticEESMMap:
    return SyntheticEESMMap()


@pytest.fixture
def scheduler(fmap: SyntheticEESMMap) -> CopperLossScheduler:
    return CopperLossScheduler(
        fmap,
        limits=SchedulerLimits(
            rs_ohm=0.05,
            rf_ohm=8.0,
            vdc_v=400.0,
            i_s_max_peak_a=120.0,
            i_f_min_a=0.0,
            i_f_max_a=15.0,
            pole_pairs=2,
            torque_tolerance_nm=1.0,
        ),
        n_grid_id=22,
        n_grid_iq=22,
        n_grid_if=10,
        n_random_refine=150,
        seed=0,
    )


def test_torque_formula_consistency(fmap: SyntheticEESMMap):
    id_, iq, if_ = -30.0, 50.0, 6.0
    ld, lq = fmap.flux_point(id_, iq, if_)
    t = float(
        electromagnetic_torque_eesm(
            np.array([id_]),
            np.array([iq]),
            np.array([ld]),
            np.array([lq]),
            pole_pairs=2,
        )[0]
    )
    expected = 1.5 * 2.0 * (ld * iq - lq * id_)
    assert np.isclose(t, expected)
    assert np.isfinite(t)


def test_voltage_and_copper_loss_finite(fmap: SyntheticEESMMap):
    id_ = np.array([-40.0])
    iq = np.array([60.0])
    if_ = np.array([5.0])
    ld, lq = fmap.flux(id_, iq, if_)
    vd, vq, vmag = stator_voltage_eesm(id_, iq, ld, lq, omega_e=200.0, rs=0.05)
    pcu = copper_loss(id_, iq, if_, rs=0.05, rf=8.0)
    assert np.all(np.isfinite([vd[0], vq[0], vmag[0], pcu[0]]))
    assert pcu[0] > 0


def test_scheduler_finds_feasible_modest_torque(scheduler: CopperLossScheduler):
    res = scheduler.schedule(omega_rpm=1500.0, t_ref_nm=20.0)
    assert res.status in ("feasible", "saturated_to_boundary")
    assert res.id_ref_a is not None
    assert res.iq_ref_a is not None
    assert res.if_ref_a is not None
    assert res.torque_nm is not None
    assert abs(res.torque_nm - 20.0) <= scheduler.limits.torque_tolerance_nm + 1e-6
    # currents within limits
    is_mag = (res.id_ref_a**2 + res.iq_ref_a**2) ** 0.5
    assert is_mag <= scheduler.limits.i_s_max_peak_a + 1e-6
    assert scheduler.limits.i_f_min_a - 1e-6 <= res.if_ref_a <= scheduler.limits.i_f_max_a + 1e-6
    # constraint flags for a feasible (or soft-boundary) solution
    assert res.torque_ok is True
    assert res.stator_current_ok is True
    assert res.field_current_ok is True
    assert res.domain_ok is True
    if res.status == "feasible":
        assert res.voltage_ok is True


def test_infeasible_torque_does_not_return_fake_refs(
    scheduler: CopperLossScheduler,
):
    res = scheduler.schedule(omega_rpm=1500.0, t_ref_nm=1.0e6)
    assert res.status in ("infeasible", "out_of_domain", "search_failed")
    assert res.id_ref_a is None
    assert res.iq_ref_a is None
    assert res.if_ref_a is None
    assert res.torque_nm is None
    # conservative flags when no solution is returned
    assert res.torque_ok is False
    assert res.voltage_ok is False
    assert res.stator_current_ok is False
    assert res.field_current_ok is False
    assert res.domain_ok is False


def test_scheduler_result_to_dict_includes_flags(scheduler: CopperLossScheduler):
    res = scheduler.schedule(omega_rpm=1500.0, t_ref_nm=20.0)
    d = res.to_dict()
    for key in (
        "torque_ok",
        "voltage_ok",
        "stator_current_ok",
        "field_current_ok",
        "domain_ok",
        "status",
    ):
        assert key in d


def test_scheduler_repeatable_with_seed(fmap: SyntheticEESMMap):
    lim = SchedulerLimits(torque_tolerance_nm=1.0)
    a = CopperLossScheduler(
        fmap, limits=lim, n_grid_id=15, n_grid_iq=15, n_grid_if=8,
        n_random_refine=80, seed=3,
    ).schedule(1200.0, 15.0)
    b = CopperLossScheduler(
        fmap, limits=lim, n_grid_id=15, n_grid_iq=15, n_grid_if=8,
        n_random_refine=80, seed=3,
    ).schedule(1200.0, 15.0)
    assert a.status == b.status
    if a.id_ref_a is not None:
        assert np.isclose(a.id_ref_a, b.id_ref_a)
        assert np.isclose(a.iq_ref_a, b.iq_ref_a)
        assert np.isclose(a.if_ref_a, b.if_ref_a)
