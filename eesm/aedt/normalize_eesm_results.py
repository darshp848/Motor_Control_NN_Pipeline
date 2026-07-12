"""Normalize unit-bearing AEDT exports without rewriting the raw evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


RAW_FIELDS = (
    "PointName", "Id [A]", "Iq [A]", "If [A]", "Flux_d [Wb]",
    "Flux_q [Wb]", "Torque [N*m]", "Project", "Design", "Setup",
    "RotorPosition [deg]", "MeshElements [count]", "AdaptivePasses [count]",
    "SolverStatus", "SolverMessage", "PolePairs [count]",
)
CANONICAL_FIELDS = (
    "point_id", "role", "source", "region", "id_a", "iq_a", "if_a",
    "lambda_d_wb", "lambda_q_wb", "solver_status", "converged",
    "provenance_id", "project", "design", "setup", "rotor_position_deg",
    "mesh_elements", "adaptive_passes", "solver_message", "torque_fem_nm",
    "pole_pairs", "qualification_purpose", "raw_units",
)


class AdapterError(ValueError):
    """Raw Maxwell export violates the frozen adapter contract."""


def _read(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        return list(reader.fieldnames or []), list(reader)


def _number(row: dict[str, str], name: str) -> float:
    try:
        value = float(row[name])
    except (KeyError, TypeError, ValueError) as exc:
        raise AdapterError("invalid numeric AEDT field: " + name) from exc
    if not math.isfinite(value):
        raise AdapterError("non-finite AEDT field: " + name)
    return value


def _optional_number(row: dict[str, str], name: str) -> float | None:
    if not row.get(name, "").strip():
        return None
    return _number(row, name)


def _positive_integer(row: dict[str, str], name: str) -> int:
    value = _number(row, name)
    if value <= 0 or not value.is_integer():
        raise AdapterError(name + " must be a positive integer")
    return int(value)


def _point_id(values: tuple[float, float, float]) -> str:
    serialized = "|".join(f"{round(value, 9) or 0.0:.9f}" for value in values)
    return hashlib.sha256(serialized.encode("ascii")).hexdigest()[:16]


def normalize_results(raw_path: Path, points_path: Path, output_path: Path) -> list[dict[str, object]]:
    fields, raw_rows = _read(Path(raw_path))
    missing_fields = set(RAW_FIELDS) - set(fields)
    if missing_fields:
        raise AdapterError("raw AEDT names/units mismatch: " + ", ".join(sorted(missing_fields)))
    _, point_rows = _read(Path(points_path))
    expected = {row["PointName"]: row for row in point_rows}
    if len(expected) != len(point_rows):
        raise AdapterError("duplicate pilot point names")
    observed = [row.get("PointName", "") for row in raw_rows]
    if len(set(observed)) != len(observed) or set(observed) != set(expected):
        raise AdapterError("duplicate or missing pilot result")

    canonical: list[dict[str, object]] = []
    for raw in raw_rows:
        point = expected[raw["PointName"]]
        currents = (
            _number(raw, "Id [A]"),
            _number(raw, "Iq [A]"),
            _number(raw, "If [A]"),
        )
        requested = tuple(float(point[name]) for name in ("Id [A]", "Iq [A]", "If [A]"))
        if currents != requested:
            raise AdapterError("result currents do not match pilot point " + raw["PointName"])
        status = raw["SolverStatus"].strip().lower()
        converged = status == "converged"
        canonical.append({
            "point_id": _point_id(currents), "role": "reference", "source": "maxwell_aedt",
            "region": point["region"], "id_a": currents[0], "iq_a": currents[1], "if_a": currents[2],
            "lambda_d_wb": _number(raw, "Flux_d [Wb]") if converged else None,
            "lambda_q_wb": _number(raw, "Flux_q [Wb]") if converged else None,
            "solver_status": status, "converged": converged,
            "provenance_id": f"{raw['Project']}:{raw['Design']}:{raw['Setup']}:{raw['PointName']}",
            "project": raw["Project"], "design": raw["Design"], "setup": raw["Setup"],
            "rotor_position_deg": _number(raw, "RotorPosition [deg]"),
            "mesh_elements": _optional_number(raw, "MeshElements [count]"),
            "adaptive_passes": _optional_number(raw, "AdaptivePasses [count]"),
            "solver_message": raw["SolverMessage"],
            "torque_fem_nm": _optional_number(raw, "Torque [N*m]") if converged else None,
            "pole_pairs": _positive_integer(raw, "PolePairs [count]"),
            "qualification_purpose": point["PointName"],
            "raw_units": json.dumps({
                "id": "A", "iq": "A", "if": "A", "flux_d": "Wb",
                "flux_q": "Wb", "torque": "N*m", "rotor_position": "deg",
                "mesh_elements": "count", "adaptive_passes": "count",
                "pole_pairs": "count",
            }, sort_keys=True),
        })
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=CANONICAL_FIELDS)
        writer.writeheader()
        writer.writerows(canonical)
    return canonical


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("raw", type=Path)
    parser.add_argument("points", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    normalize_results(args.raw, args.points, args.output)


if __name__ == "__main__":
    main()
