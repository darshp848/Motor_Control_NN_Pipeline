"""Per-operating-point extraction: currents in, (lambda_d, lambda_q, T) out.

Conventions, all from config.py and all load-bearing
----------------------------------------------------
  - Commanded (id, iq) are TERMINAL amps. With 4 parallel stator branches,
    the modelled sector is ONE branch, so it is driven with I/4. The field
    winding has 1 branch, so its commanded current is the actual one.
  - Amplitude-invariant Park, identical in form to
    eesm/aedt/flux_extraction_v2.py so the two paths stay comparable.
  - Flux multiplier x1: FEMM's circuit flux linkage is already the terminal
    (full-machine) phase flux linkage. Torque multiplier x4: the block
    integral covers one sector.

The x4 that is NOT there
------------------------
The dq torque identity T = 1.5 * p * (lambda_d * iq - lambda_q * id) applied
to TERMINAL quantities is ALREADY the full-machine torque. It gets no sector
multiplier. compare_flux_methods.py double-counted a x4 here (fixed
2026-07-22); test_femm_extract.py pins the arithmetic against a hand-computed
literal so the bug cannot come back.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple

from .config import (
    DEFAULT_CONFIG,
    FIELD_CIRCUIT,
    FemmConfig,
    PHASE_CIRCUITS,
    field_branch_current,
    stator_branch_current,
)

_TWO_THIRDS_PI = 2.0 * math.pi / 3.0


# ---------------------------------------------------------------------------
# Park transforms (pure, no FEMM)
# ---------------------------------------------------------------------------


def dq_from_abc(value_a: float, value_b: float, value_c: float,
                theta_electrical_deg: float) -> Tuple[float, float]:
    """Amplitude-invariant Park, forward."""
    th = math.radians(theta_electrical_deg)
    d = (2.0 / 3.0) * (
        value_a * math.cos(th)
        + value_b * math.cos(th - _TWO_THIRDS_PI)
        + value_c * math.cos(th + _TWO_THIRDS_PI)
    )
    q = (2.0 / 3.0) * (
        -value_a * math.sin(th)
        - value_b * math.sin(th - _TWO_THIRDS_PI)
        - value_c * math.sin(th + _TWO_THIRDS_PI)
    )
    return d, q


def abc_from_dq(value_d: float, value_q: float,
                theta_electrical_deg: float) -> Tuple[float, float, float]:
    """Amplitude-invariant Park, inverse. MUST use the same angle as forward."""
    th = math.radians(theta_electrical_deg)
    return tuple(  # type: ignore[return-value]
        value_d * math.cos(angle) - value_q * math.sin(angle)
        for angle in (th, th - _TWO_THIRDS_PI, th + _TWO_THIRDS_PI)
    )


def zero_sequence_ratio(value_a: float, value_b: float, value_c: float) -> float:
    """Inline health check.

    Scope warning carried over from eesm/aedt/flux_extraction_v2.py NOTE 5:
    stator zero-sequence is REAL PHYSICS on this machine (0.06-0.81 under
    stator excitation) and does not corrupt the dq fundamental. Apply the
    0.05 threshold to rotor/field excitations only.
    """
    zero = (value_a + value_b + value_c) / 3.0
    d, q = dq_from_abc(value_a, value_b, value_c, 0.0)
    magnitude = math.hypot(d, q)
    if magnitude < 1e-15:
        return 0.0
    return abs(zero) / magnitude


def electrical_angle_deg(rotor_angle_deg: float = 0.0,
                         cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Park reference angle for a given mechanical rotor position.

    theta_e = d_axis_offset + pole_pairs * rotor_angle_mech. Supports the
    sliding-band rotor sweep without changing the winding definition.
    """
    return (cfg.extraction.d_axis_electrical_deg
            + cfg.machine.pole_pairs * rotor_angle_deg)


# ---------------------------------------------------------------------------
# Torque identity
# ---------------------------------------------------------------------------


