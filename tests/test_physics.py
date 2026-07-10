"""Regression tests for torque / voltage / Park conventions."""

import math

import numpy as np

from pipeline.physics import (
    abc_from_dq,
    dq_from_abc,
    electromagnetic_torque,
    rpm_mech_to_we,
    stator_voltage_dq,
    v_max_svpwm,
)


def test_physics_torque_uses_pole_pairs_not_poles():
    id_, iq = -1.0, 2.0
    ld, lq = 0.05, 0.02
    t_pp2 = electromagnetic_torque(id_, iq, ld, lq, pole_pairs=2)
    t_pp4 = electromagnetic_torque(id_, iq, ld, lq, pole_pairs=4)
    # Explicit formula
    expected = 1.5 * 2 * (ld * iq - lq * id_)
    assert abs(float(t_pp2) - expected) < 1e-12
    # Doubling pole_pairs doubles torque; using poles=4 as pole_pairs would be wrong
    assert abs(float(t_pp4) - 2.0 * float(t_pp2)) < 1e-12


def test_physics_voltage_convention():
    id_, iq = -2.0, 3.0
    ld, lq = 0.1, 0.05
    we = 100.0
    rs = 1.5
    v_mag, vd, vq = stator_voltage_dq(id_, iq, ld, lq, we, rs)
    assert abs(float(vd) - (rs * id_ - we * lq)) < 1e-12
    assert abs(float(vq) - (rs * iq + we * ld)) < 1e-12
    assert abs(float(v_mag) - math.hypot(float(vd), float(vq))) < 1e-12


def test_park_roundtrip_theta0():
    # At theta_re=0: ia=Id, ib=-0.5 Id - (√3/2) Iq approximately via transform
    id_, iq = 10.0, 20.0
    ia, ib, ic = abc_from_dq(id_, iq, 0.0)
    assert abs(ia - id_) < 1e-12
    assert abs(ia + ib + ic) < 1e-9
    # Recover d (q may need full 3-phase; Park uses 2/3)
    pd, pq = dq_from_abc(ia, ib, ic, 0.0)
    assert abs(pd - id_) < 1e-9
    assert abs(pq - iq) < 1e-9


def test_park_matches_aedt_export_style():
    # Golden: pure q current at theta=0
    # ia = 0; ib = +√3/2; ic = -√3/2  (matches pipeline/AEDT abc_from_dq)
    ia, ib, ic = abc_from_dq(0.0, 1.0, 0.0)
    assert abs(ia) < 1e-12
    assert abs(ib - math.sqrt(3) / 2.0) < 1e-12
    assert abs(ic + math.sqrt(3) / 2.0) < 1e-12


def test_rpm_and_svpwm():
    we = rpm_mech_to_we(1800.0, 2)
    # 1800 rpm * 2pp = 3600 elec rpm = 377 rad/s approx
    assert abs(we - (1800 / 60.0) * 2 * math.pi * 2) < 1e-12
    assert abs(v_max_svpwm(311.0) - 311.0 / math.sqrt(3.0)) < 1e-12


def test_flux_scale_applied_once_in_torque():
    """Torque with scaled flux equals scale * torque(unscaled) for linear T(Phi)."""
    id_, iq = 0.0, 4.0
    ld_raw, lq_raw = 0.01, 0.0
    scale = 11.86
    t_raw = float(electromagnetic_torque(id_, iq, ld_raw, lq_raw, 2))
    t_scaled = float(electromagnetic_torque(id_, iq, ld_raw * scale, lq_raw * scale, 2))
    assert abs(t_scaled - scale * t_raw) < 1e-12
