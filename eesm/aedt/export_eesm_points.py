"""Pilot EESM flux-extraction exporter (IronPython 2.7, AEDT 2025 R2 Student).

Phase 2 of eesm/docs/PILOT_EXECUTION_PLAN.md (2026-07-21). Replaces the
frozen Task 9 exporter, which used route A (FluxLinkage(PhaseX)) at
ROTOR_POSITION_DEG = 180 deg in the legacy branch-amp frame. All three of
those were disproved by the 2026-07-21 flux-convention diagnostic
(out/eesm/flux_convention_diagnostic/verdict.json); see
eesm/aedt/flux_extraction_v2.py NOTES 1-4 for the binding decisions.

Differences from the superseded Task 9 exporter
----------------------------------------------
- Flux readout: route C from flux_extraction_v2.py -- per-sheet integral of
  A_z divided by sheet area, signed per COIL_MAP (same-sign; NO go/return
  differencing, which the diagnostic disproved), x CONDUCTORS_PER_SHEET x
  MODEL_DEPTH_M. Flux multiplier x1 (terminal flux; r2 contract). The
  formula lives in one place: flux_extraction_v2.lambda_abc_from_fields.
- Park reference angle: D_AXIS_ELECTRICAL_DEG = 330.01 deg electrical,
  measured from the field-only probe and awaiting a confirming point
  (NOTES 2). The 180 deg reference was wrong by 150 deg.
- Current injection in the 330.01 deg frame; commanded (id, iq) are
  TERMINAL amps (PB=4 divides internally; the field winding stays at one
  branch, so its commanded current is the actual field current).
- Preflight: read ParallelBranchesNum back from PhaseA/B/C and abort unless
  every stator phase reports 4 and the field reports 1; verify the twelve
  coil sheets named in COIL_MAP exist on the design. A run against a
  1-branch project (e.g. the original Task 9 solved project) is impossible,
  which is the protective intent of PILOT_EXECUTION_PLAN.md Phase 1.3.
- Per row: zero_sequence_ratio (inline), torque_fem_sector_nm, mesh count,
  adaptive passes, the exact injected phase currents and field current, a
  provenance id, plus every column eesm/schemas/eesm_point.schema.json
  requires. Rows with zero_sequence_ratio >= 0.05 are labelled
  'suspect' (1); they are not dropped and not silently accepted.

One-point-per-session AEDT GUI run model with progress-CSV resume, copied
from the Task 9 exporter. The runner (eesm/aedt/run_pilot_export.ps1) creates
the disposable project copy but launches AEDT headless with -RunScriptAndExit
only -- it does NOT itself open that copy (there is no AEDT CLI flag wired
into this runner to do so). This script therefore opens PROJECT_PATH itself
if it exists, exactly like the proven working pattern in
diagnose_flux_convention.py; it only falls back to an already-active project
if the disposable copy is missing (e.g. manual/interactive debugging).
CORRECTED 2026-07-22 after the first pilot invocation failed with "No active
project" -- the original design assumed the runner opened the project, which
it never did.

Scope guard
------------
This script does NOT authorise a campaign, promotion, or training step. It
qualifies extraction conventions only (PILOT_EXECUTION_PLAN.md Phase 5.4).
The frozen Task 9 dataset stays quarantined; its flux labels are wrong, not
out of tolerance.
"""

import csv
import hashlib
import json
import math
import os
import re
import sys
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))

# Single source of truth for extraction constants and the dq/abc pair.
# flux_extraction_v2.py is IronPython-safe by construction (math-only; the
# AEDT-calling functions take a design argument).
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from flux_extraction_v2 import (  # noqa: E402 (import after sys.path tweak)
    D_AXIS_ELECTRICAL_DEG,
    CONDUCTORS_PER_SHEET,
    MODEL_DEPTH_M,
    FRACTIONS,
    COIL_MAP,
    PHASES,
    zero_sequence_ratio,
    dq_from_abc,
    abc_from_dq,
    integrate_az,
    sheet_area,
    lambda_abc_from_fields,
)

# ---------------------------------------------------------------------------
# Pilot identity and paths
# ---------------------------------------------------------------------------

