"""Flux-linkage METHOD COMPARISON for the corrected PB=4 EESM model.

IronPython 2.7 inside AEDT 2025 R2 Student. Written 2026-07-22 as the
recommended next experiment from out/eesm/pilot_20260721/PILOT_FINDINGS.md.

Why this exists
---------------
The 8-point terminal-amp pilot proved:
  - the same-sign route-C COIL_MAP is correct (matches Maxwl2DV.vbs; go/return
    differencing is disproven);
  - the dq FUNDAMENTAL from route C is ~right even under load;
  - but route-C torque closure fails 1.3x-1.5x on reluctance-loaded points,
    and stator points carry a real zero-sequence spatial harmonic that the
    single-pole 2-slot/pole same-sign A_z sum aliases into the fundamental.

No sign or angle change can fix that (both disproven). The open question is
which flux-linkage METHOD to trust for stator-loaded points. This script
solves a small subset ONCE and, per point, exports THREE independent flux
readings plus torque so the choice is made offline with no further AEDT time:

  A. AEDT-native FluxLinkage(PhaseA/B/C) -- AEDT's own winding-aware flux
     linkage. It was rejected earlier, but only on the PB=1 pre-correction
     project; on the contract-correct PB=4 model it may now be right.
  B. route-C same-sign per-sheet A_z (flux_extraction_v2.lambda_abc_from_fields)
     -- validated on the d-axis anchors, suspect under stator load.
  C. Torque_FEM (Maxwell stress) -- ground-truth torque for closure tests.

Decision rule (applied offline by analyze_flux_methods.py):
  Adopt whichever flux method closes torque within ~10% at the UNSATURATED
  loaded point (pure_q_pos) AND reproduces the route-C d-axis anchors
  (field-only -> pure d-axis, correct lam_d(If) scaling). If native
  FluxLinkage closes torque, route C is retired for stator points and kept
  only as an independent d-axis cross-check.

Run model
---------
Single session, all points (the flux-convention diagnostic proved a 4-point
single-session solve works on this licence; this is 5 short points). The
companion runner run_compare_flux_methods.ps1 creates and opens a disposable
copy of the PB=4 source and launches this with -RunScriptAndExit.

Scope guard: solves and reads only. Applies NO correction, authorises NO
campaign/promotion/training. Currents are TERMINAL amps at the measured
330.01 deg d-axis, matching the pilot so results are directly comparable.
"""

import csv
import json
import math
import os
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Single source of truth for constants + route-C extraction.
from flux_extraction_v2 import (  # noqa: E402
    D_AXIS_ELECTRICAL_DEG,
    CONDUCTORS_PER_SHEET,
    MODEL_DEPTH_M,
    COIL_MAP,
    PHASES,
    abc_from_dq,
    dq_from_abc,
    zero_sequence_ratio,
    lambda_abc_from_fields,
)

PROJECT_NAME = "eesm_fluxcmp_01"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
FIELD_WINDING = "Field"
TORQUE_OUTPUT_NAME = "Torque_FEM"
POLE_PAIRS = 2

EXPECTED_STATOR_PB = 4
EXPECTED_FIELD_PB = 1
PARALLEL_BRANCHES_PROP = "Number of Parallel Branches"

OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "flux_method_comparison")
RAW_DIR = os.path.join(OUT_DIR, "raw")
EVIDENCE_JSON = os.path.join(OUT_DIR, "flux_method_evidence.json")

NATIVE_EXPRESSIONS = [
    "FluxLinkage(PhaseA)", "FluxLinkage(PhaseB)", "FluxLinkage(PhaseC)",
]

