"""Create an evidence-only Maxwell EESM qualification report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import cast


EXPECTED_PURPOSES = {
    "field_only", "q_current", "negative_d", "combined_rated",
    "saturation_neighborhood", "q_sign_negative", "d_sign_positive",
}
FEM_TO_CONTROLLER_TORQUE_SIGN = -1.0
TORQUE_CLOSURE_TOLERANCE_NM = 1.1
FIELD_EXCITATION_FLOOR_WB = 1e-6


def _check(status: str, reason: str) -> dict[str, str]:
    return {"status": status, "reason": reason}


def qualify_results(canonical_path: Path, report_path: Path) -> dict[str, object]:
    with Path(canonical_path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    converged = [row for row in rows if row["converged"].lower() == "true"]
    any_failed = any(row["solver_status"] == "failed" for row in rows)
    by_purpose = {row["qualification_purpose"]: row for row in rows}
    pilot_complete = set(by_purpose) == EXPECTED_PURPOSES
    statuses_understood = all(row["solver_status"] in {"converged", "failed"} for row in rows)
    finite_flux = all(math.isfinite(float(row[name])) for row in converged for name in ("lambda_d_wb", "lambda_q_wb"))
    try:
        pole_pair_values = [int(row["pole_pairs"]) for row in rows]
        pole_pairs_ok = bool(pole_pair_values) and len(set(pole_pair_values)) == 1 and pole_pair_values[0] > 0
    except (KeyError, TypeError, ValueError):
        pole_pairs_ok = False
    expected_units = {"id": "A", "iq": "A", "if": "A", "flux_d": "Wb",
                      "flux_q": "Wb", "torque": "N*m", "rotor_position": "deg",
                      "mesh_elements": "count", "adaptive_passes": "count",
                      "pole_pairs": "count"}
    unit_evidence = [json.loads(row["raw_units"]) for row in rows]
    units_ok = bool(unit_evidence) and all(item == expected_units for item in unit_evidence)
    field_row = by_purpose.get("field_only")
    excitation_ready = bool(
        pilot_complete and field_row and field_row["converged"].lower() == "true"
    )
    excitation_magnitude = math.hypot(
        float(field_row["lambda_d_wb"]), float(field_row["lambda_q_wb"])
    ) if excitation_ready and field_row else 0.0
    excitation_pass = excitation_ready and excitation_magnitude > FIELD_EXCITATION_FLOOR_WB
    sign_rows = [by_purpose.get(name) for name in (
        "q_current", "negative_d", "q_sign_negative", "d_sign_positive"
    )]
    signs_ready = all(row and row["converged"].lower() == "true" for row in sign_rows)
    complete_sign_rows = cast(list[dict[str, str]], sign_rows)
    signs_pass = signs_ready and (
        float(complete_sign_rows[0]["lambda_q_wb"]) * float(complete_sign_rows[2]["lambda_q_wb"]) < 0
        and float(complete_sign_rows[1]["lambda_d_wb"]) < float(complete_sign_rows[3]["lambda_d_wb"])
    )
    metadata_complete = all(row["mesh_elements"] and row["adaptive_passes"] for row in converged)
    torque_errors: list[float] = []
    if pilot_complete and len(converged) == len(rows):
        for row in rows:
            pole_pairs = int(row["pole_pairs"])
            torque_from_flux = 1.5 * pole_pairs * (
                float(row["lambda_d_wb"]) * float(row["iq_a"])
                - float(row["lambda_q_wb"]) * float(row["id_a"])
            )
            torque_controller = (
                FEM_TO_CONTROLLER_TORQUE_SIGN * float(row["torque_fem_nm"])
            )
            torque_errors.append(abs(torque_controller - torque_from_flux))
    torque_ready = len(torque_errors) == len(EXPECTED_PURPOSES)
    max_torque_error = max(torque_errors) if torque_errors else None
    torque_pass = bool(
        torque_ready and max_torque_error is not None
        and max_torque_error <= TORQUE_CLOSURE_TOLERANCE_NM
    )
    checks = {
        "pilot_contract": _check("pass" if pilot_complete else "inconclusive", "Exactly the seven energized FEM qualification purposes are required; the source-free origin is an analytic invariant because AEDT Student crashes on that redundant solve."),
        "excitation": _check("pass" if excitation_pass else ("fail" if excitation_ready else "inconclusive"), "The converged field_only row must have flux-vector magnitude above the frozen 1e-6 Wb numerical floor; the no-current origin is analytically zero."),
        "dq_signs": _check("pass" if signs_pass else ("fail" if signs_ready else "inconclusive"), "Named q_current/q_sign_negative fluxes must have opposite signs and negative_d d-flux must be below d_sign_positive."),
        "units": _check("pass" if units_ok else "fail", "Compared raw unit evidence with the declared A, Wb, N*m, deg, and count contract."),
        "pole_pairs": _check("pass" if pole_pairs_ok else "fail", "Exactly one consistent positive integer pole-pair value is required."),
        "flux_channels": _check("pass" if finite_flux and converged else "fail", "All converged pilot rows require finite d- and q-axis flux."),
        "convergence": _check("pass" if pilot_complete and statuses_understood and len(converged) == len(rows) else ("fail" if any_failed or pilot_complete else "inconclusive"), "Every point in the seven-point energized pilot must have an understood status and converge; any explicit failed row fails closed even before the pilot is complete."),
        "torque_closure": _check("pass" if torque_pass else ("fail" if torque_ready else "inconclusive"), "Task 8 freezes controller torque = -Torque_FEM for the RMxprt rotor orientation and requires max absolute residual <= 1.1 N*m against 1.5*p*(lambda_d*Iq-lambda_q*Id)."),
        "mesh_adaptive_evidence": _check("pass" if metadata_complete else "inconclusive", "Converged rows must carry measured mesh-element and adaptive-pass evidence."),
    }
    overall = "fail" if any(item["status"] == "fail" for item in checks.values()) else "inconclusive"
    if all(item["status"] == "pass" for item in checks.values()):
        overall = "pass"
    report = {
        "overall_status": overall,
        "pilot_points": len(rows),
        "converged_points": len(converged),
        "torque_translation": {
            "controller_torque_from_fem_sign": FEM_TO_CONTROLLER_TORQUE_SIGN,
            "closure_tolerance_nm": TORQUE_CLOSURE_TOLERANCE_NM,
            "max_observed_error_nm": max_torque_error,
        },
        "checks": checks,
    }
    Path(report_path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("canonical", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = qualify_results(args.canonical, args.report)
    if report["overall_status"] != "pass":
        sys.exit(1)


if __name__ == "__main__":
    main()
