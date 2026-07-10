"""OFF-GRID FEM VALIDATION SOLVER (run inside AEDT, Automation -> Run Script).

Generates 20 deterministic off-grid (Id, Iq) current pairs that fall at
midpoints of the 40x40 training grid cells (so they interpolate the
training set but never coincide with a training point), then for each:

  1. Convert (Id, Iq) -> (Ia, Ib, Ic) via abc_from_dq with theta_re=0
     (same transform as gui_full_magnetostatic_export.py).
  2. Apply currents via minimal EditWindingGroup (confirmed-working path
     from probe_isolate_analyze_break -> single_point_verify).
  3. design.Analyze("Setup_MagProbe") with the coarsened mesh + EditSetup
     recipe (MaximumPasses=1, PercentRefinement=10, slider=1) baked in
     idempotently at the start.
  4. Delete/recreate MCP_OffGrid_ABC report, ExportToFile to per-point CSV.
  5. Park-transform the exported ABC flux linkage back to (Phi_d, Phi_q).
  6. Append row to off_grid_fem_results.csv.

Pure stdlib (no numpy/torch/sklearn) because this runs in AEDT's IronPython,
which does NOT have those packages. The model-prediction + comparison half
lives in compare_off_grid_predictions.py and runs in the venv python.

Output:
  tmp/aedt_jobs/off_grid_validation/off_grid_fem_results.csv
      Header: Id,Iq,Phi_d,Phi_q
  tmp/aedt_jobs/off_grid_validation/point_exports/point_NNN_fluxlinkage_abc.csv
  tmp/aedt_jobs/off_grid_validation/off_grid_validation.json

Initial state assumption:
  Maxwell2DDesign4 is in the state left by the 40x40 full sweep
  (SurfApprox ops deleted, slider=1 mesh, Setup_MagProbe MaximumPasses=1).
  This script re-applies those settings idempotently in case they didn't
  persist, so it's safe to run even if a fresh copy of the project was
  loaded.

Run from AEDT 2025 R2 Student: Automation -> Run Script.
Then run compare_off_grid_predictions.py from the repo root with the venv
python.
"""

import csv
import json
import math
import os
import random
import traceback

# ---------------------------------------------------------------------------
# Paths and constants.
# ---------------------------------------------------------------------------

try:
    _REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _REPO_ROOT = r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline"
PROJECT_ROOT = os.path.join(_REPO_ROOT, "aedt_mcp")
PROJECT_PATH = os.path.join(
    PROJECT_ROOT, "tmp", "aedt_projects", "ipm_1_probe", "ipm_1.aedt"
)
JOB_ID = "off_grid_validation"
# Bump when fixing IronPython incompatibilities so result JSON is easy to audit.
SCRIPT_VERSION = "2026-07-09-newline-fix"
JOB_DIR = os.path.join(PROJECT_ROOT, "tmp", "aedt_jobs", JOB_ID)
POINT_DIR = os.path.join(JOB_DIR, "point_exports")
OUT_CSV = os.path.join(JOB_DIR, "off_grid_fem_results.csv")
OUT_JSON = os.path.join(JOB_DIR, "off_grid_validation.json")

PROJECT_NAME = "ipm_1"
DESIGN_NAME = "Maxwell2DDesign4"
SETUP_NAME = "Setup_MagProbe"
SOLUTION_NAME = "Setup_MagProbe : LastAdaptive"
REPORT_NAME = "MCP_OffGrid_ABC"
REPORT_TYPE = "Magnetostatic"
DISPLAY_TYPE = "Data Table"
THETA_RE = 0.0  # matches the full sweep - Park frame aligned with PhaseA

PHASES = ("PhaseA", "PhaseB", "PhaseC")
EXPRESSIONS = [
    "FluxLinkage(PhaseA)",
    "FluxLinkage(PhaseB)",
    "FluxLinkage(PhaseC)",
]

# Mesh / setup recipe (verified - see single_point_verify.py / coarsen).
MESH_OPS_TO_DELETE = ("SurfApprox_Mag", "SurfApprox_Main", "CylindricalGap1")
COARSEN_SLIDER_LEVEL = 1
SETUP_MAX_PASSES = 1
SETUP_MIN_PASSES = 1
SETUP_PERCENT_REFINEMENT = 10

# Off-grid point generation: 20 deterministic pairs at cell midpoints of the
# 40x40 training grid (Id step ~ 15.38A, Iq step ~ 7.69 A). Half-integer cell
# indices ensure no point coincides with a training node.
N_POINTS = 20
GRID_I_STEP = 600.0 / 39.0
GRID_Q_STEP = 300.0 / 39.0
ID_RANGE = (-300.0, 300.0)
IQ_RANGE = (0.0, 300.0)


