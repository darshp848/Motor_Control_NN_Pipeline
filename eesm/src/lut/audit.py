"""Reference-LUT construction and prospective FEM audit joins."""

from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Mapping

from pipeline.physics import electromagnetic_torque, rpm_mech_to_we, stator_voltage_dq
from scheduler.copper_loss_scheduler import CopperLossScheduler, SchedulerLimits


def build_reference_lut(
    scheduler: CopperLossScheduler,
    commands: Iterable[tuple[float, float]],
) -> list[dict[str, Any]]:
    """Schedule frozen commands while retaining every infeasible result."""
    rows: list[dict[str, Any]] = []
    for omega_rpm, torque_request_nm in commands:
        row = scheduler.schedule(omega_rpm, torque_request_nm).to_dict()
        row["torque_request_nm"] = row.pop("t_ref_nm")
        rows.append(row)
    return rows


def build_audit_commands(
    lut_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Request FEM only for schedulable rows with complete references."""
    commands: list[dict[str, Any]] = []
    for source in lut_rows:
        row = dict(source)
        complete = all(
            row.get(name) is not None
            for name in ("id_ref_a", "iq_ref_a", "if_ref_a")
        )
        schedulable = row.get("status") in {
            "feasible",
            "saturated_to_boundary",
        }
        needs_fem = bool(schedulable and complete)
        commands.append(
            row
            | {
                "needs_fem": needs_fem,
                "audit_status": (
                    "pending" if needs_fem else "not_auditable_infeasible"
                ),
            }
        )
    return commands


def _current_key(values: Iterable[object]) -> tuple[float, float, float]:
    return tuple(round(float(value), 9) for value in values)


def join_fem_audit(
    commands: Iterable[Mapping[str, Any]],
    fem_records: Iterable[Mapping[str, Any]],
    limits: SchedulerLimits | None = None,
) -> dict[str, Any]:
    """Join canonical scheduler-audit rows and recompute torque and voltage."""
    limits = limits or SchedulerLimits()
    by_current: dict[tuple[float, float, float], dict[str, Any]] = {}
    for source in fem_records:
        record = dict(source)
        if record.get("role") != "scheduler_audit":
            raise ValueError("join_fem_audit accepts only scheduler_audit records")
        key = _current_key(record[name] for name in ("id_a", "iq_a", "if_a"))
        if key in by_current:
            raise ValueError(f"duplicate scheduler_audit current triple: {key}")
        by_current[key] = record

    rows: list[dict[str, Any]] = []
    for source in commands:
        row = dict(source)
        if not row.get("needs_fem", False):
            row["audit_status"] = "not_auditable_infeasible"
            rows.append(row)
            continue
        key = _current_key(
            row[name] for name in ("id_ref_a", "iq_ref_a", "if_ref_a")
        )
        record = by_current.get(key)
        if record is None:
            row["audit_status"] = "missing_fem"
            rows.append(row)
            continue
        row.update(
            fem_point_id=record.get("point_id"),
            fem_provenance_id=record.get("provenance_id"),
            fem_solver_status=record.get("solver_status"),
            fem_converged=record.get("converged"),
            fem_lambda_d_wb=record.get("lambda_d_wb"),
            fem_lambda_q_wb=record.get("lambda_q_wb"),
            fem_torque_nm=record.get("torque_nm"),
        )
        usable = (
            record.get("converged") is True
            and record.get("solver_status") == "success"
            and record.get("lambda_d_wb") is not None
            and record.get("lambda_q_wb") is not None
        )
        if not usable:
            row["audit_status"] = "fem_failed"
            rows.append(row)
            continue
        pole_pairs = int(record.get("pole_pairs") or limits.pole_pairs)
        torque = electromagnetic_torque(
            record["id_a"],
            record["iq_a"],
            record["lambda_d_wb"],
            record["lambda_q_wb"],
            pole_pairs,
        )
        voltage, _, _ = stator_voltage_dq(
            record["id_a"],
            record["iq_a"],
            record["lambda_d_wb"],
            record["lambda_q_wb"],
            rpm_mech_to_we(row["omega_rpm"], pole_pairs),
            limits.rs_ohm,
        )
        row.update(
            audit_status="audited",
            fem_torque_recomputed_nm=float(torque),
            fem_v_mag_recomputed_v=float(voltage),
            fem_torque_export_delta_nm=(
                None
                if record.get("torque_nm") is None
                else float(record["torque_nm"] - torque)
            ),
        )
        rows.append(row)

    return {
        "rows": rows,
        "summary": dict(Counter(row["audit_status"] for row in rows)),
    }