# Reuse the pilot's exact currents (TERMINAL amps) so the two datasets are
# directly comparable. Subset: two field-only d-axis anchors, one pure-d,
# the key unsaturated loaded point (pure_q), and one reluctance point.
# (name, id_a, iq_a, if_a, role_note)
COMPARISON_POINTS = [
    ("field_only_3a", 0.0, 0.0, 3.0, "d-axis anchor (If=3)"),
    ("field_only_5a", 0.0, 0.0, 5.0, "d-axis anchor (If=5)"),
    ("pure_d_neg", -30.0, 0.0, 2.0, "pure d, reluctance sign check"),
    ("pure_q_pos", 0.0, 30.0, 2.0, "UNSATURATED loaded point - decides the method"),
    ("rated_ish", -30.0, 45.0, 4.0, "reluctance-loaded (route C gave k~0.67)"),
]


# ---------------------------------------------------------------------------
# small helpers (self-contained; no import of the top-level exporter)
# ---------------------------------------------------------------------------

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(k), normalize(v)) for k, v in value.items())
    try:
        return [normalize(v) for v in list(value)]
    except BaseException:
        return str(value)


def required(label, thunk):
    try:
        return thunk()
    except BaseException as exc:
        raise RuntimeError(label + ": " + str(exc))


def is_finite(x):
    try:
        return not (math.isnan(x) or math.isinf(x))
    except BaseException:
        return False


def numeric_output(value, name):
    try:
        number = float(str(value).split()[0])
    except BaseException:
        raise RuntimeError(name + " not a plain numeric value")
    if not is_finite(number):
        raise RuntimeError(name + " non-finite")
    return number


# ---------------------------------------------------------------------------
# preflight (same contract as the pilot exporter)
# ---------------------------------------------------------------------------