PILOT_ID = "eesm_pilot_20260721"
SOURCE_TAG = "eesm_pilot_export_20260721"
CAMPAIGN_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "pilot_20260721")
RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
POINTS = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
POINTS_SHA256_PATH = os.path.join(CAMPAIGN_ROOT, "frozen_points.sha256")
PROGRESS = os.path.join(RAW_ROOT, "pilot_progress.csv")
STATUS_JSON = os.path.join(RAW_ROOT, "pilot_status.json")
EXPORT_DIR = os.path.join(RAW_ROOT, "point_exports")
EVIDENCE_DIR = os.path.join(RAW_ROOT, "solver_evidence")

PROJECT_NAME = "eesm_pilot_01"
# The disposable copy run_pilot_export.ps1 creates. That runner launches AEDT
# headless (-RunScriptAndExit) but does not pass this path to AEDT on launch,
# so oDesktop has no active project when this script starts; see the module
# docstring's 2026-07-22 correction.
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
POLE_PAIRS = 2
TORQUE_OUTPUT_NAME = "Torque_FEM"

MAX_NEW_POINTS_PER_RUN = 1

# Safety ceiling on mesh element count, not the densification target. The
# Task 9 run on this Student licence saturated near ~1500-1900 elements;
# densifying past this value is an explicit, single-click user action on
# the setup (PILOT_EXECUTION_PLAN.md Phase 3.2). If you densify, raise this
# in lockstep -- the abort path is intentionally fail-closed.
MAX_MESH_ELEMENTS = 1950

ADAPTIVE_NONCONVERGENCE_MARKER = "adaptive passes did not converge"
ZERO_SEQUENCE_SUSPECT_RATIO = 0.05

EXPECTED_STATOR_PARALLEL_BRANCHES = 4
EXPECTED_FIELD_PARALLEL_BRANCHES = 1
EXPECTED_PILOT_BUDGET = 8

FROZEN_POINT_FIELDS = [
    "point_name", "point_id", "role", "region",
    "id_a", "iq_a", "if_a", "source", "provenance_note",
]

# Schema-aligned row keys (eesm/schemas/eesm_point.schema.json). The schema
# permits additionalProperties, so the pilot diagnostics ride alongside the
# required columns in the same CSV row.
PROGRESS_FIELDS = [
    # schema-required
    "point_id", "role", "source", "region",
    "id_a", "iq_a", "if_a",
    "lambda_d_wb", "lambda_q_wb",
    "solver_status", "converged", "provenance_id",
    # pilot extraction diagnostics (additionalProperties)
    "point_name",
    "lambda_a_wb", "lambda_b_wb", "lambda_c_wb",
    "zero_sequence_ratio",
    "suspect",
    "torque_fem_sector_nm",
    "mesh_elements", "adaptive_passes",
    "d_axis_electrical_deg",
    "conductors_per_sheet", "model_depth_m", "fractions", "pole_pairs",
    "expected_stator_parallel_branches",
    "expected_field_parallel_branches",
    "applied_phase_a_a", "applied_phase_b_a", "applied_phase_c_a",
    "applied_field_a",
    "project", "design", "setup",
    "raw_abc_flux_path", "mesh_evidence_path", "convergence_evidence_path",
    "solver_message",
]


# ---------------------------------------------------------------------------
# Generic utilities
# ---------------------------------------------------------------------------

def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def call(fn):
    try:
        raw_value = fn()
        return {"ok": True, "value": normalize(raw_value), "_raw": raw_value}
    except BaseException as exc:
        return {"ok": False, "error": str(exc),
                "traceback_tail": traceback.format_exc().splitlines()[-8:]}


def required(fn, label):
    outcome = call(fn)
    if not outcome["ok"]:
        raise RuntimeError(label + ": " + outcome["error"])
    return outcome["_raw"]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def write_status(payload):
    if not os.path.exists(RAW_ROOT):
        os.makedirs(RAW_ROOT)
    with open(STATUS_JSON, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def mark_stage(payload, point_name, stage):
    payload["active_point"] = point_name
    payload["stage"] = stage
    write_status(payload)


def is_finite(value):
    try:
        return not (math.isnan(value) or math.isinf(value))
    except BaseException:
        return False


def _format_current(value):
    rounded = round(float(value), 9)
    if rounded == 0.0:
        rounded = 0.0
    return "%.9f" % rounded


def canonical_point_id(values):
    payload = "|".join(_format_current(value) for value in values)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]


def numeric_output(value, name):
    try:
        number = float(str(value).split()[0])
    except BaseException:
        raise RuntimeError(name + " was not a plain numeric value in declared SI units")
    if not is_finite(number):
        raise RuntimeError(name + " was non-finite")
    return number


