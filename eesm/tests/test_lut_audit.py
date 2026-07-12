"""Prospective EESM LUT-audit boundary."""

from __future__ import annotations

import pytest

from lut.audit import build_audit_commands, join_fem_audit
from scheduler.copper_loss_scheduler import SchedulerLimits


def test_infeasible_commands_never_request_fem() -> None:
    commands = build_audit_commands(
        [
            {
                "omega_rpm": 1000.0,
                "torque_request_nm": 10.0,
                "status": "infeasible",
                "id_ref_a": None,
                "iq_ref_a": None,
                "if_ref_a": None,
            }
        ]
    )

    assert commands[0]["needs_fem"] is False
    assert commands[0]["audit_status"] == "not_auditable_infeasible"


def test_fem_join_preserves_commands_and_recomputes_shared_physics() -> None:
    commands = build_audit_commands(
        [
            {
                "omega_rpm": 1000.0,
                "torque_request_nm": 10.0,
                "status": "feasible",
                "id_ref_a": -2.0,
                "iq_ref_a": 3.0,
                "if_ref_a": 1.0,
            },
            {
                "omega_rpm": 2000.0,
                "torque_request_nm": 20.0,
                "status": "feasible",
                "id_ref_a": -4.0,
                "iq_ref_a": 5.0,
                "if_ref_a": 2.0,
            },
        ]
    )
    fem_record = {
        "point_id": "audit-1",
        "role": "scheduler_audit",
        "source": "maxwell",
        "region": "interior",
        "id_a": -2.0,
        "iq_a": 3.0,
        "if_a": 1.0,
        "lambda_d_wb": 0.02,
        "lambda_q_wb": 0.01,
        "torque_nm": 0.15,
        "solver_status": "success",
        "converged": True,
        "provenance_id": "qualification-1",
        "pole_pairs": 2,
    }

    report = join_fem_audit(commands, [fem_record], SchedulerLimits())

    assert [row["audit_status"] for row in report["rows"]] == [
        "audited",
        "missing_fem",
    ]
    assert report["rows"][0]["fem_torque_recomputed_nm"] == pytest.approx(0.24)
    assert report["summary"] == {"audited": 1, "missing_fem": 1}
