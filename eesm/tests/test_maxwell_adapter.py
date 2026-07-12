"""Offline contract tests for the Maxwell EESM adapter."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

AEDT_DIR = Path(__file__).parents[1] / "aedt"
sys.path.insert(0, str(AEDT_DIR))

from normalize_eesm_results import AdapterError, normalize_results  # noqa: E402
from qualify_eesm_project import qualify_results  # noqa: E402


RAW_FIELDS = [
    "PointName",
    "Id [A]",
    "Iq [A]",
    "If [A]",
    "Flux_d [Wb]",
    "Flux_q [Wb]",
    "Torque [N*m]",
    "Project",
    "Design",
    "Setup",
    "RotorPosition [deg]",
    "MeshElements [count]",
    "AdaptivePasses [count]",
    "SolverStatus",
    "SolverMessage",
    "PolePairs [count]",
]


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.parametrize(
    ("variant", "expected"),
    [
        ("valid", "inconclusive"),
        ("solver_failure", "fail"),
        ("bad_units", AdapterError),
        ("duplicate_missing", AdapterError),
    ],
)
def test_adapter_contract(tmp_path: Path, variant: str, expected: object) -> None:
    points = [
        {"PointName": "zero", "region": "interior", "Id [A]": 0, "Iq [A]": 0, "If [A]": 0, "Purpose": "zero_current"},
        {"PointName": "q_sign", "region": "interior", "Id [A]": 0, "Iq [A]": 10, "If [A]": 2, "Purpose": "q_sign"},
    ]
    rows = [
        {
            "PointName": point["PointName"], "Id [A]": point["Id [A]"],
            "Iq [A]": point["Iq [A]"], "If [A]": point["If [A]"],
            "Flux_d [Wb]": 0.01, "Flux_q [Wb]": 0.02,
            "Torque [N*m]": 1.5, "Project": "motor", "Design": "EESM",
            "Setup": "Setup1", "RotorPosition [deg]": 0,
            "MeshElements [count]": 1000, "AdaptivePasses [count]": 3,
            "SolverStatus": "converged", "SolverMessage": "Normal completion",
            "PolePairs [count]": 4,
        }
        for point in points
    ]
    fields = list(RAW_FIELDS)
    if variant == "solver_failure":
        rows[1]["SolverStatus"] = "failed"
        rows[1]["SolverMessage"] = "solve failed"
        rows[1]["MeshElements [count]"] = ""
        rows[1]["AdaptivePasses [count]"] = ""
        rows[1]["Torque [N*m]"] = ""
    elif variant == "bad_units":
        fields[fields.index("Flux_d [Wb]")] = "Flux_d [mWb]"
        for row in rows:
            row["Flux_d [mWb]"] = row.pop("Flux_d [Wb]")
    elif variant == "duplicate_missing":
        rows[1] = dict(rows[0])

    points_path, raw_path = tmp_path / "points.csv", tmp_path / "raw.csv"
    canonical_path, report_path = tmp_path / "canonical.csv", tmp_path / "report.json"
    _write_csv(points_path, list(points[0]), points)
    _write_csv(raw_path, fields, rows)

    if expected is AdapterError:
        with pytest.raises(AdapterError):
            normalize_results(raw_path, points_path, canonical_path)
        return

    canonical = normalize_results(raw_path, points_path, canonical_path)
    report = qualify_results(canonical_path, report_path)
    assert len(canonical) == 2
    assert canonical[0]["role"] == "reference"
    assert canonical[0]["torque_fem_nm"] == 1.5
    assert json.loads(canonical[0]["raw_units"])["flux_d"] == "Wb"
    assert report["checks"]["pole_pairs"]["status"] == "pass"
    exporter = (AEDT_DIR / "export_eesm_points.py").read_text(encoding="utf-8")
    assert "Refusing resume: progress contains failed row" in exporter
    assert "SMOKE_APPROVED = False" in exporter
    assert "if isinstance(value, dict):" in exporter
    qualifier = (AEDT_DIR / "qualify_eesm_project.py").read_text(encoding="utf-8")
    assert '"q_sign_negative", "d_sign_positive"' in qualifier
    if variant == "solver_failure":
        assert canonical[1]["mesh_elements"] is None
        assert canonical[1]["adaptive_passes"] is None
    assert report["overall_status"] == expected
    assert report["checks"]["torque_closure"]["status"] == "inconclusive"
    assert "Task 9" in report["checks"]["torque_closure"]["reason"]
    assert json.loads(report_path.read_text(encoding="utf-8")) == report
