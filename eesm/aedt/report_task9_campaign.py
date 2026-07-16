"""Fail-closed evidence report for the frozen Task 9 Maxwell campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter
from pathlib import Path
from typing import Any


FEM_TO_CONTROLLER_TORQUE_SIGN = -1.0
TORQUE_CLOSURE_TOLERANCE_NM = 1.1
MESH_ELEMENT_LIMIT = 1950
EXPECTED_PROJECT = "eesm_qual"
EXPECTED_DESIGN = "EESM_2D_Qual"
EXPECTED_SETUP = "Setup_Qual"
EXPECTED_POLE_PAIRS = 2
EXPECTED_ROLES = {"train": 40, "selection": 12, "reference": 8, "scheduler_audit": 4}
ADAPTIVE_NONCONVERGENCE_MARKER = "adaptive passes did not converge"
EXPECTED_UNITS = {
    "id": "A", "iq": "A", "if": "A", "flux_d": "Wb", "flux_q": "Wb",
    "torque": "N*m", "rotor_position": "deg",
    "mesh_elements": "count", "adaptive_passes": "count", "pole_pairs": "count",
}


def _read(path: Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def _check(passed: bool, reason: str, evidence: Any = None) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "pass" if passed else "fail", "reason": reason}
    if evidence is not None:
        result["evidence"] = evidence
    return result


def _torque_error_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {
            "count": 0, "within_tolerance": 0, "outside_tolerance": 0,
            "mean_abs_error_nm": None, "rms_error_nm": None,
            "max_abs_error_nm": None, "by_region": {}, "worst_points": [],
        }
    errors = [item["abs_error_nm"] for item in items]
    by_region: dict[str, list[float]] = {}
    for item in items:
        by_region.setdefault(item["region"], []).append(item["abs_error_nm"])
    return {
        "count": len(errors),
        "within_tolerance": sum(error <= TORQUE_CLOSURE_TOLERANCE_NM for error in errors),
        "outside_tolerance": sum(error > TORQUE_CLOSURE_TOLERANCE_NM for error in errors),
        "mean_abs_error_nm": sum(errors) / len(errors),
        "rms_error_nm": math.sqrt(sum(error * error for error in errors) / len(errors)),
        "max_abs_error_nm": max(errors),
        "by_region": {
            region: {
                "count": len(values),
                "mean_abs_error_nm": sum(values) / len(values),
                "max_abs_error_nm": max(values),
                "outside_tolerance": sum(
                    value > TORQUE_CLOSURE_TOLERANCE_NM for value in values
                ),
            }
            for region, values in sorted(by_region.items())
        },
        "worst_points": sorted(
            items, key=lambda item: (-item["abs_error_nm"], item["point_id"])
        )[:5],
    }


def _finite(row: dict[str, str], names: tuple[str, ...]) -> bool:
    try:
        return all(math.isfinite(float(row[name])) for name in names)
    except (KeyError, TypeError, ValueError):
        return False


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _sha256_row(row: dict[str, str]) -> str:
    payload = json.dumps(row, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _matches_frozen_currents(row: dict[str, str], frozen: dict[str, str] | None) -> bool:
    if frozen is None:
        return False
    try:
        return all(
            float(row[canonical_name]) == float(frozen[frozen_name])
            for canonical_name, frozen_name in (
                ("id_a", "Id [A]"), ("iq_a", "Iq [A]"), ("if_a", "If [A]")
            )
        )
    except (KeyError, TypeError, ValueError):
        return False


def _machine_metadata_ok(row: dict[str, str]) -> bool:
    try:
        return (
            row.get("project") == EXPECTED_PROJECT
            and row.get("design") == EXPECTED_DESIGN
            and row.get("setup") == EXPECTED_SETUP
            and float(row["pole_pairs"]).is_integer()
            and int(float(row["pole_pairs"])) == EXPECTED_POLE_PAIRS
            and float(row["rotor_position_deg"]) == 180.0
        )
    except (KeyError, TypeError, ValueError):
        return False


def build_report(points_path: Path, raw_path: Path, canonical_path: Path, report_path: Path) -> dict[str, Any]:
    points = _read(points_path)
    raw_rows = _read(raw_path)
    rows = _read(canonical_path)
    expected_ids = [row.get("point_id", "") for row in points]
    observed_ids = [row.get("point_id", "") for row in rows]
    point_by_id = {row.get("point_id", ""): row for row in points}

    completion_ok = (
        len(points) == 64 and len(raw_rows) == 64 and len(rows) == 64
        and len(set(expected_ids)) == 64 and len(set(observed_ids)) == 64
        and set(observed_ids) == set(expected_ids)
        and {row.get("PointName", "") for row in raw_rows} == set(expected_ids)
    )
    current_tuples = [(row.get("id_a"), row.get("iq_a"), row.get("if_a")) for row in rows]
    roles = Counter(row.get("role", "") for row in rows)
    roles_ok = roles == Counter(EXPECTED_ROLES) and all(
        row.get("role") == point_by_id.get(row.get("point_id", ""), {}).get("role")
        for row in rows
    )
    regions_ok = all(
        row.get("region") == point_by_id.get(row.get("point_id", ""), {}).get("region")
        for row in rows
    )
    currents_match = all(
        _matches_frozen_currents(row, point_by_id.get(row.get("point_id", "")))
        for row in rows
    )
    domain_ok = all(
        _finite(row, ("id_a", "iq_a", "if_a"))
        and -120.0 <= float(row["id_a"]) <= 0.0
        and 0.0 <= float(row["iq_a"]) <= 120.0
        and 0.0 <= float(row["if_a"]) <= 15.0
        and (float(row["id_a"]), float(row["iq_a"]), float(row["if_a"])) != (0.0, 0.0, 0.0)
        for row in rows
    )
    converged_ok = all(
        row.get("solver_status") == "converged" and row.get("converged", "").lower() == "true"
        for row in rows
    )
    finite_ok = all(_finite(row, ("lambda_d_wb", "lambda_q_wb", "torque_fem_nm", "torque_controller_nm")) for row in rows)
    metadata_ok = all(_machine_metadata_ok(row) for row in rows)
    mesh_numeric = [float(row["mesh_elements"]) for row in rows if _finite(row, ("mesh_elements",))]
    pass_numeric = [float(row["adaptive_passes"]) for row in rows if _finite(row, ("adaptive_passes",))]
    mesh_values = [int(value) for value in mesh_numeric if value.is_integer()]
    pass_values = [int(value) for value in pass_numeric if value.is_integer()]
    mesh_ok = len(mesh_values) == len(rows) and all(0 < value <= MESH_ELEMENT_LIMIT for value in mesh_values)
    convergence_evidence_ok = len(pass_values) == len(rows) and all(value > 0 for value in pass_values)
    units_ok = all(_json_object(row.get("raw_units", "")) == EXPECTED_UNITS for row in rows)

    messages_ok = True
    for row in rows:
        messages = _json_object(row.get("solver_message", ""))
        if messages is None or messages.get("errors") or any(
            ADAPTIVE_NONCONVERGENCE_MARKER in str(item).lower()
            for item in messages.get("warnings", [])
        ):
            messages_ok = False

    raw_progress_sha256 = _sha256_file(raw_path)
    raw_by_name = {row.get("PointName", ""): row for row in raw_rows}
    evidence_paths_ok = len(raw_by_name) == len(raw_rows)
    for row in rows:
        evidence_fields = (
            ("raw_abc_flux_path", "raw_abc_flux_sha256"),
            ("mesh_evidence_path", "mesh_evidence_sha256"),
            ("convergence_evidence_path", "convergence_evidence_sha256"),
        )
        for name, hash_name in evidence_fields:
            path_text = row.get(name, "")
            path = Path(path_text)
            if (not path_text or not path.is_file() or path.stat().st_size <= 0
                    or row.get(hash_name) != _sha256_file(path)):
                evidence_paths_ok = False
        raw_row = raw_by_name.get(row.get("point_id", ""))
        expected_provenance = f"{row.get('project')}:{row.get('design')}:{row.get('setup')}:{row.get('point_id')}"
        if (raw_row is None or row.get("raw_progress_sha256") != raw_progress_sha256
                or row.get("raw_row_sha256") != _sha256_row(raw_row)
                or row.get("provenance_id") != expected_provenance):
            evidence_paths_ok = False

    torque_errors: list[float] = []
    torque_error_items: list[dict[str, Any]] = []
    torque_sign_ok = True
    for row in rows:
        if not _finite(row, ("id_a", "iq_a", "lambda_d_wb", "lambda_q_wb", "torque_fem_nm", "torque_controller_nm")):
            torque_sign_ok = False
            continue
        torque_controller = FEM_TO_CONTROLLER_TORQUE_SIGN * float(row["torque_fem_nm"])
        if not math.isclose(float(row["torque_controller_nm"]), torque_controller, rel_tol=0.0, abs_tol=1e-12):
            torque_sign_ok = False
        torque_flux = 1.5 * EXPECTED_POLE_PAIRS * (
            float(row["lambda_d_wb"]) * float(row["iq_a"])
            - float(row["lambda_q_wb"]) * float(row["id_a"])
        )
        torque_error = abs(torque_controller - torque_flux)
        torque_errors.append(torque_error)
        torque_error_items.append({
            "point_id": row["point_id"], "role": row["role"],
            "region": row["region"], "id_a": float(row["id_a"]),
            "iq_a": float(row["iq_a"]), "if_a": float(row["if_a"]),
            "torque_controller_nm": torque_controller,
            "torque_from_flux_nm": torque_flux,
            "abs_error_nm": torque_error,
        })
    max_torque_error = max(torque_errors) if torque_errors else None
    torque_ok = torque_sign_ok and len(torque_errors) == len(rows) and max_torque_error is not None and max_torque_error <= TORQUE_CLOSURE_TOLERANCE_NM

    checks = {
        "exact_point_set": _check(completion_ok, "Exactly the frozen 64 unique point IDs must be present once."),
        "no_duplicate_currents": _check(len(set(current_tuples)) == len(rows), "Current tuples must be unique."),
        "all_energized_converged": _check(converged_ok, "Every requested row must be an understood converged energized solve."),
        "finite_flux_and_torque": _check(finite_ok, "Flux and both torque conventions must be finite."),
        "units_and_machine_metadata": _check(units_ok and metadata_ok, "Units, project, design, setup, rotor position, and pole pairs must be frozen and consistent."),
        "student_mesh_limit": _check(mesh_ok, "Measured mesh elements must be positive and no more than 1,950.", {"max": max(mesh_values) if mesh_values else None}),
        "measured_convergence": _check(convergence_evidence_ok, "Every row must preserve a positive measured adaptive-pass count."),
        "current_and_sign_domain": _check(domain_ok and currents_match, "Canonical currents must match the frozen point rows, stay in-domain, and exclude the analytic source-free origin."),
        "task8_torque_translation": _check(torque_ok, "controller torque = -Torque_FEM and closure residual must remain within 1.1 N.m.", {"max_observed_error_nm": max_torque_error}),
        "immutable_role_boundaries": _check(roles_ok and regions_ok, "Roles and regions must match the pre-FEM frozen point CSV.", dict(roles)),
        "raw_to_canonical_provenance": _check(evidence_paths_ok, "Every canonical row must hash-link to raw progress and nonempty ABC, mesh, and convergence evidence."),
        "solver_messages": _check(messages_ok, "Every solver message payload must parse, contain no AEDT errors, and contain no adaptive non-convergence warning."),
    }
    overall = "pass" if all(item["status"] == "pass" for item in checks.values()) else "fail"
    threshold_decision = {
        "threshold_status": "baseline_required",
        "canonical_manifest_updated": False,
        "proposed_thresholds": {
            "data_qa": 0.0 if overall == "pass" else None,
            "interior": None, "boundary": None, "saturation": None,
            "field_weakening": None, "torque": None, "voltage": None, "feasibility": None,
        },
        "reason": "Task 9 can require zero failed baseline QA rows, but surrogate-error, voltage, and feasibility distributions do not exist until later frozen model evaluation. The all-or-none manifest threshold contract therefore remains baseline_required.",
        "scheduler_audit_used": False,
        "scheduler_audit_collected": completion_ok and roles.get("scheduler_audit", 0) == 4,
        "scheduler_audit_available_for_decisions": False,
    }
    report = {
        "task": 9,
        "campaign_status": overall,
        "requested_points": len(points),
        "converged_points": sum(row.get("converged", "").lower() == "true" for row in rows),
        "checks": checks,
        "torque_translation": {
            "controller_torque_from_fem_sign": FEM_TO_CONTROLLER_TORQUE_SIGN,
            "closure_tolerance_nm": TORQUE_CLOSURE_TOLERANCE_NM,
            "max_observed_error_nm": max_torque_error,
            "error_summary": _torque_error_summary(torque_error_items),
        },
        "threshold_decision": threshold_decision,
        "claims": {
            "promoted_surrogate": False,
            "controller_ready_lut": False,
            "release_ready_map": False,
            "task_10_complete": False,
        },
    }
    Path(report_path).parent.mkdir(parents=True, exist_ok=True)
    Path(report_path).write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("points", type=Path)
    parser.add_argument("raw", type=Path)
    parser.add_argument("canonical", type=Path)
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = build_report(args.points, args.raw, args.canonical, args.report)
    if report["campaign_status"] != "pass":
        sys.exit(1)


if __name__ == "__main__":
    main()
