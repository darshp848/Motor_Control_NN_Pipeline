"""Compact evaluation of synthetic-map software and physics invariants."""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from scheduler.copper_loss_scheduler import (
    electromagnetic_torque_eesm,
    rpm_mech_to_we,
    stator_voltage_eesm,
)


def evaluate_invariants(
    map_model: Any,
    points: Mapping[str, Any],
    machine: Mapping[str, Any],
) -> dict:
    """Evaluate deterministic internal invariants on a supplied point set."""
    id_a = np.asarray(points["id_a"], dtype=np.float64).ravel()
    iq_a = np.asarray(points["iq_a"], dtype=np.float64).ravel()
    if_a = np.asarray(points["if_a"], dtype=np.float64).ravel()
    if not (id_a.size == iq_a.size == if_a.size):
        raise ValueError("point current arrays must have matching lengths")

    ld, lq = map_model.flux(id_a, iq_a, if_a)
    ld_repeat, lq_repeat = map_model.flux(id_a, iq_a, if_a)
    ld = np.asarray(ld, dtype=np.float64).ravel()
    lq = np.asarray(lq, dtype=np.float64).ravel()

    field_comparisons = []
    for i in range(id_a.size):
        same_currents = (id_a == id_a[i]) & (iq_a == iq_a[i])
        higher_field = same_currents & (if_a > if_a[i])
        if np.any(higher_field):
            field_comparisons.extend((ld[higher_field] > ld[i]).tolist())
    field_influence = bool(field_comparisons) and all(field_comparisons)

    pole_pairs = int(machine["pole_pairs"])
    torque = electromagnetic_torque_eesm(id_a, iq_a, ld, lq, pole_pairs)
    rpm = np.asarray(points.get("rpm_mech", np.zeros(id_a.size)), dtype=np.float64)
    rpm = np.broadcast_to(rpm, id_a.shape)
    omega_e = np.array([rpm_mech_to_we(value, pole_pairs) for value in rpm])
    _, _, voltage = stator_voltage_eesm(
        id_a, iq_a, ld, lq, omega_e, float(machine["rs_ohm"])
    )
    current_feasible = (
        np.sqrt(id_a * id_a + iq_a * iq_a)
        <= float(machine["i_s_max_peak_a"]) + 1e-9
    )

    return {
        "finite_flux": bool(np.all(np.isfinite(ld)) and np.all(np.isfinite(lq))),
        "deterministic_repeatability": bool(
            np.array_equal(ld, ld_repeat) and np.array_equal(lq, lq_repeat)
        ),
        "field_current_increases_lambda_d": field_influence,
        "domain_containment": [
            bool(value)
            for value in map_model.is_in_domain(id_a, iq_a, if_a).tolist()
        ],
        "finite_torque": bool(np.all(np.isfinite(torque))),
        "finite_voltage": bool(np.all(np.isfinite(voltage))),
        "current_circle_labels": [
            "feasible" if bool(value) else "infeasible"
            for value in current_feasible.tolist()
        ],
    }