def generate_off_grid_points(n_points=N_POINTS, seed=7):
    """Deterministic. Returns list of (Id, Iq) tuples at random cell midpoints
    of the 40x40 training grid."""
    rng = random.Random(seed)
    pts = []
    for _ in range(n_points):
        i_idx = int(rng.random() * 39) + 0.5  # half-integer in [0.5, 39.5)
        id_v = ID_RANGE[0] + i_idx * GRID_I_STEP
        j_idx = int(rng.random() * 39) + 0.5
        iq_v = IQ_RANGE[0] + j_idx * GRID_Q_STEP
        pts.append((round(id_v, 6), round(iq_v, 6)))
    return pts


# ---------------------------------------------------------------------------
# Stdlib helpers (no numpy/torch/lightweight libs).
# ---------------------------------------------------------------------------

def warn(message):
    try:
        AddWarningMessage(message)
    except BaseException:
        print(message)


def safe_list(fn):
    try:
        return list(fn())
    except BaseException:
        return []


def get_or_open_project():
    projects = safe_list(oDesktop.GetProjectList)
    if PROJECT_NAME in projects:
        return PROJECT_NAME
    if os.path.exists(PROJECT_PATH):
        try:
            oDesktop.OpenProject(PROJECT_PATH)
        except BaseException as exc:
            warn("OpenProject warning: " + str(exc))
    projects = safe_list(oDesktop.GetProjectList)
    if PROJECT_NAME in projects:
        return PROJECT_NAME
    return None


def normalize(value):
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def call(fn):
    try:
        return {"ok": True, "value": normalize(fn())}
    except BaseException as exc:
        return {
            "ok": False,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-8:],
        }


def messages_snapshot():
    snap = {}
    for level in (0, 1, 2, 3):
        snap[str(level)] = call(
            lambda level=level: oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, level)
        )
    snap["global_errors"] = call(lambda: oDesktop.GetMessages("", "", 2))
    return snap


def abc_from_dq(id_value, iq_value, theta_re):
    ia = math.cos(theta_re) * id_value - math.sin(theta_re) * iq_value
    ib = math.cos(theta_re - 2.0 * math.pi / 3.0) * id_value \
        - math.sin(theta_re - 2.0 * math.pi / 3.0) * iq_value
    ic = -(ia + ib)
    return ia, ib, ic


def dq_from_abc(phi_a, phi_b, phi_c, theta_re):
    phi_d = (2.0 / 3.0) * (
        phi_a * math.cos(theta_re)
        + phi_b * math.cos(theta_re - 2.0 * math.pi / 3.0)
        + phi_c * math.cos(theta_re + 2.0 * math.pi / 3.0)
    )
    phi_q = (2.0 / 3.0) * (
        -phi_a * math.sin(theta_re)
        - phi_b * math.sin(theta_re - 2.0 * math.pi / 3.0)
        - phi_c * math.sin(theta_re + 2.0 * math.pi / 3.0)
    )
    return phi_d, phi_q


def currents_text(ia, ib, ic):
    return ("%.12gA" % ia, "%.12gA" % ib, "%.12gA" % ic)


# ---------------------------------------------------------------------------
# Mesh + setup recipe (idempotent re-application so this script is safe to
# run even if a fresh project copy is loaded).
# ---------------------------------------------------------------------------

def reapply_mesh_and_setup(mesh_module, analysis):
    """Same recipe as single_point_verify.py / gui_full_magnetostatic_export.py
    Step 0. Idempotent - all failures are captured not raised."""
    existing_probe = call(lambda: mesh_module.GetOperationNames("All"))
    existing = existing_probe.get("value") or []
    delete_results = {}
    for op in MESH_OPS_TO_DELETE:
        if op in existing:
            delete_results[op] = call(lambda op=op: mesh_module.DeleteOp([op]))
        else:
            delete_results[op] = {"ok": True, "value": "already_absent"}
    coarsen_args = [
        "NAME:MeshSettings",
        ["NAME:GlobalSurfApproximation",
         "CurvedSurfaceApproxChoice:=", "UseSlider",
         "SliderMeshSettings:=", COARSEN_SLIDER_LEVEL],
        ["NAME:GlobalModelRes", "UseAutoLength:=", True],
        "MeshMethod:=", "AnsoftClassic",
    ]
    initial = call(lambda: mesh_module.InitialMeshSettings(coarsen_args))
    edit_args = [
        "NAME:" + SETUP_NAME,
        "Enabled:=", True,
        ["NAME:MeshLink", "ImportMesh:=", False],
        "MaximumPasses:=", SETUP_MAX_PASSES,
        "MinimumPasses:=", SETUP_MIN_PASSES,
        "MinimumConvergedPasses:=", 1,
        "PercentRefinement:=", SETUP_PERCENT_REFINEMENT,
        "SolveFieldOnly:=", False,
        "PercentError:=", 1,
        "SolveMatrixAtLast:=", True,
        "UseIterativeSolver:=", False,
        "RelativeResidual:=", 1e-06,
        "NonLinearResidual:=", 0.0001,
        "SmoothBHCurve:=", False,
        ["NAME:MuOption", "MuNonLinearBH:=", True],
    ]
    edit = call(lambda: analysis.EditSetup(SETUP_NAME, edit_args))
    return {"delete_ops": delete_results, "initial_mesh": initial,
            "edit_setup": edit, "existing_ops_probe": existing_probe}