def _read_pb(design, winding):
    node = required(
        "Excitations child " + winding,
        lambda: design.GetChildObject("Excitations").GetChildObject(winding),
    )
    raw = required(
        "Read PB for " + winding,
        lambda: node.GetPropValue(PARALLEL_BRANCHES_PROP),
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
        raise RuntimeError("Could not parse PB='" + text + "' for " + winding)
    return int(digits)


def preflight(design):
    bad = []
    branches = {}
    for w in PHASES:
        n = _read_pb(design, w)
        branches[w] = n
        if n != EXPECTED_STATOR_PB:
            bad.append((w, n))
    fn = _read_pb(design, FIELD_WINDING)
    branches[FIELD_WINDING] = fn
    if fn != EXPECTED_FIELD_PB:
        bad.append((FIELD_WINDING, fn))
    if bad:
        raise RuntimeError(
            "PREFLIGHT FAILED: ParallelBranchesNum contract not met "
            "(stator must be 4, field 1). Offenders: "
            + ", ".join("%s=%d" % (n, v) for n, v in bad)
            + ". This is not the PB=4 pilot source."
        )
    editor = required("3D Modeler", lambda: design.SetActiveEditor("3D Modeler"))
    sheets = set(str(s) for s in list(required(
        "Sheets group", lambda: editor.GetObjectsInGroup("Sheets"))))
    missing = [s for s in COIL_MAP if s not in sheets]
    if missing:
        raise RuntimeError("PREFLIGHT FAILED: missing coil sheets: "
                           + ", ".join(missing))
    return branches


# ---------------------------------------------------------------------------
# native FluxLinkage read (mirrors diagnose_flux_convention.read_report_expressions)
# ---------------------------------------------------------------------------

def read_native_flux_linkage(design, point_name):
    report = design.GetModule("ReportSetup")
    report_name = "CMP_Native_Flux_" + point_name
    existing = [str(x) for x in list(report.GetAllReportNames())]
    if report_name in existing:
        report.DeleteReports([report_name])
    report.CreateReport(
        report_name, "Magnetostatic", "Data Table", SOLUTION_NAME, [],
        ["fractions:=", ["All"]],
        ["X Component:=", "fractions", "Y Component:=", list(NATIVE_EXPRESSIONS)],
    )
    csv_path = os.path.join(RAW_DIR, point_name + "_native_flux.csv")
    report.ExportToFile(report_name, csv_path)
    report.DeleteReports([report_name])
    if not (os.path.exists(csv_path) and os.path.getsize(csv_path) > 0):
        raise RuntimeError("native flux export produced no file")
    stream = open(csv_path, "r")
    try:
        lines = [ln.strip() for ln in stream.readlines() if ln.strip()]
    finally:
        stream.close()
    if len(lines) < 2:
        raise RuntimeError("native flux export had no data row")
    header = [h.strip().strip('"') for h in lines[0].split(",")]
    values = [v.strip().strip('"') for v in lines[1].split(",")]
    row = {}
    for key, value in zip(header, values):
        try:
            row[key] = float(value)
        except ValueError:
            row[key] = value

    def pick(phase):
        for key in row:
            if ("FluxLinkage" in key and phase in key
                    and isinstance(row[key], float)):
                return row[key]
        raise RuntimeError("native FluxLinkage(" + phase + ") not in export header")

    return pick("PhaseA"), pick("PhaseB"), pick("PhaseC"), csv_path


# ---------------------------------------------------------------------------
# current injection (TERMINAL amps at the measured d-axis)
# ---------------------------------------------------------------------------

def apply_currents(design, id_a, iq_a, if_a):
    abc = abc_from_dq(id_a, iq_a, D_AXIS_ELECTRICAL_DEG)
    boundary = design.GetModule("BoundarySetup")
    for phase, value in zip(PHASES, abc):
        boundary.EditWindingGroup(phase, [
            "NAME:" + phase, "Type:=", "Current", "Current:=", "%.12gA" % value])
    boundary.EditWindingGroup(FIELD_WINDING, [
        "NAME:" + FIELD_WINDING, "Type:=", "Current", "Current:=", "%.12gA" % if_a])
    return {"phase_a_a": abc[0], "phase_b_a": abc[1], "phase_c_a": abc[2],
            "field_a": if_a}


def restore_parametric(design):
    boundary = design.GetModule("BoundarySetup")
    expr = {"PhaseA": "I_phase_a", "PhaseB": "I_phase_b",
            "PhaseC": "I_phase_c", "Field": "If"}
    for w, e in expr.items():
        boundary.EditWindingGroup(w, ["NAME:" + w, "Type:=", "Current",
                                      "Current:=", e])


# ---------------------------------------------------------------------------
# per-point solve + three flux readings + torque
# ---------------------------------------------------------------------------

def probe(design, name, id_a, iq_a, if_a, note, area_cache):
    rec = {"point": name, "id_a": id_a, "iq_a": iq_a, "if_a": if_a, "note": note}
    rec["applied"] = apply_currents(design, id_a, iq_a, if_a)

    started = time.time()
    solve_rc = design.Analyze(SETUP_NAME)
    rec["solve_seconds"] = time.time() - started
    rec["solve_return"] = normalize(solve_rc)

    # A. native FluxLinkage(PhaseX)
    try:
        na, nb, nc, npath = read_native_flux_linkage(design, name)
        nd, nq = dq_from_abc(na, nb, nc, D_AXIS_ELECTRICAL_DEG)
        rec["native"] = {
            "lambda_abc_wb": [na, nb, nc], "lambda_d_wb": nd, "lambda_q_wb": nq,
            "zero_sequence_ratio": zero_sequence_ratio(na, nb, nc),
            "csv": npath, "ok": True}
    except BaseException as exc:
        rec["native"] = {"ok": False, "error": str(exc)}

    # B. route C same-sign per-sheet A_z
    try:
        ca, cb, cc = lambda_abc_from_fields(
            design, SOLUTION_NAME, area_cache=area_cache)
        cd, cq = dq_from_abc(ca, cb, cc, D_AXIS_ELECTRICAL_DEG)
        rec["route_c"] = {
            "lambda_abc_wb": [ca, cb, cc], "lambda_d_wb": cd, "lambda_q_wb": cq,
            "zero_sequence_ratio": zero_sequence_ratio(ca, cb, cc), "ok": True}
    except BaseException as exc:
        rec["route_c"] = {"ok": False, "error": str(exc)}

    # C. Torque_FEM (sector), full machine = x4
    try:
        raw = design.GetModule("OutputVariable").GetOutputVariableValue(
            TORQUE_OUTPUT_NAME, "", SOLUTION_NAME, "Magnetostatic", [])
        t_sector = numeric_output(raw, TORQUE_OUTPUT_NAME)
        rec["torque_fem_sector_nm"] = t_sector
        rec["torque_fem_full_nm"] = t_sector * 4.0
    except BaseException as exc:
        rec["torque_error"] = str(exc)

    # torque closure per method (full machine):
    #   T_dq_full = 1.5 * p * (ld*iq - lq*id)   [NO extra x4]
    # Route-C lambda is the full-machine TERMINAL flux linkage (one PB=4 branch
    # = one pole = the sector, so lambda_sector = lambda_terminal, x1 -- see
    # flux_extraction_v2 NOTE 1), and iq/id are terminal amps. The dq identity
    # with terminal quantities is ALREADY the full-machine torque. Torque_FEM,
    # by contrast, is per-sector and IS multiplied by 4 to reach full machine.
    # A previous version multiplied T_dq by 4 as well, which double-counted and
    # inflated every residual by exactly 4 (fixed 2026-07-22, confirmed by the
    # pure_q/q_neg mirror pair).
    tfull = rec.get("torque_fem_full_nm")
    for tag in ("native", "route_c"):
        m = rec.get(tag)
        if m and m.get("ok") and tfull is not None:
            tdq = 1.5 * POLE_PAIRS * (
                m["lambda_d_wb"] * iq_a - m["lambda_q_wb"] * id_a)
            m["torque_dq_full_nm"] = tdq
            m["torque_residual"] = ((tdq - tfull) / tfull
                                    if abs(tfull) > 1e-6 else None)
    return rec


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

payload = {
    "status": "running",
    "artifact_type": "flux_method_comparison",
    "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "d_axis_electrical_deg": D_AXIS_ELECTRICAL_DEG,
    "conductors_per_sheet": CONDUCTORS_PER_SHEET,
    "model_depth_m": MODEL_DEPTH_M,
    "pole_pairs": POLE_PAIRS,
    "currents_are": "terminal_amps",
    "campaign_authorized": False,
    "qualification_authorized": False,
    "training_authorized": False,
    "points": [],
}
try:
    ensure_dir(RAW_DIR)
    if not os.path.isfile(PROJECT_PATH):
        raise RuntimeError(
            "Disposable copy not found at " + PROJECT_PATH
            + ". run_compare_flux_methods.ps1 creates it from the PB=4 source.")
    project = required("OpenProject", lambda: oDesktop.OpenProject(PROJECT_PATH))
    if project is None:
        raise RuntimeError("OpenProject returned None")
    payload["project"] = str(project.GetName())
    design = required("SetActiveDesign",
                      lambda: project.SetActiveDesign(DESIGN_NAME))
    if design is None:
        raise RuntimeError("Design " + DESIGN_NAME + " not found")

    payload["preflight"] = preflight(design)

    area_cache = {}
    for name, id_a, iq_a, if_a, note in COMPARISON_POINTS:
        payload["points"].append(
            probe(design, name, id_a, iq_a, if_a, note, area_cache))
        with open(EVIDENCE_JSON, "w") as stream:      # checkpoint each point
            json.dump(normalize(payload), stream, indent=2)

    payload["status"] = "collected"
except BaseException as exc:
    payload["status"] = "error"
    payload["error"] = str(exc)
    payload["traceback"] = traceback.format_exc().splitlines()
finally:
    try:
        if "design" in globals():
            restore_parametric(design)
        if "project" in globals():
            project.Save()
    except BaseException as rexc:
        payload["restore_error"] = str(rexc)
    with open(EVIDENCE_JSON, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)
    try:
        AddWarningMessage("Flux method comparison: " + EVIDENCE_JSON)
    except BaseException:
        print(EVIDENCE_JSON)
