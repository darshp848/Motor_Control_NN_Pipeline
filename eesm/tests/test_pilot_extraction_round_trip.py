"""Phase 2 exit-gate tests: dq<->abc round trip + pilot schema validation.

PILOT_EXECUTION_PLAN.md Phase 2.6 requires:

  - offline dry-parse of the exporter under CPython (python -m py_compile);
  - a mock-object unit run of the abc/dq round trip: dq -> abc -> dq
    identity to 1e-12 at theta = 330.01 deg.

The exporter itself cannot be imported under CPython (its top level
executes the AEDT entry point), so the round-trip is exercised against
eesm/aedt/flux_extraction_v2.py -- the single source of truth for
D_AXIS_ELECTRICAL_DEG, dq_from_abc, abc_from_dq, and zero_sequence_ratio --
which is IronPython-safe by construction and has no top-level side
effects.

The schema test asserts that one representative row produced by
eesm/aedt/freeze_pilot_block.py validates against
eesm/schemas/eesm_point.schema.json; that covers Phase 3.3's frozen block
in the same exit gate. A regression test guards the on-disk hash so the
frozen block cannot silently drift without forcing the exporter's hash
guard to re-fire on the live side.

No AEDT licence is used by any test here.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import sys

import jsonschema
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
AEDT_DIR = os.path.join(ROOT, "aedt")
SCHEMA_DIR = os.path.join(ROOT, "schemas")
REPO_ROOT = os.path.dirname(ROOT)

# flux_extraction_v2 is IronPython-safe (math-only) and importable here.
if AEDT_DIR not in sys.path:
    sys.path.insert(0, AEDT_DIR)
from flux_extraction_v2 import (  # noqa: E402
    D_AXIS_ELECTRICAL_DEG,
    FRACTIONS,
    abc_from_dq,
    dq_from_abc,
    zero_sequence_ratio,
)
from data.experiment_points import canonical_point_id  # noqa: E402 (conftest path)

# freeze_pilot_block is offline CPython; lives alongside the exporter.
FREEZE_PY = os.path.join(AEDT_DIR, "freeze_pilot_block.py")
FREEZE_DIR = os.path.join(REPO_ROOT, "out", "eesm", "pilot_20260721")
FROZEN_CSV = os.path.join(FREEZE_DIR, "frozen_points.csv")
FROZEN_SHA256 = os.path.join(FREEZE_DIR, "frozen_points.sha256")
SCHEMA_PATH = os.path.join(SCHEMA_DIR, "eesm_point.schema.json")

PILOT_DIR_ALIGN_THRESHOLD = 1.0e-12  # rad/deg residual for round-trip identity


# ---------------------------------------------------------------------------
# Phase 2 exit gate: dq <-> abc round trip at the measured d-axis angle
# ---------------------------------------------------------------------------

def _identity_residual_deg(id_a, iq_a, theta_deg):
    abc = abc_from_dq(id_a, iq_a, theta_deg)
    d, q = dq_from_abc(abc[0], abc[1], abc[2], theta_deg)
    return math.hypot(d - id_a, q - iq_a), abc, (d, q)


def test_dq_abc_round_trip_identity_at_measured_d_axis():
    """dq -> abc -> dq must reconstruct (id, iq) to within 1e-12 at 330.01 deg."""
    residual, _abc, _recovered = _identity_residual_deg(
        -30.0, 45.0, D_AXIS_ELECTRICAL_DEG)
    assert residual < PILOT_DIR_ALIGN_THRESHOLD, (
        "dq<->abc round trip not identity at D_AXIS_ELECTRICAL_DEG="
        + str(D_AXIS_ELECTRICAL_DEG) + "; residual=" + str(residual))


def test_abc_dq_abc_round_trip_identity_at_measured_d_axis():
    """abc -> dq -> abc must reconstruct the abc set to within 1e-12."""
    theta_deg = D_AXIS_ELECTRICAL_DEG
    th = theta_deg * math.pi / 180.0
    base_abc = (math.cos(th), math.cos(th - 2 * math.pi / 3),
               math.cos(th + 2 * math.pi / 3))
    d, q = dq_from_abc(*base_abc, theta_deg)
    recovered = abc_from_dq(d, q, theta_deg)
    residual = max(abs(a - b) for a, b in zip(base_abc, recovered))
    assert residual < PILOT_DIR_ALIGN_THRESHOLD, (
        "abc<->dq<->abc round trip residual=" + str(residual))


def test_dq_abc_round_trip_identity_on_zero_q():
    """Pure-d (iq=0) must map to a balanced abc set with zero residual."""
    residual, _abc, (d, q) = _identity_residual_deg(
        -25.0, 0.0, D_AXIS_ELECTRICAL_DEG)
    assert residual < PILOT_DIR_ALIGN_THRESHOLD
    assert abs(q) < 1e-12


def test_dq_abc_round_trip_identity_on_zero_d():
    """Pure-q (id=0) must map to a balanced abc set with zero residual."""
    residual, _abc, (d, q) = _identity_residual_deg(
        0.0, 30.0, D_AXIS_ELECTRICAL_DEG)
    assert residual < PILOT_DIR_ALIGN_THRESHOLD
    assert abs(d) < 1e-12


def test_d_axis_angle_matches_diagnostic_verdict():
    """D_AXIS_ELECTRICAL_DEG must match the flux-convention verdict.

    flux_extraction_v2 stores the binding constant in the rounded form used
    for current injection (330.01 deg); the verdict.json full-precision
    value (330.01189...) rounds to it within 2e-3 deg. Guards against an
    accidental edit of flux_extraction_v2 that would silently invalidate
    the round-trip tests above.
    """
    assert D_AXIS_ELECTRICAL_DEG == 330.01
    assert abs(330.0118923436186 - D_AXIS_ELECTRICAL_DEG) < 2.0e-3


def test_fractions_constant_intact():
    assert FRACTIONS == 4  # r2 contract: one-pole sector; torque x4 unconditionally


def test_zero_sequence_ratio_balanced_set_is_below_limit():
    """zero_sequence_ratio of a balanced set (0.0, 45.0, 0) dq must be ~0."""
    abc = abc_from_dq(0.0, 45.0, D_AXIS_ELECTRICAL_DEG)
    ratio = zero_sequence_ratio(*abc)
    assert ratio < 1e-9


# ---------------------------------------------------------------------------
# Phase 3.3: frozen pilot block schema + hash integrity
# ---------------------------------------------------------------------------

def _import_freeze_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("freeze_pilot_block", FREEZE_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_schema():
    with open(SCHEMA_PATH, "r") as stream:
        return json.load(stream)


def _progress_row(name, id_a, iq_a, if_a, role="reference", region="interior"):
    """One full progress-CSV row as the importer would write it.

    Every required eesm_point.schema.json column is present and populated
    with the values the exporter writes; additional pilot diagnostics ride
    as additionalProperties (permitted by the schema).
    """
    return {
        "point_id": canonical_point_id(id_a, iq_a, if_a),
        "role": role,
        "source": "eesm_pilot_export_20260721",
        "region": region,
        "id_a": float(id_a),
        "iq_a": float(iq_a),
        "if_a": float(if_a),
        "lambda_d_wb": -1.0e-3,
        "lambda_q_wb": 4.5e-4,
        "solver_status": "converged",
        "converged": True,
        "provenance_id": "eesm_pilot_20260721::" + name,
    }


def test_progress_row_validates_against_point_schema():
    """One exporter-emitted progress row must satisfy eesm_point.schema.json."""
    schema = _load_schema()
    row = _progress_row("pure_d_neg", -30.0, 0.0, 2.0)
    jsonschema.validate(row, schema)


def test_progress_row_requires_role_enum():
    """A bogus role must be rejected (proves the schema is actually wired)."""
    schema = _load_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_progress_row("x", 0.0, 0.0, 2.0, role="bogus"), schema)


def test_progress_row_requires_region_enum():
    schema = _load_schema()
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(_progress_row("x", 0.0, 0.0, 2.0, region="nowhere"), schema)


def test_progress_row_rejects_wrong_point_id_pattern():
    schema = _load_schema()
    row = _progress_row("x", 0.0, 0.0, 2.0)
    row["point_id"] = "NOT-HEX!"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(row, schema)


# ---------------------------------------------------------------------------
# Frozen block on-disk integrity and exporter-alignment
# ---------------------------------------------------------------------------

def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def test_frozen_pilot_exists_and_hash_matches_record():
    if not os.path.exists(FROZEN_SHA256):
        pytest.skip("frozen pilot block not present; run freeze_pilot_block.py")
    with open(FROZEN_SHA256, "r") as stream:
        recorded = stream.read().strip().lower()
    actual = _sha256_file(FROZEN_CSV)
    assert actual == recorded, (
        "frozen_points.sha256 drifts from frozen_points.csv; "
        "regenerate via eesm/aedt/freeze_pilot_block.py")


def _exporter_format_current(value):
    rounded = round(float(value), 9)
    if rounded == 0.0:
        rounded = 0.0
    return "%.9f" % rounded


def _exporter_canonical_point_id(values):
    payload = "|".join(_exporter_format_current(value) for value in values)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]


def test_frozen_pilot_point_ids_match_exporter_ironpython_port():
    """The exporter re-reads frozen_points.csv and re-derives point_id with
    its own IronPython `_format_current` + `canonical_point_id`. This offline
    replica of that exact code path must reproduce every frozen point_id, or
    the exporter will raise 'Point identity mismatch' on the live design.
    """
    if not os.path.exists(FROZEN_CSV):
        pytest.skip("frozen pilot CSV not present")
    with open(FROZEN_CSV, "r") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 8, "pilot block must have exactly 8 points"
    for row in rows:
        values = (float(row["id_a"]), float(row["iq_a"]), float(row["if_a"]))
        expected = _exporter_canonical_point_id(values)
        assert row["point_id"] == expected, (
            "point_id '" + row["point_id"] + "' for point '"
            + row["point_name"] + "' does not match the exporter's "
            "canonical_point_id port '" + expected + "'")


def test_frozen_pilot_currents_away_from_legacy_200a_terminal_excursions():
    """PILOT_EXECUTION_PLAN.md Phase 3.1: nothing near the legacy 200 A-terminal excursions."""
    if not os.path.exists(FROZEN_CSV):
        pytest.skip("frozen pilot CSV not present")
    with open(FROZEN_CSV, "r") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        id_a = float(row["id_a"])
        iq_a = float(row["iq_a"])
        magnitude = math.hypot(id_a, iq_a)
        assert magnitude < 80.0, (
            "pilot point '" + row["point_name"] + "' exceeds the modest "
            "terminal-amp envelope (|id,iq|=" + str(magnitude)
            + "A); keep clear of the legacy 200 A-terminal excursions.")


def test_frozen_pilot_includes_two_distinct_field_only_points():
    """Phase 4.4 needs a SECOND field-only point to confirm 330.01 deg."""
    if not os.path.exists(FROZEN_CSV):
        pytest.skip("frozen pilot CSV not present")
    with open(FROZEN_CSV, "r") as stream:
        rows = list(csv.DictReader(stream))
    field_only = [row for row in rows
                  if float(row["id_a"]) == 0.0 and float(row["iq_a"]) == 0.0]
    assert len(field_only) >= 2, "need >=2 field-only points for Phase 4.4"
    ifs = {float(r["if_a"]) for r in field_only}
    assert 2.0 not in ifs, (
        "field-only points must NOT reuse the diagnostic's If=2A; Phase 3.1 "
        "requires a DIFFERENT If so the d-axis confirmation is independent.")
    assert len(ifs) >= 2, "field-only points must use at least two distinct If"