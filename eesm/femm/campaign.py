"""Resumable, fail-closed campaign driver for the FEMM path.

Discipline copied from eesm/aedt/export_eesm_points.py (lines 574-662): a
resume that cannot prove the existing evidence is consistent REFUSES rather
than continuing. Every refusal raises CampaignRefusal with a message starting
"Refusing resume:", so an operator sees which invariant broke.

Invariants
----------
  - The frozen points CSV is hashed; a changed points file aborts a resume.
  - Results are only ever APPENDED. Nothing overwrites an existing row.
  - A completed point is never re-solved: the solver is not even called.
  - Every row is validated against eesm/schemas/eesm_point.schema.json
    BEFORE it is written. An invalid row aborts the run with nothing
    appended, rather than landing in the evidence file.
  - A failed solve is recorded in the status JSON and stops the run; it is
    never written to the results CSV as if it were data.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

import jsonschema

from . import runtime
from .config import DEFAULT_CONFIG, FemmConfig, as_provenance_payload
from .extract import extract_point


class CampaignRefusal(RuntimeError):
    """A resume or write invariant failed. Nothing was modified."""


SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "schemas", "eesm_point.schema.json",
)

SOURCE_TAG = "eesm_femm_campaign"

#: Columns required from the frozen points CSV.
FROZEN_POINT_FIELDS: Sequence[str] = (
    "point_name", "point_id", "role", "region", "id_a", "iq_a", "if_a",
)

#: Result columns. The first block is schema-required; the rest ride along as
#: additionalProperties (the schema permits them).
#:
#: 'lambda_field_wb' is deliberately NOT called 'lambda_f_wb': the schema sets
#: that property to `false`, meaning FORBIDDEN, and a row carrying it fails
#: validation outright.
RESULT_FIELDS: Sequence[str] = (
    "point_id", "role", "source", "region",
    "id_a", "iq_a", "if_a",
    "lambda_d_wb", "lambda_q_wb",
    "solver_status", "converged", "provenance_id",
    # diagnostics
    "point_name",
    "lambda_a_wb", "lambda_b_wb", "lambda_c_wb", "lambda_field_wb",
    "zero_sequence_ratio",
    "torque_sector_nm", "torque_fem_nm", "torque_identity_nm",
    "torque_residual_nm", "torque_residual_rel", "torque_residual_suspect",
    "flux_multiplier", "torque_sector_multiplier",
    "rotor_angle_deg", "theta_electrical_deg",
    "pole_pairs", "model_depth_m",
    "mesh_elements", "solver_backend",
)

FORBIDDEN_ROW_KEYS = ("lambda_f_wb", "roles")


@dataclass(frozen=True)
class CampaignPaths:
    """Where a campaign keeps its inputs and its evidence."""

    root: str

    @property
    def points_csv(self) -> str:
        return os.path.join(self.root, "frozen_points.csv")

    @property
    def results_csv(self) -> str:
        return os.path.join(self.root, "femm_results.csv")

    @property
    def status_json(self) -> str:
        return os.path.join(self.root, "femm_status.json")

    def ensure(self) -> None:
        os.makedirs(self.root, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def load_schema(path: str = SCHEMA_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def _coerce_row_for_schema(row: Dict[str, Any]) -> Dict[str, Any]:
    """CSV round-trips everything to text; the schema wants real types."""
    payload = dict(row)
    for key in ("id_a", "iq_a", "if_a", "lambda_d_wb", "lambda_q_wb"):
        value = payload.get(key)
        if value in ("", None):
            payload[key] = None
        else:
            payload[key] = float(value)
    converged = payload.get("converged")
    if isinstance(converged, str):
        payload["converged"] = converged.strip().lower() in ("true", "1", "yes")
    return payload


def validate_row(row: Dict[str, Any],
                 schema: Optional[Dict[str, Any]] = None) -> None:
    """Raise CampaignRefusal unless the row satisfies the frozen schema."""
    for key in FORBIDDEN_ROW_KEYS:
        if key in row:
            raise CampaignRefusal(
                "Refusing write: %r is forbidden by eesm_point.schema.json "
                "(the schema sets that property to `false`)." % key
            )
    schema = schema if schema is not None else load_schema()
    try:
        jsonschema.validate(_coerce_row_for_schema(row), schema)
    except jsonschema.ValidationError as exc:
        raise CampaignRefusal(
            "Refusing write: row failed eesm_point.schema.json: %s"
            % str(exc).splitlines()[0]
        )


def read_points(path: str) -> List[Dict[str, Any]]:
    """Read the frozen points CSV. Fail closed on anything unexpected."""
    if not os.path.exists(path):
        raise CampaignRefusal("Refusing run: frozen points file missing: %s" % path)
    with open(path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        names = list(reader.fieldnames or [])
        missing = [f for f in FROZEN_POINT_FIELDS if f not in names]
        if missing:
            raise CampaignRefusal(
                "Refusing run: frozen points file is missing columns %s" % missing
            )
        rows = [dict(row) for row in reader]
    if not rows:
        raise CampaignRefusal("Refusing run: frozen points file has no rows")
    seen: Set[str] = set()
    for row in rows:
        name = row.get("point_name", "")
        if not name:
            raise CampaignRefusal("Refusing run: frozen point with empty point_name")
        if name in seen:
            raise CampaignRefusal("Refusing run: duplicate frozen point " + name)
        seen.add(name)
        for key in ("id_a", "iq_a", "if_a"):
            try:
                float(row[key])
            except (TypeError, ValueError):
                raise CampaignRefusal(
                    "Refusing run: frozen point %s has non-numeric %s" % (name, key)
                )
    return rows


def read_progress(path: str, expected: Sequence[Dict[str, Any]]):
    """Read completed results, refusing anything inconsistent with `expected`."""
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return [], set()
    with open(path, "r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        if list(reader.fieldnames or []) != list(RESULT_FIELDS):
            raise CampaignRefusal("Refusing resume: malformed results header")
        rows = [dict(row) for row in reader]

    names = [row.get("point_name", "") for row in rows]
    if len(set(names)) != len(names):
        raise CampaignRefusal("Refusing resume: duplicated results row")

    expected_by_name = {row["point_name"]: row for row in expected}
    for row in rows:
        name = row.get("point_name", "")
        if name not in expected_by_name:
            raise CampaignRefusal("Refusing resume: unknown results point " + name)
        if row.get("solver_status", "").strip().lower() != "converged":
            raise CampaignRefusal("Refusing resume: results contain failed row " + name)
        if str(row.get("converged", "")).strip().lower() not in ("true", "1", "yes"):
            raise CampaignRefusal(
                "Refusing resume: results row not marked converged: " + name)
        frozen = expected_by_name[name]
        if row.get("point_id") != frozen.get("point_id"):
            raise CampaignRefusal("Refusing resume: inconsistent point_id for " + name)
        if row.get("role") != frozen.get("role"):
            raise CampaignRefusal("Refusing resume: inconsistent role for " + name)
        if row.get("region") != frozen.get("region"):
            raise CampaignRefusal("Refusing resume: inconsistent region for " + name)
        for key in ("id_a", "iq_a", "if_a"):
            if float(row[key]) != float(frozen[key]):
                raise CampaignRefusal(
                    "Refusing resume: inconsistent %s for %s" % (key, name))
    return rows, set(names)


def read_prior_status(path: str, points_hash: str, results_path: str
                      ) -> Optional[Dict[str, Any]]:
    """Cross-check the status JSON against the results file. Fail closed."""
    results_exist = os.path.exists(results_path) and os.path.getsize(results_path) > 0
    if not os.path.exists(path):
        if results_exist:
            raise CampaignRefusal("Refusing resume: results exist without status JSON")
        return None
    try:
        with open(path, "r", encoding="utf-8") as stream:
            prior = json.load(stream)
    except BaseException:
        raise CampaignRefusal("Refusing resume: status JSON is malformed")
    if not results_exist:
        raise CampaignRefusal("Refusing resume: status JSON exists without results")
    if prior.get("points_sha256") != points_hash:
        raise CampaignRefusal(
            "Refusing resume: frozen points file changed since the last run")
    if prior.get("failure"):
        raise CampaignRefusal(
            "Refusing resume: prior run recorded a failure and needs operator review")
    return prior


def append_row(path: str, row: Dict[str, Any]) -> None:
    """Append one row. Never truncates, never rewrites."""
    exists = os.path.exists(path) and os.path.getsize(path) > 0
    with open(path, "a", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(RESULT_FIELDS),
                                extrasaction="raise")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def write_status(path: str, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True, default=str)


def provenance_id(point: Dict[str, Any], points_hash: str) -> str:
    """Stable id tying a row to its point and to the exact frozen input file."""
    payload = "|".join([
        SOURCE_TAG, points_hash, str(point.get("point_id", "")),
        str(point.get("point_name", "")),
    ])
    return "%s:%s" % (SOURCE_TAG, hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16])


# ---------------------------------------------------------------------------
# Row assembly
# ---------------------------------------------------------------------------


def build_row(point: Dict[str, Any], result: Dict[str, Any], points_hash: str,
              solver_backend: str) -> Dict[str, Any]:
    """Assemble one result row in RESULT_FIELDS order."""
    row: Dict[str, Any] = {
        "point_id": point["point_id"],
        "role": point["role"],
        "source": SOURCE_TAG,
        "region": point["region"],
        "id_a": float(point["id_a"]),
        "iq_a": float(point["iq_a"]),
        "if_a": float(point["if_a"]),
        "lambda_d_wb": result.get("lambda_d_wb"),
        "lambda_q_wb": result.get("lambda_q_wb"),
        "solver_status": result.get("solver_status", "unknown"),
        "converged": bool(result.get("converged", False)),
        "provenance_id": provenance_id(point, points_hash),
        "point_name": point["point_name"],
        "lambda_a_wb": result.get("lambda_a_wb"),
        "lambda_b_wb": result.get("lambda_b_wb"),
        "lambda_c_wb": result.get("lambda_c_wb"),
        "lambda_field_wb": result.get("lambda_field_wb"),
        "zero_sequence_ratio": result.get("zero_sequence_ratio"),
        "torque_sector_nm": result.get("torque_sector_nm"),
        "torque_fem_nm": result.get("torque_fem_nm"),
        "torque_identity_nm": result.get("torque_identity_nm"),
        "torque_residual_nm": result.get("torque_residual_nm"),
        "torque_residual_rel": result.get("torque_residual_rel"),
        "torque_residual_suspect": result.get("torque_residual_suspect"),
        "flux_multiplier": result.get("flux_multiplier"),
        "torque_sector_multiplier": result.get("torque_sector_multiplier"),
        "rotor_angle_deg": result.get("rotor_angle_deg"),
        "theta_electrical_deg": result.get("theta_electrical_deg"),
        "pole_pairs": result.get("pole_pairs"),
        "model_depth_m": result.get("model_depth_m"),
        "mesh_elements": result.get("mesh_elements"),
        "solver_backend": solver_backend,
    }
    return row


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_campaign(handle: Any, paths: CampaignPaths,
                 cfg: FemmConfig = DEFAULT_CONFIG,
                 max_new_points: Optional[int] = None,
                 rotor_angle_deg: float = 0.0,
                 solver_backend: str = "unknown") -> Dict[str, Any]:
    """Solve every not-yet-completed point. Returns the status payload.

    `handle` is whatever runtime.resolve_femm() produced. Completed points are
    skipped WITHOUT calling the solver at all -- the mock's analyze_count is
    the evidence for that, asserted in test_femm_campaign.py.
    """
    paths.ensure()
    points = read_points(paths.points_csv)
    points_hash = sha256_file(paths.points_csv)

    prior = read_prior_status(paths.status_json, points_hash, paths.results_csv)
    existing_rows, completed = read_progress(paths.results_csv, points)

    if prior is not None:
        prior_completed = sorted(prior.get("completed", []))
        if prior_completed != sorted(completed):
            raise CampaignRefusal(
                "Refusing resume: status JSON and results rows disagree on "
                "which points are complete")

    schema = load_schema()
    pending = [point for point in points if point["point_name"] not in completed]

    status: Dict[str, Any] = {
        "campaign_id": SOURCE_TAG,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "points_sha256": points_hash,
        "points_total": len(points),
        "completed": sorted(completed),
        "pending_at_start": [point["point_name"] for point in pending],
        "solved_this_run": [],
        "failure": None,
        "status": "running",
        "solver_backend": solver_backend,
        "femm_availability": runtime.availability_payload(),
        "config_provenance": as_provenance_payload(cfg),
        "rotor_angle_deg": rotor_angle_deg,
    }

    budget = len(pending) if max_new_points is None else max_new_points
    for point in pending[:budget]:
        result = extract_point(
            handle,
            float(point["id_a"]), float(point["iq_a"]), float(point["if_a"]),
            rotor_angle_deg=rotor_angle_deg, cfg=cfg,
        )
        if not result.get("converged"):
            status["failure"] = {
                "point_name": point["point_name"],
                "solver_status": result.get("solver_status"),
            }
            status["status"] = "failed"
            write_status(paths.status_json, status)
            raise CampaignRefusal(
                "Refusing to continue: solve failed at %s (%s). Nothing was "
                "written for this point."
                % (point["point_name"], result.get("solver_status"))
            )
        row = build_row(point, result, points_hash, solver_backend)
        validate_row(row, schema)          # validate BEFORE writing
        append_row(paths.results_csv, row)
        status["completed"].append(point["point_name"])
        status["solved_this_run"].append(point["point_name"])

    status["completed"] = sorted(set(status["completed"]))
    status["status"] = ("complete" if len(status["completed"]) == len(points)
                        else "partial_resume_required")
    status["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    status["rows_before_run"] = len(existing_rows)
    write_status(paths.status_json, status)
    return status
