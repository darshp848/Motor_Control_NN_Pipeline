"""LUT scheduler FEM audit (run inside AEDT, Automation -> Run Script).

Reads out/audit/lut_audit_commands.csv (repo-relative) and for each row with
needs_fem=true:

  1. Apply (Id, Iq) via the same minimal winding path as off-grid validation
  2. Analyze Setup_MagProbe
  3. Export ABC flux, Park to dq
  4. Append Id,Iq,Phi_d,Phi_q,command_id to lut_audit_fem_results.csv

Pure stdlib / IronPython-safe. Copy results to out/audit/ then run
compare_lut_audit.py in the venv.

Stage 0: protocol freeze. FEM hours optional until you need torque closure.
"""

import csv
import json
import math
import os
import traceback

try:
    _REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _REPO_ROOT = r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline"

PROJECT_ROOT = os.path.join(_REPO_ROOT, "aedt_mcp")
PROJECT_PATH = os.path.join(
    PROJECT_ROOT, "tmp", "aedt_projects", "ipm_1_probe", "ipm_1.aedt"
)
JOB_ID = "lut_scheduler_audit"
SCRIPT_VERSION = "2026-07-10-stage0-lut-audit"
JOB_DIR = os.path.join(PROJECT_ROOT, "tmp", "aedt_jobs", JOB_ID)
POINT_DIR = os.path.join(JOB_DIR, "point_exports")
# Prefer commands from repo out/audit; fall back to job dir copy.
COMMANDS_CSV = os.path.join(_REPO_ROOT, "out", "audit", "lut_audit_commands.csv")
OUT_CSV = os.path.join(JOB_DIR, "lut_audit_fem_results.csv")
OUT_JSON = os.path.join(JOB_DIR, "lut_audit_fem.json")

PROJECT_NAME = "ipm_1"
DESIGN_NAME = "Maxwell2DDesign4"
SETUP_NAME = "Setup_MagProbe"
SOLUTION_NAME = "Setup_MagProbe : LastAdaptive"
REPORT_NAME = "MCP_LutAudit_ABC"
REPORT_TYPE = "Magnetostatic"
DISPLAY_TYPE = "Data Table"
THETA_RE = 0.0
PHASES = ("PhaseA", "PhaseB", "PhaseC")
EXPRESSIONS = [
    "FluxLinkage(PhaseA)",
    "FluxLinkage(PhaseB)",
    "FluxLinkage(PhaseC)",
]
MESH_OPS_TO_DELETE = ("SurfApprox_Mag", "SurfApprox_Main", "CylindricalGap1")
COARSEN_SLIDER_LEVEL = 1
SETUP_MAX_PASSES = 1
SETUP_MIN_PASSES = 1
SETUP_PERCENT_REFINEMENT = 10


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


def call(fn, default=None):
    try:
        return fn()
    except BaseException:
        return default


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


def reapply_mesh_and_setup(mesh_module, analysis):
    recipe = {}
    for name in MESH_OPS_TO_DELETE:
        try:
            mesh_module.DeleteOp(name)
            recipe[name] = "deleted"
        except BaseException:
            recipe[name] = "absent_or_failed"
    try:
        mesh_module.InitialMeshSettings.SliderMeshSettings = COARSEN_SLIDER_LEVEL
        recipe["slider"] = COARSEN_SLIDER_LEVEL
    except BaseException as exc:
        recipe["slider_error"] = str(exc)
    try:
        analysis.EditSetup(SETUP_NAME, [
            "NAME:" + SETUP_NAME,
            "Enabled:=", True,
            "MaximumPasses:=", SETUP_MAX_PASSES,
            "MinimumPasses:=", SETUP_MIN_PASSES,
            "PercentRefinement:=", SETUP_PERCENT_REFINEMENT,
        ])
        recipe["setup"] = "edited"
    except BaseException as exc:
        recipe["setup_error"] = str(exc)
    return recipe


def read_commands(path):
    rows = []
    with open(path, "r") as f:
        r = csv.DictReader(f)
        for row in r:
            needs = str(row.get("needs_fem", "")).strip().lower()
            if needs not in ("1", "true", "yes", "y"):
                continue
            try:
                id_v = float(row["Id_ref_A"])
                iq_v = float(row["Iq_ref_A"])
            except Exception:
                continue
            if id_v != id_v or iq_v != iq_v:  # NaN
                continue
            rows.append({
                "command_id": row.get("command_id", ""),
                "Id": id_v,
                "Iq": iq_v,
            })
    return rows