def _as_text_list(values):
    try:
        return [str(v) for v in list(values)]
    except BaseException:
        return []


# ---------------------------------------------------------------------------
# Frozen pilot points
# ---------------------------------------------------------------------------

def read_frozen_sha256():
    if not os.path.exists(POINTS_SHA256_PATH):
        raise RuntimeError("Missing frozen pilot SHA-256: " + POINTS_SHA256_PATH)
    with open(POINTS_SHA256_PATH, "r") as stream:
        recorded = stream.read().strip().lower()
    if not recorded or any(ch not in "0123456789abcdef" for ch in recorded):
        raise RuntimeError("Malformed frozen pilot SHA-256: " + POINTS_SHA256_PATH)
    return recorded


def read_points():
    recorded = read_frozen_sha256()
    actual = sha256_file(POINTS)
    if actual != recorded:
        raise RuntimeError(
            "Frozen pilot CSV hash mismatch. expected " + recorded
            + " actual " + actual
            + ". Regenerate via eesm/aedt/freeze_pilot_block.py."
        )
    with open(POINTS, "r") as stream:
        reader = csv.DictReader(stream)
        if list(reader.fieldnames or []) != FROZEN_POINT_FIELDS:
            raise RuntimeError("Malformed frozen pilot point header")
        points = list(reader)
    if len(points) != EXPECTED_PILOT_BUDGET:
        raise RuntimeError(
            "Frozen pilot point budget must be exactly " + str(EXPECTED_PILOT_BUDGET)
            + " (got " + str(len(points)) + ")"
        )
    names = [row["point_name"] for row in points]
    currents = []
    for row in points:
        values = tuple(float(row[name]) for name in ("id_a", "iq_a", "if_a"))
        currents.append(values)
        if row["point_id"] != canonical_point_id(values):
            raise RuntimeError("Point identity mismatch: " + row["point_name"])
        if values == (0.0, 0.0, 0.0):
            raise RuntimeError("Source-free origin must remain analytic")
        if row["role"] not in ("train", "selection", "scheduler_audit", "reference"):
            raise RuntimeError("Unknown frozen point role: " + row["point_name"])
        if row["region"] not in ("interior", "boundary", "saturation",
                                 "field_weakening", "unsupported"):
            raise RuntimeError("Unknown frozen point region: " + row["point_name"])
    if len(set(names)) != len(names):
        raise RuntimeError("Duplicate frozen pilot point name")
    if len(set(currents)) != len(currents):
        raise RuntimeError("Duplicate frozen pilot point currents")
    return points


# ---------------------------------------------------------------------------
# Preflight (Phase 1.3 / 1.4)
# ---------------------------------------------------------------------------

# Property name in the child-object data model (GetPropValue) for a winding
# group's parallel-branch count. This is the human-readable DISPLAY name, NOT
# the .aedt serialization key 'ParallelBranchesNum'. Confirmed against a live
# read in out/eesm/task9_requalification_r3_gui_recovery_20260716_01/
# active_project_audit.json ('Number of Parallel Branches' -> '4').
PARALLEL_BRANCHES_PROP = "Number of Parallel Branches"


def _read_winding_int(design, winding, prop):
    """Read an integer winding property via the Excitations child-object tree.

    CORRECTED 2026-07-22. The previous implementation used
    design.GetPropertyValue("BoundarySetupTab", winding, "ParallelBranchesNum"),
    which fails on AEDT 2025 R2 Student -- the same call is non-fatal-wrapped
    in diagnose_flux_convention.py and returned nothing there too (hence
    verdict.json coil_inventory_entries: 0 and the hardcoded FALLBACK_COIL_MAP
    in analyze_flux_convention.py). The reliable path on Student is tree
    navigation: design.GetChildObject("Excitations").GetChildObject(<winding>)
    .GetPropValue("Number of Parallel Branches"), the same API
    configure_active_r3_gui.py and audit_active_r3_gui.py use successfully.
    """
    node = required(
        lambda: design.GetChildObject("Excitations").GetChildObject(winding),
        "Get Excitations child node for winding " + winding,
    )
    raw = required(
        lambda: node.GetPropValue(prop),
        "Read '" + prop + "' for winding " + winding,
    )
    text = str(raw).strip()
    digits = ""
    for ch in text:
        if ch.isdigit() or (ch == "-" and not digits):
            digits += ch
        elif ch.isspace():
            continue
        else:
            break
    if not digits:
        raise RuntimeError(
            "Could not parse '" + prop + "'='" + text + "' for winding " + winding
        )
    return int(digits)