def torque_from_dq(lambda_d: float, lambda_q: float, id_a: float, iq_a: float,
                   cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """T = 1.5 * p * (lambda_d * iq - lambda_q * id), FULL MACHINE.

    No sector multiplier. See the module docstring.
    """
    return (cfg.extraction.torque_identity_constant
            * cfg.machine.pole_pairs
            * (lambda_d * iq_a - lambda_q * id_a))


def full_machine_torque(sector_torque_nm: float,
                        cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Sector block-integral torque -> full-machine torque (x4)."""
    return sector_torque_nm * cfg.extraction.torque_sector_multiplier


def terminal_flux(circuit_flux_wb: float,
                  cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Circuit flux linkage -> terminal flux linkage (x1)."""
    return circuit_flux_wb * cfg.extraction.flux_multiplier


# ---------------------------------------------------------------------------
# Current injection
# ---------------------------------------------------------------------------


def branch_currents(id_a: float, iq_a: float, if_a: float,
                    theta_electrical_deg: float,
                    cfg: FemmConfig = DEFAULT_CONFIG) -> Dict[str, float]:
    """Terminal (id, iq, if) -> the current each modelled circuit carries."""
    terminal_abc = abc_from_dq(id_a, iq_a, theta_electrical_deg)
    currents = {
        name: stator_branch_current(value, cfg)
        for name, value in zip(PHASE_CIRCUITS, terminal_abc)
    }
    currents[FIELD_CIRCUIT] = field_branch_current(if_a, cfg)
    return currents


def set_currents(handle: Any, id_a: float, iq_a: float, if_a: float,
                 theta_electrical_deg: float,
                 cfg: FemmConfig = DEFAULT_CONFIG) -> Dict[str, float]:
    """Apply the branch currents to the FEMM circuits."""
    currents = branch_currents(id_a, iq_a, if_a, theta_electrical_deg, cfg)
    for name, value in currents.items():
        handle.mi_setcurrent(name, value)
    return currents


# ---------------------------------------------------------------------------
# Readback
# ---------------------------------------------------------------------------


def read_circuit_flux(handle: Any, circuit: str) -> float:
    """mo_getcircuitproperties returns (current, voltage, flux_linkage)."""
    properties = handle.mo_getcircuitproperties(circuit)
    values = list(properties)
    if len(values) < 3:
        raise RuntimeError(
            "mo_getcircuitproperties(%r) returned %d values, expected 3"
            % (circuit, len(values))
        )
    return float(values[2])


def read_sector_torque(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Weighted stress tensor torque over the rotating groups, one sector."""
    handle.mo_clearblock()
    for group in cfg.api.torque_groups:
        handle.mo_groupselectblock(group)
    torque = float(handle.mo_blockintegral(cfg.api.block_integral_torque))
    handle.mo_clearblock()
    return torque


def read_mesh_elements(handle: Any) -> Optional[int]:
    """Element count, for provenance. None if FEMM will not report it."""
    try:
        return int(handle.mo_numelements())
    except BaseException:
        return None


# ---------------------------------------------------------------------------
# One operating point
# ---------------------------------------------------------------------------


def extract_point(handle: Any, id_a: float, iq_a: float, if_a: float,
                  rotor_angle_deg: float = 0.0,
                  cfg: FemmConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """Solve one operating point and return everything about it.

    Returns a dict carrying the dq result, the torque pair and its residual,
    the raw per-phase quantities, and provenance (mesh count, solver status,
    the exact injected currents, the Park angle actually used).
    """
    theta = electrical_angle_deg(rotor_angle_deg, cfg)
    applied = set_currents(handle, id_a, iq_a, if_a, theta, cfg)

    solver_status = "converged"
    converged = True
    try:
        handle.mi_analyze(1)  # 1 = non-verbose
        handle.mi_loadsolution()
    except BaseException as exc:
        # Fail closed: report the failure, never a partial number.
        return {
            "id_a": id_a,
            "iq_a": iq_a,
            "if_a": if_a,
            "rotor_angle_deg": rotor_angle_deg,
            "theta_electrical_deg": theta,
            "applied_branch_currents_a": applied,
            "lambda_d_wb": None,
            "lambda_q_wb": None,
            "solver_status": "failed: %s: %s" % (type(exc).__name__, exc),
            "converged": False,
            "mesh_elements": None,
        }

    flux_abc = tuple(
        terminal_flux(read_circuit_flux(handle, name), cfg)
        for name in PHASE_CIRCUITS
    )
    lambda_field = read_circuit_flux(handle, FIELD_CIRCUIT)

    lambda_d, lambda_q = dq_from_abc(flux_abc[0], flux_abc[1], flux_abc[2], theta)

    sector_torque = read_sector_torque(handle, cfg)
    torque_fem = full_machine_torque(sector_torque, cfg)
    torque_identity = torque_from_dq(lambda_d, lambda_q, id_a, iq_a, cfg)
    residual = torque_fem - torque_identity
    scale = max(abs(torque_fem), abs(torque_identity))
    residual_rel = abs(residual) / scale if scale > 0.0 else 0.0

    return {
        "id_a": id_a,
        "iq_a": iq_a,
        "if_a": if_a,
        "rotor_angle_deg": rotor_angle_deg,
        "theta_electrical_deg": theta,
        "applied_branch_currents_a": applied,
        "lambda_a_wb": flux_abc[0],
        "lambda_b_wb": flux_abc[1],
        "lambda_c_wb": flux_abc[2],
        "lambda_d_wb": lambda_d,
        "lambda_q_wb": lambda_q,
        # NOT 'lambda_f_wb': eesm/schemas/eesm_point.schema.json sets that
        # property to `false`, i.e. FORBIDDEN. A row carrying it fails
        # validation outright. test_femm_campaign.py pins this.
        "lambda_field_wb": lambda_field,
        "zero_sequence_ratio": zero_sequence_ratio(*flux_abc),
        "torque_sector_nm": sector_torque,
        "torque_fem_nm": torque_fem,
        "torque_identity_nm": torque_identity,
        "torque_residual_nm": residual,
        "torque_residual_rel": residual_rel,
        "torque_residual_suspect": int(
            residual_rel > cfg.extraction.torque_residual_report_threshold),
        "flux_multiplier": cfg.extraction.flux_multiplier,
        "torque_sector_multiplier": cfg.extraction.torque_sector_multiplier,
        "pole_pairs": cfg.machine.pole_pairs,
        "model_depth_m": cfg.machine.model_depth_m,
        "mesh_elements": read_mesh_elements(handle),
        "solver_status": solver_status,
        "converged": converged,
    }