def apply_currents(boundary, id_v, iq_v):
    ia, ib, ic = abc_from_dq(id_v, iq_v, THETA_RE)
    # Minimal EditWindingGroup path (proven for off-grid).
    for phase, val in zip(PHASES, (ia, ib, ic)):
        boundary.EditWindingGroup(
            [
                "NAME:Winding1",
                "Type:=", "Solid",
                "FillFactor:=", "0",
            ],
            [
                "NAME:" + phase,
                "Current:=", ("%.12gA" % val),
            ],
        )
    return ia, ib, ic


def export_phi_abc(report, out_csv):
    try:
        report.DeleteReports([REPORT_NAME])
    except BaseException:
        pass
    report.CreateReport(
        REPORT_NAME, REPORT_TYPE, DISPLAY_TYPE, SOLUTION_NAME,
        ["Domain:=", "Sweep"],
        ["Freq:=", ["All"]],
        {"Context": PHASES[0]},
        EXPRESSIONS,
    )
    report.ExportToFile(REPORT_NAME, out_csv)
    # Parse last numeric row of each expression — format varies; use simple scan.
    with open(out_csv, "r") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    # Expect columns including FluxLinkage values; take last data row floats.
    data_lines = [ln for ln in lines if not ln.lower().startswith("freq")]
    if not data_lines:
        data_lines = lines[1:] if len(lines) > 1 else lines
    parts = data_lines[-1].replace('"', "").split(",")
    nums = []
    for p in parts:
        try:
            nums.append(float(p))
        except Exception:
            continue
    if len(nums) < 3:
        raise RuntimeError("Could not parse ABC flux from " + out_csv)
    # Prefer last 3 floats as Phi_a,b,c
    return nums[-3], nums[-2], nums[-1]


def main():
    if not os.path.exists(JOB_DIR):
        os.makedirs(JOB_DIR)
    if not os.path.exists(POINT_DIR):
        os.makedirs(POINT_DIR)

    if not os.path.exists(COMMANDS_CSV):
        return {
            "status": "error",
            "message": "Commands CSV missing: " + COMMANDS_CSV,
            "hint": "Run audit_lut_scheduler.py in the venv first.",
        }

    project_name = get_or_open_project()
    if not project_name:
        return {
            "status": "error",
            "message": "No AEDT project open and could not open ipm_1.aedt",
            "project_path": PROJECT_PATH,
        }
    project = oDesktop.SetActiveProject(project_name)
    design = project.SetActiveDesign(DESIGN_NAME)
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    mesh_module = design.GetModule("MeshSetup")
    report = design.GetModule("ReportSetup")

    commands = read_commands(COMMANDS_CSV)
    payload = {
        "script_version": SCRIPT_VERSION,
        "n_commands": len(commands),
        "commands_csv": COMMANDS_CSV,
        "out_csv": OUT_CSV,
    }
    payload["mesh_setup_recipe"] = reapply_mesh_and_setup(mesh_module, analysis)

    with open(OUT_CSV, "w") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Id", "Iq", "Phi_d", "Phi_q", "command_id"])

    completed = []
    for i, cmd in enumerate(commands, start=1):
        id_v = cmd["Id"]
        iq_v = cmd["Iq"]
        cid = cmd["command_id"]
        warn("LutAudit %d/%d %s Id=%.4f Iq=%.4f" % (i, len(commands), cid, id_v, iq_v))
        try:
            apply_currents(boundary, id_v, iq_v)
            design.Analyze(SETUP_NAME)
            pt_csv = os.path.join(POINT_DIR, "point_%03d_fluxlinkage_abc.csv" % i)
            phi_a, phi_b, phi_c = export_phi_abc(report, pt_csv)
            phi_d, phi_q = dq_from_abc(phi_a, phi_b, phi_c, THETA_RE)
            with open(OUT_CSV, "a") as f:
                w = csv.writer(f, lineterminator="\n")
                w.writerow([
                    ("%.6f" % id_v), ("%.6f" % iq_v),
                    ("%.12g" % phi_d), ("%.12g" % phi_q), cid,
                ])
            completed.append(cid)
        except BaseException as exc:
            payload["status"] = "failed_at_" + cid
            payload["error"] = str(exc)
            payload["traceback"] = traceback.format_exc().splitlines()
            payload["completed"] = completed
            return payload

    payload["status"] = "ok"
    payload["completed"] = completed
    payload["repo_copy_hint"] = (
        "Copy " + OUT_CSV + " to " +
        os.path.join(_REPO_ROOT, "out", "audit", "lut_audit_fem_results.csv")
    )
    return payload


try:
    payload = main()
except BaseException as exc:
    payload = {
        "status": "error",
        "message": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }

if not os.path.exists(JOB_DIR):
    os.makedirs(JOB_DIR)
with open(OUT_JSON, "w") as f:
    json.dump(payload, f, indent=2)
warn("Wrote LUT FEM audit result to: " + OUT_JSON)