def preflight_winding_branches(design):
    """Abort unless PhaseA/B/C report ParallelBranchesNum == 4 and Field == 1.

    The r2 winding contract (eesm/docs/MAXWELL_EESM_QUALIFICATION.md): 36
    conductors/slot, FOUR balanced stator branches -> 36 series turns/phase.
    With PB=4 the commanded winding current is the TERMINAL current and AEDT
    drives each branch with I/4, so the per-sector flux linkage is the
    terminal flux linkage (multiplier x1). A run against a 1-branch project
    (e.g. the original Task 9 solved project) is impossible by design.
    """
    bad = []
    branches = {}
    for winding in PHASES:
        n = _read_winding_int(design, winding, PARALLEL_BRANCHES_PROP)
        branches[winding] = n
        if n != EXPECTED_STATOR_PARALLEL_BRANCHES:
            bad.append((winding, n))
    field_n = _read_winding_int(design, "Field", PARALLEL_BRANCHES_PROP)
    branches["Field"] = field_n
    if field_n != EXPECTED_FIELD_PARALLEL_BRANCHES:
        bad.append(("Field", field_n))
    if bad:
        raise RuntimeError(
            "PREFLIGHT FAILED: ParallelBranchesNum contract not met. The r2 "
            "winding contract requires stator PB=4 (36 series turns/phase, "
            "terminal amps commanded, per-sector flux x1) and field PB=1. "
            "Offenders: " + ", ".join("%s=%d" % (name, n) for name, n in bad)
            + ". Re-apply Phase 1.2 of PILOT_EXECUTION_PLAN.md before running."
        )
    return branches


def preflight_coil_sheets(design):
    """Abort unless all twelve coil sheets named in COIL_MAP exist.

    Flux extraction is the same-sign sum over exactly these sheets; if any
    one is renamed or missing the totals are silently wrong. We do not
    check for unexpected extra coil sheets -- only the twelve we use.
    """
    editor = required(lambda: design.SetActiveEditor("3D Modeler"),
                      "Activate 3D Modeler editor")
    raw_sheets = required(lambda: editor.GetObjectsInGroup("Sheets"),
                          "List sheets in group 'Sheets'")
    sheets = set(_as_text_list(raw_sheets))
    missing = [name for name in COIL_MAP if name not in sheets]
    if missing:
        raise RuntimeError(
            "PREFLIGHT FAILED: coil sheet inventory mismatch. COIL_MAP in "
            "flux_extraction_v2.py expects twelve coil sheets; the live "
            "design is missing: " + ", ".join(missing)
            + ". Re-validate build_canonical_eesm.py against the manifest "
            "before running."
        )
    return sorted(COIL_MAP.keys())


# ---------------------------------------------------------------------------
# Current injection (terminal amps, 330.01 deg frame)
# ---------------------------------------------------------------------------

def change_currents(design, point):
    """Inject terminal amps at D_AXIS_ELECTRICAL_DEG; field current literal."""
    id_terminal = float(point["id_a"])
    iq_terminal = float(point["iq_a"])
    if_field = float(point["if_a"])
    abc = abc_from_dq(id_terminal, iq_terminal, D_AXIS_ELECTRICAL_DEG)
    applied = {
        "phase_a_a": abc[0],
        "phase_b_a": abc[1],
        "phase_c_a": abc[2],
        "field_a": if_field,
    }
    boundary = required(lambda: design.GetModule("BoundarySetup"),
                        "Get BoundarySetup")
    for phase, value in zip(PHASES, abc):
        current = "%.12gA" % value
        required(lambda phase=phase, current=current: boundary.EditWindingGroup(
            phase, ["NAME:" + phase, "Type:=", "Current", "Current:=", current]),
            "Apply numeric terminal current to " + phase)
    required(lambda: boundary.EditWindingGroup("Field", [
        "NAME:Field", "Type:=", "Current", "Current:=", "%.12gA" % if_field]),
        "Apply numeric field current")
    return applied


def restore_parametric_currents(design):
    boundary = required(lambda: design.GetModule("BoundarySetup"),
                        "Get BoundarySetup")
    expressions = {"PhaseA": "I_phase_a", "PhaseB": "I_phase_b",
                   "PhaseC": "I_phase_c", "Field": "If"}
    for winding, expression in expressions.items():
        required(lambda winding=winding, expression=expression:
                 boundary.EditWindingGroup(winding, ["NAME:" + winding,
                     "Type:=", "Current", "Current:=", expression]),
                 "Restore parametric current for " + winding)