# ---------------------------------------------------------------------------
# Per-point solver cycle.
# ---------------------------------------------------------------------------

def apply_currents(boundary, ia, ib, ic):
    texts = currents_text(ia, ib, ic)
    for phase, text in zip(PHASES, texts):
        payload = ["NAME:" + phase, "Type:=", "Current", "Current:=", text]
        res = call(lambda p=phase, pl=payload: boundary.EditWindingGroup(p, pl))
        if not res.get("ok"):
            return {"ok": False, "phase": phase, "result": res}
    return {"ok": True}


def delete_report_if_present(report):
    names = call(report.GetAllReportNames)
    if not names.get("ok"):
        return names
    if REPORT_NAME in (names.get("value") or []):
        return call(lambda: report.DeleteReports([REPORT_NAME]))
    return {"ok": True, "value": "not_present"}


def parse_flux_csv(path):
    """Bare CSV parser (no pandas). Returns last row's (PhiA, PhiB, PhiC)."""
    with open(path, "r") as f:
        reader = csv.reader(f)
        try:
            header = next(reader)
        except StopIteration:
            raise RuntimeError("Empty flux CSV: " + path)
        rows = list(reader)
    if len(header) < 4:
        raise RuntimeError("Expected >=4 columns in flux CSV, got header="
                           + str(header))
    if not rows:
        raise RuntimeError("Flux CSV had no data rows: " + path)
    last = rows[-1]
    if len(last) < 4:
        raise RuntimeError("Flux CSV row had <4 cols: " + str(last))
    # Columns: ["fractions []", "FluxLinkage(PhaseA) [Wb]",
    #           "FluxLinkage(PhaseB) [Wb]", "FluxLinkage(PhaseC) [Wb]"]
    return float(last[1]), float(last[2]), float(last[3])


def solve_one_point(design, boundary, report, point_index, id_value, iq_value):
    """Returns (row, failure) where row = (Id, Iq, Phi_d, Phi_q)."""
    ia, ib, ic = abc_from_dq(id_value, iq_value, THETA_RE)

    warn("OffGrid %d/%d: Id=%.4f Iq=%.4f -> Ia=%.4f Ib=%.4f Ic=%.4f"
         % (point_index, N_POINTS, id_value, iq_value, ia, ib, ic))
    applied = apply_currents(boundary, ia, ib, ic)
    if not applied.get("ok", False):
        return None, {
            "point_index": point_index, "id": id_value, "iq": iq_value,
            "ia": ia, "ib": ib, "ic": ic,
            "stage": "apply_current", "apply_result": applied,
            "messages": messages_snapshot(),
        }

    analyzed = call(lambda: design.Analyze(SETUP_NAME))
    # AEDT Analyze returns long: 0 on success.
    if not (analyzed.get("ok") and analyzed.get("value") == 0):
        return None, {
            "point_index": point_index, "id": id_value, "iq": iq_value,
            "ia": ia, "ib": ib, "ic": ic,
            "stage": "analyze", "analyze_result": analyzed,
            "validate_after_apply": call(design.ValidateDesign),
            "messages": messages_snapshot(),
        }

    delete_report_if_present(report)
    created = call(lambda: report.CreateReport(
        REPORT_NAME, REPORT_TYPE, DISPLAY_TYPE, SOLUTION_NAME,
        [], ["fractions:=", ["All"]],
        ["X Component:=", "fractions", "Y Component:=", EXPRESSIONS],
    ))
    if not created.get("ok"):
        return None, {
            "point_index": point_index, "id": id_value, "iq": iq_value,
            "stage": "create_report", "create_result": created,
            "messages": messages_snapshot(),
        }
    point_csv = os.path.join(
        POINT_DIR, "point_%03d_fluxlinkage_abc.csv" % point_index
    )
    exported = call(lambda: report.ExportToFile(REPORT_NAME, point_csv))
    if not (exported.get("ok") and os.path.exists(point_csv)
            and os.path.getsize(point_csv) > 0):
        return None, {
            "point_index": point_index, "id": id_value, "iq": iq_value,
            "stage": "export", "export_result": exported,
            "messages": messages_snapshot(),
        }
    try:
        phi_a, phi_b, phi_c = parse_flux_csv(point_csv)
    except BaseException as exc:
        return None, {
            "point_index": point_index, "id": id_value, "iq": iq_value,
            "stage": "parse_csv", "error": str(exc),
            "messages": messages_snapshot(),
        }
    phi_d, phi_q = dq_from_abc(phi_a, phi_b, phi_c, THETA_RE)
    return (id_value, iq_value, phi_d, phi_q), None


