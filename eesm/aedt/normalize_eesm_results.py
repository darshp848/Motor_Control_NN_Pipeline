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
    "torque_controller_nm", "pole_pairs", "qualification_purpose", "raw_units",
    "campaign_id", "raw_abc_flux_path", "mesh_evidence_path",
    "convergence_evidence_path", "raw_progress_sha256", "raw_row_sha256",
    "raw_abc_flux_sha256", "mesh_evidence_sha256", "convergence_evidence_sha256",
)
ADAPTIVE_NONCONVERGENCE_MARKER = "adaptive passes did not converge"


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


def _sha256_file(path: str) -> str:
    evidence = Path(path)
    if not evidence.is_file() or evidence.stat().st_size <= 0:
        raise AdapterError("missing or empty AEDT evidence: " + path)
    return hashlib.sha256(evidence.read_bytes()).hexdigest()


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

    raw_progress_sha256 = hashlib.sha256(Path(raw_path).read_bytes()).hexdigest()
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
        computed_point_id = _point_id(currents)
        if point.get("point_id") and point["point_id"] != computed_point_id:
            raise AdapterError("frozen point ID does not match currents for " + raw["PointName"])
        role = point.get("role", "reference")
        if role not in {"train", "selection", "scheduler_audit", "reference"}:
            raise AdapterError("unknown frozen role for " + raw["PointName"])
        task9 = bool(point.get("campaign_id"))
        if task9 and converged and ADAPTIVE_NONCONVERGENCE_MARKER in raw.get("SolverMessage", "").lower():
            raise AdapterError("AEDT adaptive convergence criteria were not met for " + raw["PointName"])
        torque_fem = _number(raw, "Torque [N*m]") if converged else None
        if task9 and raw.get("PointID") != computed_point_id:
            raise AdapterError("raw point ID does not match frozen identity for " + raw["PointName"])
        if task9 and (raw.get("Role") != role or raw.get("Region") != point["region"]):
            raise AdapterError("raw role or region differs from frozen point " + raw["PointName"])
        if task9 and converged:
            mesh_elements: float | int | None = _positive_integer(raw, "MeshElements [count]")
            adaptive_passes: float | int | None = _positive_integer(raw, "AdaptivePasses [count]")
            evidence_paths = {
                "raw_abc_flux_path": raw.get("RawABCFluxPath", ""),
                "mesh_evidence_path": raw.get("MeshEvidencePath", ""),
                "convergence_evidence_path": raw.get("ConvergenceEvidencePath", ""),
            }
            evidence_hashes = {name.replace("_path", "_sha256"): _sha256_file(path)
                               for name, path in evidence_paths.items()}
        else:
            mesh_elements = _optional_number(raw, "MeshElements [count]")
            adaptive_passes = _optional_number(raw, "AdaptivePasses [count]")
            evidence_paths = {
                "raw_abc_flux_path": raw.get("RawABCFluxPath", ""),
                "mesh_evidence_path": raw.get("MeshEvidencePath", ""),
                "convergence_evidence_path": raw.get("ConvergenceEvidencePath", ""),
            }
            evidence_hashes = {
                "raw_abc_flux_sha256": "", "mesh_evidence_sha256": "",
                "convergence_evidence_sha256": "",
            }
        canonical.append({
            "point_id": computed_point_id, "role": role, "source": "maxwell_aedt",
            "region": point["region"], "id_a": currents[0], "iq_a": currents[1], "if_a": currents[2],
            "lambda_d_wb": _number(raw, "Flux_d [Wb]") if converged else None,
            "lambda_q_wb": _number(raw, "Flux_q [Wb]") if converged else None,
            "solver_status": status, "converged": converged,
            "provenance_id": f"{raw['Project']}:{raw['Design']}:{raw['Setup']}:{raw['PointName']}",
            "project": raw["Project"], "design": raw["Design"], "setup": raw["Setup"],
            "rotor_position_deg": _number(raw, "RotorPosition [deg]"),
            "mesh_elements": mesh_elements,
            "adaptive_passes": adaptive_passes,
            "solver_message": raw["SolverMessage"],
            "torque_fem_nm": torque_fem,
            "torque_controller_nm": -torque_fem if torque_fem is not None else None,
            "pole_pairs": _positive_integer(raw, "PolePairs [count]"),
            "qualification_purpose": point.get("Purpose", point["PointName"]),
            "raw_units": json.dumps({
                "id": "A", "iq": "A", "if": "A", "flux_d": "Wb",
                "flux_q": "Wb", "torque": "N*m", "rotor_position": "deg",
                "mesh_elements": "count", "adaptive_passes": "count",
                "pole_pairs": "count",
            }, sort_keys=True),
            "campaign_id": point.get("campaign_id", "task8_qualification"),
            **evidence_paths,
            "raw_progress_sha256": raw_progress_sha256,
            "raw_row_sha256": hashlib.sha256(
                json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            **evidence_hashes,
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