# ---------------------------------------------------------------------------
# Route C extraction and per-point raw evidence
# ---------------------------------------------------------------------------

def extract_route_c(design, point_name, area_cache):
    """Authoritative totals from flux_extraction_v2.lambda_abc_from_fields,
    plus a per-sheet raw-CSV evidence file (route C, same-sign).

    Returns (lambda_a, lambda_b, lambda_c, raw_path).
    """
    la, lb, lc = lambda_abc_from_fields(
        design, SOLUTION_NAME, area_cache=area_cache,
    )
    for value in (la, lb, lc):
        if not is_finite(value):
            raise RuntimeError("Non-finite phase flux linkage from route C")

    sheet_az = {}
    for sheet in COIL_MAP:
        az = integrate_az(design, SOLUTION_NAME, sheet)
        if not is_finite(az):
            raise RuntimeError("Non-finite A_z integral for sheet " + sheet)
        sheet_az[sheet] = az

    raw_path = os.path.join(EXPORT_DIR, point_name + "_route_c_raw.csv")
    if os.path.exists(raw_path):
        raise RuntimeError("Refusing to overwrite orphaned route C raw: " + raw_path)
    with open(raw_path, "wb") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["sheet", "phase", "sign",
                         "az_integral_wb_m", "area_m2"])
        for sheet, (phase, sign) in COIL_MAP.items():
            area = area_cache.get(sheet) if area_cache is not None else None
            writer.writerow([
                sheet, phase, "%.17g" % sign,
                "%.17g" % sheet_az[sheet],
                "%.17g" % (area if area is not None else 0.0),
            ])
    return la, lb, lc, raw_path


def read_torque_fem(design):
    output_variables = design.GetModule("OutputVariable")
    raw = required(lambda: output_variables.GetOutputVariableValue(
        TORQUE_OUTPUT_NAME, "", SOLUTION_NAME, "Magnetostatic", []),
        "Read configured torque output " + TORQUE_OUTPUT_NAME)
    return numeric_output(raw, TORQUE_OUTPUT_NAME)


# ---------------------------------------------------------------------------
# Solver evidence
# ---------------------------------------------------------------------------

def _positive_integers(text):
    return [int(item) for item in re.findall(r"(?<![.\d])-?\d+(?![.\d])", text)
            if int(item) > 0]


def export_solver_evidence(design, point_name):
    mesh_path = os.path.join(EVIDENCE_DIR, point_name + "_mesh.ms")
    convergence_path = os.path.join(EVIDENCE_DIR, point_name + "_convergence.conv")
    for path in (mesh_path, convergence_path):
        if os.path.exists(path):
            raise RuntimeError("Refusing to overwrite orphaned solver evidence: " + path)
    required(lambda: design.ExportMeshStats(SETUP_NAME, "", mesh_path, True),
             "Export measured mesh statistics")
    required(lambda: design.ExportConvergence(SETUP_NAME, "", convergence_path, True),
             "Export measured convergence history")
    for path in (mesh_path, convergence_path):
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            raise RuntimeError("Missing/empty solver evidence: " + path)
    with open(mesh_path, "r") as stream:
        total_lines = [line for line in stream.readlines() if "total" in line.lower()]
    mesh_values = []
    for line in total_lines:
        mesh_values.extend(_positive_integers(line))
    if not mesh_values:
        raise RuntimeError("Could not derive total mesh elements from " + mesh_path)
    with open(convergence_path, "r") as stream:
        convergence_lines = stream.readlines()
    pass_values = []
    in_pass_summary = False
    for line in convergence_lines:
        lowered = line.lower()
        if "number of pass" in lowered:
            in_pass_summary = True
            continue
        if in_pass_summary and "completed" in lowered:
            pass_values.extend(_positive_integers(line))
            break
    if not pass_values:
        raise RuntimeError("Could not derive adaptive passes from " + convergence_path)
    mesh_elements = max(mesh_values)
    if mesh_elements > MAX_MESH_ELEMENTS:
        raise RuntimeError(
            "Mesh element count " + str(mesh_elements)
            + " exceeds MAX_MESH_ELEMENTS=" + str(MAX_MESH_ELEMENTS)
            + ". Raise MAX_MESH_ELEMENTS in lockstep with manual mesh "
            "densification (PILOT_EXECUTION_PLAN.md Phase 3.2); do not "
            "loosen the cap without explicitly densifying the mesh."
        )
    return mesh_elements, max(pass_values), mesh_path, convergence_path


