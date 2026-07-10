"""Copper-loss constrained EESM current scheduler.

Maps:
  (omega, T_ref) -> (id_ref, iq_ref, if_ref)

Objective:
  P_cu = (3/2) Rs (id^2 + iq^2) + Rf if^2

Subject to torque tolerance, Is limit, if min/max, voltage limit, map domain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

from synthetic.synthetic_map import SyntheticEESMMap


def electromagnetic_torque_eesm(
    id_: np.ndarray,
    iq: np.ndarray,
    lambda_d: np.ndarray,
    lambda_q: np.ndarray,
    pole_pairs: int,
) -> np.ndarray:
    """T = (3/2) * P * (lambda_d * iq - lambda_q * id)."""
    p = float(pole_pairs)
    return 1.5 * p * (lambda_d * iq - lambda_q * id_)


def stator_voltage_eesm(
    id_: np.ndarray,
    iq: np.ndarray,
    lambda_d: np.ndarray,
    lambda_q: np.ndarray,
    omega_e: float,
    rs: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """vd, vq, |v| with motor convention."""
    vd = rs * id_ - omega_e * lambda_q
    vq = rs * iq + omega_e * lambda_d
    vmag = np.sqrt(vd * vd + vq * vq)
    return vd, vq, vmag


def copper_loss(
    id_: np.ndarray,
    iq: np.ndarray,
    if_: np.ndarray,
    rs: float,
    rf: float,
) -> np.ndarray:
    """P_cu = (3/2) Rs (id^2 + iq^2) + Rf if^2."""
    return 1.5 * rs * (id_ * id_ + iq * iq) + rf * (if_ * if_)


def rpm_mech_to_we(rpm_mech: float, pole_pairs: int) -> float:
    omega_m = 2.0 * math.pi * float(rpm_mech) / 60.0
    return omega_m * float(pole_pairs)


@dataclass
class SchedulerLimits:
    rs_ohm: float = 0.05
    rf_ohm: float = 8.0
    vdc_v: float = 400.0
    i_s_max_peak_a: float = 120.0
    i_f_min_a: float = 0.0
    i_f_max_a: float = 15.0
    pole_pairs: int = 2
    torque_tolerance_nm: float = 0.5

    @property
    def v_max_phase_peak(self) -> float:
        return float(self.vdc_v) / math.sqrt(3.0)


@dataclass
class SchedulerResult:
    omega_rpm: float
    t_ref_nm: float
    id_ref_a: Optional[float]
    iq_ref_a: Optional[float]
    if_ref_a: Optional[float]
    torque_nm: Optional[float]
    p_cu_w: Optional[float]
    v_mag_v: Optional[float]
    status: str
    message: str = ""


class CopperLossScheduler:
    """Grid + random refine search for min copper loss under constraints."""

    def __init__(
        self,
        flux_map: SyntheticEESMMap,
        limits: Optional[SchedulerLimits] = None,
        n_grid_id: int = 25,
        n_grid_iq: int = 25,
        n_grid_if: int = 12,
        n_random_refine: int = 200,
        seed: int = 0,
    ):
        self.map = flux_map
        self.limits = limits or SchedulerLimits()
        self.n_grid_id = int(n_grid_id)
        self.n_grid_iq = int(n_grid_iq)
        self.n_grid_if = int(n_grid_if)
        self.n_random_refine = int(n_random_refine)
        self.seed = int(seed)

    def _candidate_pool(self, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        d = self.map.domain
        lim = self.limits
        # Restrict stator currents to map domain ∩ Is disk
        id_vals = np.linspace(d.id_min_a, d.id_max_a, self.n_grid_id)
        iq_vals = np.linspace(d.iq_min_a, d.iq_max_a, self.n_grid_iq)
        if_vals = np.linspace(
            max(d.if_min_a, lim.i_f_min_a),
            min(d.if_max_a, lim.i_f_max_a),
            self.n_grid_if,
        )
        ID, IQ, IF = np.meshgrid(id_vals, iq_vals, if_vals, indexing="ij")
        id_g = ID.ravel()
        iq_g = IQ.ravel()
        if_g = IF.ravel()

        # Random refine inside domain box
        n_r = self.n_random_refine
        if n_r > 0:
            u = rng.random((n_r, 3))
            id_r = d.id_min_a + u[:, 0] * (d.id_max_a - d.id_min_a)
            iq_r = d.iq_min_a + u[:, 1] * (d.iq_max_a - d.iq_min_a)
            if_lo = max(d.if_min_a, lim.i_f_min_a)
            if_hi = min(d.if_max_a, lim.i_f_max_a)
            if_r = if_lo + u[:, 2] * (if_hi - if_lo)
            id_a = np.concatenate([id_g, id_r])
            iq_a = np.concatenate([iq_g, iq_r])
            if_a = np.concatenate([if_g, if_r])
        else:
            id_a, iq_a, if_a = id_g, iq_g, if_g
        return id_a, iq_a, if_a

    def schedule(
        self,
        omega_rpm: float,
        t_ref_nm: float,
    ) -> SchedulerResult:
        """Constrained min copper-loss search for one (speed, torque) command."""
        lim = self.limits
        d = self.map.domain
        t_ref = float(t_ref_nm)
        omega_e = rpm_mech_to_we(omega_rpm, lim.pole_pairs)
        v_max = lim.v_max_phase_peak
        tol = float(lim.torque_tolerance_nm)

        # Impossible torque magnitude with empty domain
        if t_ref < 0:
            return SchedulerResult(
                omega_rpm=float(omega_rpm),
                t_ref_nm=t_ref,
                id_ref_a=None,
                iq_ref_a=None,
                if_ref_a=None,
                torque_nm=None,
                p_cu_w=None,
                v_mag_v=None,
                status="infeasible",
                message="negative torque not supported in Stage 1 scaffold",
            )

        rng = np.random.default_rng(self.seed)
        try:
            id_a, iq_a, if_a = self._candidate_pool(rng)
        except Exception as exc:  # pragma: no cover
            return SchedulerResult(
                omega_rpm=float(omega_rpm),
                t_ref_nm=t_ref,
                id_ref_a=None,
                iq_ref_a=None,
                if_ref_a=None,
                torque_nm=None,
                p_cu_w=None,
                v_mag_v=None,
                status="search_failed",
                message=str(exc),
            )

        # Domain
        in_dom = self.map.is_in_domain(id_a, iq_a, if_a)
        # Stator current limit
        is_mag = np.sqrt(id_a * id_a + iq_a * iq_a)
        ok_is = is_mag <= lim.i_s_max_peak_a + 1e-9
        ok_if = (if_a >= lim.i_f_min_a - 1e-9) & (if_a <= lim.i_f_max_a + 1e-9)

        ld, lq = self.map.flux(id_a, iq_a, if_a)
        if not (np.all(np.isfinite(ld)) and np.all(np.isfinite(lq))):
            return SchedulerResult(
                omega_rpm=float(omega_rpm),
                t_ref_nm=t_ref,
                id_ref_a=None,
                iq_ref_a=None,
                if_ref_a=None,
                torque_nm=None,
                p_cu_w=None,
                v_mag_v=None,
                status="search_failed",
                message="non-finite flux from map",
            )

        t_em = electromagnetic_torque_eesm(id_a, iq_a, ld, lq, lim.pole_pairs)
        _, _, vmag = stator_voltage_eesm(
            id_a, iq_a, ld, lq, omega_e, lim.rs_ohm
        )
        pcu = copper_loss(id_a, iq_a, if_a, lim.rs_ohm, lim.rf_ohm)

        ok_v = vmag <= v_max + 1e-9
        ok_t = np.abs(t_em - t_ref) <= tol

        feasible = in_dom & ok_is & ok_if & ok_v & ok_t
        if np.any(feasible):
            idx_pool = np.flatnonzero(feasible)
            best_local = idx_pool[np.argmin(pcu[idx_pool])]
            return SchedulerResult(
                omega_rpm=float(omega_rpm),
                t_ref_nm=t_ref,
                id_ref_a=float(id_a[best_local]),
                iq_ref_a=float(iq_a[best_local]),
                if_ref_a=float(if_a[best_local]),
                torque_nm=float(t_em[best_local]),
                p_cu_w=float(pcu[best_local]),
                v_mag_v=float(vmag[best_local]),
                status="feasible",
                message="min copper loss among feasible candidates",
            )

        # Soft boundary: meet torque + domain + current, allow voltage soft?
        # Prefer torque-feasible points inside domain and current limits.
        soft = in_dom & ok_is & ok_if & ok_t
        if np.any(soft):
            idx_pool = np.flatnonzero(soft)
            # Among torque-ok points, prefer lowest voltage violation then Pcu
            v_viol = np.maximum(0.0, vmag[idx_pool] - v_max)
            order = np.lexsort((pcu[idx_pool], v_viol))
            best_local = idx_pool[order[0]]
            return SchedulerResult(
                omega_rpm=float(omega_rpm),
                t_ref_nm=t_ref,
                id_ref_a=float(id_a[best_local]),
                iq_ref_a=float(iq_a[best_local]),
                if_ref_a=float(if_a[best_local]),
                torque_nm=float(t_em[best_local]),
                p_cu_w=float(pcu[best_local]),
                v_mag_v=float(vmag[best_local]),
                status="saturated_to_boundary",
                message="torque met; voltage or other limit on boundary",
            )

        # No torque match: report infeasible (do not invent fake refs)
        # Check if domain is empty of any valid current points
        basic = in_dom & ok_is & ok_if
        if not np.any(basic):
            return SchedulerResult(
                omega_rpm=float(omega_rpm),
                t_ref_nm=t_ref,
                id_ref_a=None,
                iq_ref_a=None,
                if_ref_a=None,
                torque_nm=None,
                p_cu_w=None,
                v_mag_v=None,
                status="out_of_domain",
                message="no candidates inside map domain and current limits",
            )

        # Max achievable |T| under limits (for message only)
        t_max = float(np.max(np.abs(t_em[basic]))) if np.any(basic) else 0.0
        return SchedulerResult(
            omega_rpm=float(omega_rpm),
            t_ref_nm=t_ref,
            id_ref_a=None,
            iq_ref_a=None,
            if_ref_a=None,
            torque_nm=None,
            p_cu_w=None,
            v_mag_v=None,
            status="infeasible",
            message=(
                f"no candidate within torque tolerance {tol} N.m; "
                f"approx max |T| under limits ~ {t_max:.3f} N.m"
            ),
        )