# ---------------------------------------------------------------------------
# Top-level pipeline.
# ---------------------------------------------------------------------------

def main():
    if not os.path.exists(JOB_DIR):
        os.makedirs(JOB_DIR)
    if not os.path.exists(POINT_DIR):
        os.makedirs(POINT_DIR)

    project_name = get_or_open_project()
    if not project_name:
        return {
            "status": "error",
            "message": "No AEDT project is open and ipm_1.aedt could not be "
                       "opened from " + PROJECT_PATH,
            "project_path": PROJECT_PATH,
        }
    project = oDesktop.SetActiveProject(project_name)
    design = project.SetActiveDesign(DESIGN_NAME)
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    mesh_module = design.GetModule("MeshSetup")
    report = design.GetModule("ReportSetup")

    payload = {
        "script_version": SCRIPT_VERSION,
        "project": project_name,
        "design": DESIGN_NAME,
        "setup": SETUP_NAME,
        "theta_re": THETA_RE,
        "n_points": N_POINTS,
        "out_csv": OUT_CSV,
        "prestate": {
            "solution_type": call(design.GetSolutionType),
            "validate_before": call(design.ValidateDesign),
            "reports_before": call(report.GetAllReportNames),
            "messages_before": messages_snapshot(),
        },
    }

    warn("OffGridValidation: re-applying mesh + setup recipe (idempotent)")
    payload["mesh_setup_recipe"] = reapply_mesh_and_setup(mesh_module, analysis)

    points = generate_off_grid_points(N_POINTS, seed=7)
    payload["points"] = [{"index": i + 1, "id": p[0], "iq": p[1]}
                         for i, p in enumerate(points)]

    # Write CSV header.
    # IronPython's open() does not accept newline= (CPython 3-only kwarg).
    with open(OUT_CSV, "w") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Id", "Iq", "Phi_d", "Phi_q"])

    completed = []
    failures = []
    for i, (id_v, iq_v) in enumerate(points, start=1):
        row, failure = solve_one_point(
            design, boundary, report, i, id_v, iq_v
        )
        if failure is not None:
            failures.append(failure)
            # Stop at first failure for diagnostic clarity.
            payload["completed_count"] = len(completed)
            payload["first_failure"] = failure
            payload["status"] = "failed_at_point_" + str(i)
            return payload
        with open(OUT_CSV, "a") as f:
            w = csv.writer(f, lineterminator="\n")
            w.writerow([("%.6f" % row[0]), ("%.6f" % row[1]),
                        ("%.12g" % row[2]), ("%.12g" % row[3])])
        completed.append(row)
        warn("OffGrid %d done: Phi_d=%.6e Phi_q=%.6e" %
             (i, row[2], row[3]))

    payload["completed_count"] = len(completed)
    payload["first_failure"] = None
    payload["status"] = "ok"
    payload["poststate"] = {
        "messages_after": messages_snapshot(),
        "validate_after": call(design.ValidateDesign),
    }
    return payload


try:
    payload = main()
    if "status" not in payload:
        payload["status"] = "ok"
except BaseException as exc:
    payload = {
        "status": "error",
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines(),
        "out_csv": OUT_CSV,
        "messages": messages_snapshot(),
    }

with open(OUT_JSON, "w") as f:
    json.dump(payload, f, indent=2)
warn("Wrote off-grid FEM validation result to: " + OUT_JSON)
warn("Truth CSV (for compare_off_grid_predictions.py): " + OUT_CSV)