def solver_messages(project_name, design_name, solve_return):
    errors = normalize(required(lambda: oDesktop.GetMessages(project_name, design_name, 2),
                                 "Read AEDT error messages"))
    warnings = normalize(required(lambda: oDesktop.GetMessages(project_name, design_name, 1),
                                   "Read AEDT warning messages"))
    return {"solve_return": solve_return, "errors": errors or [], "warnings": warnings or []}


# ---------------------------------------------------------------------------
# Progress / resume
# ---------------------------------------------------------------------------

def append_result(result):
    exists = os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0
    with open(PROGRESS, "ab") as stream:
        writer = csv.DictWriter(stream, fieldnames=PROGRESS_FIELDS,
                                lineterminator="\r\n")
        if not exists:
            writer.writeheader()
        writer.writerow(result)


def read_progress(expected):
    if not os.path.exists(PROGRESS):
        return [], set()
    with open(PROGRESS, "r") as stream:
        reader = csv.DictReader(stream)
        if list(reader.fieldnames or []) != PROGRESS_FIELDS:
            raise RuntimeError("Refusing resume: malformed progress header")
        rows = list(reader)
    names = [row.get("point_name", "") for row in rows]
    if len(set(names)) != len(names):
        raise RuntimeError("Refusing resume: duplicated progress row")
    expected_by_name = dict((row["point_name"], row) for row in expected)
    for row in rows:
        name = row.get("point_name", "")
        if name not in expected_by_name:
            raise RuntimeError("Refusing resume: unknown progress point " + name)
        if row.get("solver_status", "").lower() != "converged":
            raise RuntimeError("Refusing resume: progress contains failed row " + name)
        frozen = expected_by_name[name]
        exact = (
            row.get("point_id") == frozen["point_id"]
            and row.get("role") == frozen["role"]
            and row.get("region") == frozen["region"]
            and all(float(row[key]) == float(frozen[key])
                    for key in ("id_a", "iq_a", "if_a"))
            and row.get("project") == PROJECT_NAME
            and row.get("design") == DESIGN_NAME
            and row.get("setup") == SETUP_NAME
            and float(row.get("d_axis_electrical_deg", "nan")) == D_AXIS_ELECTRICAL_DEG
            and int(float(row.get("pole_pairs", "0"))) == POLE_PAIRS
        )
        if not exact:
            raise RuntimeError("Refusing resume: inconsistent progress row " + name)
        expected_paths = {
            "raw_abc_flux_path": os.path.join(EXPORT_DIR, name + "_route_c_raw.csv"),
            "mesh_evidence_path": os.path.join(EVIDENCE_DIR, name + "_mesh.ms"),
            "convergence_evidence_path": os.path.join(EVIDENCE_DIR, name + "_convergence.conv"),
        }
        for key, expected_path in expected_paths.items():
            path = row.get(key, "")
            if (os.path.normcase(os.path.abspath(path))
                    != os.path.normcase(os.path.abspath(expected_path))
                    or not os.path.exists(path) or os.path.getsize(path) <= 0):
                raise RuntimeError("Refusing resume: missing raw evidence for " + name)
        try:
            message_payload = json.loads(row.get("solver_message", "{}"))
            warnings = message_payload.get("warnings", [])
        except BaseException:
            raise RuntimeError("Refusing resume: malformed solver messages for " + name)
        if any(ADAPTIVE_NONCONVERGENCE_MARKER in str(item).lower()
               for item in warnings):
            raise RuntimeError(
                "Refusing resume: adaptive convergence criteria were not met for " + name)
    return rows, set(names)


def read_prior_status(points_hash):
    if not os.path.exists(STATUS_JSON):
        if os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0:
            raise RuntimeError("Refusing resume: progress exists without pilot status")
        return None
    try:
        with open(STATUS_JSON, "r") as stream:
            prior = json.load(stream)
    except BaseException:
        raise RuntimeError("Refusing resume: pilot status is malformed")
    if not (os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0):
        raise RuntimeError("Refusing resume: status exists without progress")
    allowed = (prior.get("status") == "partial_resume_required"
        and prior.get("stage") == "idle"
        and prior.get("active_point") is None
        and not prior.get("failure")
        and not prior.get("restore_error")
        and prior.get("points_sha256") == points_hash
        and prior.get("campaign_id") == PILOT_ID)
    legacy_close = prior.get("close_error") in (None, "QuitApplication")
    if not (allowed and legacy_close):
        raise RuntimeError("Refusing resume: prior pilot status requires operator review")
    return prior


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

