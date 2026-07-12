"""Create an evidence-only Maxwell EESM qualification report."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import cast


def _check(status: str, reason: str) -> dict[str, str]:
    return {"status": status, "reason": reason}


def qualify_results(canonical_path: Path, report_path: Path) -> dict[str, object]:
    with Path(canonical_path).open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    converged = [row for row in rows if row["converged"].lower() == "true"]
    by_purpose = {row["qualification_purpose"]: row for row in rows}
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
    field_rows = [by_purpose.get(name) for name in ("zero_current", "field_only")]
    excitation_ready = all(row and row["converged"].lower() == "true" for row in field_rows)
    complete_field_rows = cast(list[dict[str, str]], field_rows)
    excitation_pass = excitation_ready and float(complete_field_rows[1]["lambda_d_wb"]) > float(complete_field_rows[0]["lambda_d_wb"])
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
    checks = {
        "excitation": _check("pass" if excitation_pass else ("fail" if excitation_ready else "inconclusive"), "Named zero_current and field_only rows must converge and field excitation must strictly increase d-axis flux."),
        "dq_signs": _check("pass" if signs_pass else ("fail" if signs_ready else "inconclusive"), "Named q_current/q_sign_negative fluxes must have opposite signs and negative_d d-flux must be below d_sign_positive."),
        "units": _check("pass" if units_ok else "fail", "Compared raw unit evidence with the declared A, Wb, N*m, deg, and count contract."),
        "pole_pairs": _check("pass" if pole_pairs_ok else "fail", "Exactly one consistent positive integer pole-pair value is required."),
        "flux_channels": _check("pass" if finite_flux and converged else "fail", "All converged pilot rows require finite d- and q-axis flux."),
        "convergence": _check("pass" if statuses_understood and len(converged) == len(rows) else "fail", "Every pilot solve must have an understood status and converge."),
        "torque_closure": _check("inconclusive", "Task 9 must define the torque translation and evidence-based tolerance; current LUT audit is unchanged."),
        "mesh_adaptive_evidence": _check("pass" if metadata_complete else "inconclusive", "Converged rows must carry measured mesh-element and adaptive-pass evidence."),
    }
    overall = "fail" if any(item["status"] == "fail" for item in checks.values()) else "inconclusive"
    if all(item["status"] == "pass" for item in checks.values()):
        overall = "pass"
    report = {"overall_status": overall, "pilot_points": len(rows), "converged_points": len(converged), "checks": checks}
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
