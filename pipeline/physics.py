"""Shared electromagnetic transforms and torque/voltage equations.

Conventions (frozen for IPM Stage 0):
  - Currents are peak phase amplitudes in the dq frame (A).
  - Park angle theta_re = 0 aligns d-axis with Phase A (matches FEM export).
  - Torque uses pole_pairs P (not pole count):
        T = (3/2) * P * (lambda_d * Iq - lambda_q * Id)
  - Steady-state stator voltage (motor convention, electrical rad/s):
        Vd = Rs * Id - omega_e * lambda_q
        Vq = Rs * Iq + omega_e * lambda_d
  - SVPWM phase peak limit: V_max = V_dc / sqrt(3)
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple, Union

import numpy as np

ArrayLike = Union[float, Sequence[float], np.ndarray]


def abc_from_dq(
    id_value: float, iq_value: float, theta_re: float = 0.0
) -> Tuple[float, float, float]:
    """Inverse Park (amplitude-invariant) at electrical angle theta_re."""
    ia = math.cos(theta_re) * id_value - math.sin(theta_re) * iq_value
    ib = (
        math.cos(theta_re - 2.0 * math.pi / 3.0) * id_value
        - math.sin(theta_re - 2.0 * math.pi / 3.0) * iq_value
    )
    ic = -(ia + ib)
    return ia, ib, ic


def dq_from_abc(
    phi_a: float, phi_b: float, phi_c: float, theta_re: float = 0.0
) -> Tuple[float, float]:
    """Park transform (2/3 factor) matching AEDT export post-processing."""
    phi_d = (2.0 / 3.0) * (
        phi_a * math.cos(theta_re)
        + phi_b * math.cos(theta_re - 2.0 * math.pi / 3.0)
        + phi_c * math.cos(theta_re + 2.0 * math.pi / 3.0)
    )
    phi_q = (2.0 / 3.0) * (
        -phi_a * math.sin(theta_re)
        - phi_b * math.sin(theta_re - 2.0 * math.pi / 3.0)
        - phi_c * math.sin(theta_re + 2.0 * math.pi / 3.0)
    )
    return phi_d, phi_q


def electromagnetic_torque(
    id_: ArrayLike,
    iq: ArrayLike,
    lambda_d: ArrayLike,
    lambda_q: ArrayLike,
    pole_pairs: int,
) -> np.ndarray:
    """IPM electromagnetic torque. pole_pairs is P, not pole count."""
    id_a = np.asarray(id_, dtype=np.float64)
    iq_a = np.asarray(iq, dtype=np.float64)
    ld = np.asarray(lambda_d, dtype=np.float64)
    lq = np.asarray(lambda_q, dtype=np.float64)
    p = float(pole_pairs)
    return 1.5 * p * (ld * iq_a - lq * id_a)


def stator_voltage_dq(
    id_: ArrayLike,
    iq: ArrayLike,
    lambda_d: ArrayLike,
    lambda_q: ArrayLike,
    omega_e: float,
    rs: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (|V|, Vd, Vq) for each sample."""
    id_a = np.asarray(id_, dtype=np.float64)
    iq_a = np.asarray(iq, dtype=np.float64)
    ld = np.asarray(lambda_d, dtype=np.float64)
    lq = np.asarray(lambda_q, dtype=np.float64)
    vd = rs * id_a - omega_e * lq
    vq = rs * iq_a + omega_e * ld
    v_mag = np.sqrt(vd * vd + vq * vq)
    return v_mag, vd, vq


def rpm_mech_to_we(rpm_mech: float, pole_pairs: int) -> float:
    """Mechanical rpm -> electrical angular speed (rad/s)."""
    return (float(rpm_mech) / 60.0) * 2.0 * math.pi * float(pole_pairs)


def v_max_svpwm(vdc: float) -> float:
    """SVPWM maximum phase-peak voltage magnitude."""
    return float(vdc) / math.sqrt(3.0)