payload = {
    "status": "running",
    "completed": [],
    "failure": None,
    "campaign_id": PILOT_ID,
    "points_sha256": None,
    "max_new_points_per_run": MAX_NEW_POINTS_PER_RUN,
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
try:
    for directory in (RAW_ROOT, EXPORT_DIR, EVIDENCE_DIR):
        if not os.path.exists(directory):
            os.makedirs(directory)
    points = read_points()
    points_hash = sha256_file(POINTS)
    payload["points_sha256"] = points_hash
    prior_status = read_prior_status(points_hash)

    # Open the disposable copy ourselves, mirroring the proven working
    # pattern in diagnose_flux_convention.py: the runner creates the copy on
    # disk but does not tell AEDT to open it on launch. Fall back to an
    # already-active project only if the disposable copy is missing (manual
    # / interactive debugging), matching that same script's fallback order.
    if os.path.isfile(PROJECT_PATH):
        project = required(lambda: oDesktop.OpenProject(PROJECT_PATH),
                            "Open disposable pilot project " + PROJECT_PATH)
        payload["project_source"] = "opened_by_exporter"
    else:
        project = required(oDesktop.GetActiveProject, "Get active project")
        payload["project_source"] = "active_project_fallback"
    if project is None:
        raise RuntimeError(
            "No AEDT project available. Expected the disposable copy at "
            + PROJECT_PATH + " (created by run_pilot_export.ps1) or an "
            "already-active project of the same name."
        )
    project_name = required(project.GetName, "Get project name")
    if project_name != PROJECT_NAME:
        raise RuntimeError("Active project must be " + PROJECT_NAME)
    design_outcome = call(lambda: project.SetActiveDesign(DESIGN_NAME))
    if not design_outcome["ok"]:
        raise RuntimeError("No active AEDT design: " + design_outcome["error"])
    design = design_outcome["_raw"]
    design_name = required(design.GetName, "Get design name")
    if design_name != DESIGN_NAME:
        raise RuntimeError("Active design must be " + DESIGN_NAME)

    branch_inventory = preflight_winding_branches(design)
    coil_sheets_verified = preflight_coil_sheets(design)
    payload["preflight"] = {
        "stator_parallel_branches": branch_inventory,
        "expected_stator_parallel_branches": EXPECTED_STATOR_PARALLEL_BRANCHES,
        "expected_field_parallel_branches": EXPECTED_FIELD_PARALLEL_BRANCHES,
        "d_axis_electrical_deg": D_AXIS_ELECTRICAL_DEG,
        "conductors_per_sheet": CONDUCTORS_PER_SHEET,
        "model_depth_m": MODEL_DEPTH_M,
        "fractions": FRACTIONS,
        "pole_pairs": POLE_PAIRS,
        "coil_sheets_verified": coil_sheets_verified,
    }
    mark_stage(payload, None, "preflight_complete")

    progress_rows, done = read_progress(points)
    if prior_status is not None and prior_status.get("completed") != [
            row["point_name"] for row in progress_rows]:
        raise RuntimeError("Refusing resume: prior status and progress rows disagree")
    payload["completed"] = [row["point_name"] for row in progress_rows]

    area_cache = {}
    new_points = 0
    for point in points:
        if point["point_name"] in done:
            continue
        result = dict((name, "") for name in PROGRESS_FIELDS)
        result.update({
            "point_id": point["point_id"],
            "role": point["role"],
            "source": SOURCE_TAG,
            "region": point["region"],
            "id_a": point["id_a"],
            "iq_a": point["iq_a"],
            "if_a": point["if_a"],
            "provenance_id": PILOT_ID + "::" + point["point_id"],
            "point_name": point["point_name"],
            "project": project_name,
            "design": design_name,
            "setup": SETUP_NAME,
            "d_axis_electrical_deg": D_AXIS_ELECTRICAL_DEG,
            "conductors_per_sheet": CONDUCTORS_PER_SHEET,
            "model_depth_m": MODEL_DEPTH_M,
            "fractions": FRACTIONS,
            "pole_pairs": POLE_PAIRS,
            "expected_stator_parallel_branches": EXPECTED_STATOR_PARALLEL_BRANCHES,
            "expected_field_parallel_branches": EXPECTED_FIELD_PARALLEL_BRANCHES,
        })
        try:
            mark_stage(payload, point["point_name"], "apply_currents")
            applied = change_currents(design, point)
            result.update({
                "applied_phase_a_a": applied["phase_a_a"],
                "applied_phase_b_a": applied["phase_b_a"],
                "applied_phase_c_a": applied["phase_c_a"],
                "applied_field_a": applied["field_a"],
            })
            mark_stage(payload, point["point_name"], "analyze")
            solve = call(lambda: design.Analyze(SETUP_NAME))
            if not solve["ok"] or solve["value"] not in (0, None):
                raise RuntimeError(
                    "Analyze failed: " + (solve.get("error") or str(solve["value"])))

            mark_stage(payload, point["point_name"], "extract_route_c")
            phi_a, phi_b, phi_c, raw_path = extract_route_c(
                design, point["point_name"], area_cache)
            phi_d, phi_q = dq_from_abc(phi_a, phi_b, phi_c, D_AXIS_ELECTRICAL_DEG)
            if not all(is_finite(value) for value in (phi_d, phi_q)):
                raise RuntimeError("Non-finite dq flux")
            zsr = zero_sequence_ratio(phi_a, phi_b, phi_c)
            suspect = 1 if (zsr >= ZERO_SEQUENCE_SUSPECT_RATIO) else 0
            result.update({
                "lambda_a_wb": phi_a,
                "lambda_b_wb": phi_b,
                "lambda_c_wb": phi_c,
                "lambda_d_wb": phi_d,
                "lambda_q_wb": phi_q,
                "zero_sequence_ratio": zsr,
                "suspect": suspect,
                "raw_abc_flux_path": raw_path,
            })

            mark_stage(payload, point["point_name"], "read_torque")
            result["torque_fem_sector_nm"] = read_torque_fem(design)

            mark_stage(payload, point["point_name"], "export_solver_evidence")
            mesh, passes, mesh_path, conv_path = export_solver_evidence(
                design, point["point_name"])
            result.update({
                "mesh_elements": mesh,
                "adaptive_passes": passes,
                "mesh_evidence_path": mesh_path,
                "convergence_evidence_path": conv_path,
            })

            messages = solver_messages(project_name, design_name, solve["value"])
            if messages["errors"]:
                raise RuntimeError(
                    "AEDT reported unresolved solver errors: "
                    + json.dumps(messages["errors"]))
            if any(ADAPTIVE_NONCONVERGENCE_MARKER in str(item).lower()
                   for item in messages["warnings"]):
                raise RuntimeError(
                    "AEDT adaptive convergence criteria were not met: "
                    + json.dumps(messages["warnings"]))

            result["solver_status"] = "converged"
            result["converged"] = True
            result["solver_message"] = json.dumps(messages, sort_keys=True)
        except BaseException as exc:
            result["solver_status"] = "failed"
            result["converged"] = False
            result["solver_message"] = json.dumps(
                {"errors": [str(exc)]}, sort_keys=True)
            append_result(result)
            payload["status"] = "failed"
            payload["failure"] = {
                "point": point,
                "error": str(exc),
                "traceback": traceback.format_exc().splitlines(),
            }
            break
        append_result(result)
        payload["completed"].append(point["point_name"])
        mark_stage(payload, point["point_name"], "point_complete")
        new_points += 1
        if new_points >= MAX_NEW_POINTS_PER_RUN:
            break

    if payload["status"] == "running":
        payload["status"] = ("complete" if len(payload["completed"]) == len(points)
                             else "partial_resume_required")
    payload["active_point"] = None
    payload["stage"] = "idle"
    payload["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
except BaseException as exc:
    payload["status"] = "error"
    payload["failure"] = {"error": str(exc),
                          "traceback": traceback.format_exc().splitlines()}
finally:
    try:
        if "design" in globals():
            restore_parametric_currents(design)
        if "project" in globals():
            project.Save()
    except BaseException as restore_exc:
        payload["restore_error"] = str(restore_exc)
        payload["status"] = "error"
    write_status(payload)
    try:
        AddWarningMessage("Pilot export status: " + STATUS_JSON)
    except BaseException:
        print(STATUS_JSON)