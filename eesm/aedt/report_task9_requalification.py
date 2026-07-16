"""Build the fail-closed Task 9 torque requalification report."""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path


TORQUE_CLOSURE_TOLERANCE_NM = 1.1
FEM_TO_CONTROLLER_TORQUE_SIGN = -1.0
COENERGY_STEP_AGREEMENT_TOLERANCE_NM = 1.1


def _finite(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite diagnostic value")
    return number


def build_report(points_path: Path, progress_path: Path, output_path: Path) -> dict[str, object]:
    with points_path.open(newline="", encoding="utf-8") as stream:
        points = list(csv.DictReader(stream))
    with progress_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    expected = {row["point_id"] for row in points}
    actual = {row["PointID"] for row in rows}
    complete = len(rows) == 10 and actual == expected and all(row["SolverStatus"] == "converged" for row in rows)

    comparisons = {
        "virtual_vs_coenergy": [],
        "phase_flux_vs_coenergy": [],
        "virtual_vs_phase_flux": [],
        "coenergy_step_agreement": [],
    }
    if complete:
        for row in rows:
            virtual = _finite(row["TorqueController [N*m]"])
            phase_flux = _finite(row["TorquePhaseFlux [N*m]"])
            coenergy = _finite(row["TorqueCoenergy [N*m]"])
            coarse = _finite(row["TorqueCoenergyCoarse [N*m]"])
            comparisons["virtual_vs_coenergy"].append(abs(virtual - coenergy))
            comparisons["phase_flux_vs_coenergy"].append(abs(phase_flux - coenergy))
            comparisons["virtual_vs_phase_flux"].append(abs(virtual - phase_flux))
            comparisons["coenergy_step_agreement"].append(abs(coenergy - coarse))

    checks = {}
    for name, values in comparisons.items():
        tolerance = COENERGY_STEP_AGREEMENT_TOLERANCE_NM if name == "coenergy_step_agreement" else TORQUE_CLOSURE_TOLERANCE_NM
        maximum = max(values) if values else None
        checks[name] = {
            "status": "pass" if complete and maximum is not None and maximum <= tolerance else "fail",
            "maximum_abs_error_nm": maximum,
            "tolerance_nm": tolerance,
        }
    passed = complete and all(check["status"] == "pass" for check in checks.values())
    report = {
        "overall_status": "pass" if passed else "fail",
        "completed_rows": len(rows),
        "expected_rows": 10,
        "checks": checks,
        "claims": {
            "new_task9_campaign_authorized": False,
            "task_10_complete": False,
            "note": "A passing r2 diagnostic supports root-cause selection only; any correction requires a new r3 freeze.",
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2] / "out" / "eesm" / "task9_requalification_r2"
    print(json.dumps(build_report(root / "frozen_points.csv", root / "raw" / "diagnostic_progress.csv", root / "requalification_report.json"), indent=2))
