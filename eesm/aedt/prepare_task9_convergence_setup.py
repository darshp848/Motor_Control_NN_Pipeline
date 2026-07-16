"""Update only Setup_Qual for a three-pass Task 9 convergence retry."""

import json
import os
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
STATUS_PATH = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_baseline", "setup_remediation_status.json"
)
PROJECT_NAME = "eesm_qual"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "eesm_qual", "eesm_qual.aedt"
)
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
MAXIMUM_PASSES = 3
PERCENT_ERROR = 1


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


def write_status(payload):
    parent = os.path.dirname(STATUS_PATH)
    if not os.path.exists(parent):
        os.makedirs(parent)
    with open(STATUS_PATH, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


payload = {
    "status": "running",
    "stage": "preflight",
    "project": PROJECT_NAME,
    "design": DESIGN_NAME,
    "setup": SETUP_NAME,
    "maximum_passes_before": 2,
    "maximum_passes_after": MAXIMUM_PASSES,
    "percent_error": PERCENT_ERROR,
    "geometry_rebuilt": False,
    "maxwell_solve_attempted": False,
    "failure": None,
}
write_status(payload)
try:
    project = required(oDesktop.GetActiveProject, "Get active project")
    if project is None:
        project = required(lambda: oDesktop.OpenProject(PROJECT_PATH),
                           "Open qualified project")
    project_name = required(project.GetName, "Get project name")
    if project_name != PROJECT_NAME:
        raise RuntimeError("Active project must be " + PROJECT_NAME)
    design = required(lambda: project.SetActiveDesign(DESIGN_NAME), "Activate design")
    design_name = required(design.GetName, "Get design name")
    if design_name != DESIGN_NAME:
        raise RuntimeError("Active design must be " + DESIGN_NAME)
    analysis = required(lambda: design.GetModule("AnalysisSetup"), "Get AnalysisSetup")
    if SETUP_NAME not in list(required(analysis.GetSetups, "Get setup names")):
        raise RuntimeError("Missing qualified setup " + SETUP_NAME)

    payload["stage"] = "edit_setup"
    write_status(payload)
    required(lambda: analysis.EditSetup(SETUP_NAME, [
        "NAME:" + SETUP_NAME,
        "Enabled:=", True,
        ["NAME:MeshLink", "ImportMesh:=", False],
        "MaximumPasses:=", MAXIMUM_PASSES,
        "MinimumPasses:=", 1,
        "MinimumConvergedPasses:=", 1,
        "PercentRefinement:=", 10,
        "SolveFieldOnly:=", False,
        "PercentError:=", PERCENT_ERROR,
        "SolveMatrixAtLast:=", True,
        "UseNonLinearIterNum:=", True,
        "MinIterNum:=", 5,
        "MaxIterNum:=", 20,
        "NonLinearResidual:=", 0.001,
        "SmoothBHCurve:=", True,
    ]), "Edit Setup_Qual convergence settings")

    payload["stage"] = "validate"
    write_status(payload)
    validation = call(design.ValidateDesign)
    errors = normalize(required(
        lambda: oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2),
        "Read validation errors",
    ))
    payload["validation"] = validation
    payload["errors"] = errors or []
    if not validation["ok"] or errors:
        raise RuntimeError("Setup remediation validation reported errors")
    required(project.Save, "Save qualified project")
    payload["status"] = "updated"
    payload["stage"] = "idle"
except BaseException as exc:
    payload["status"] = "error"
    payload["failure"] = {
        "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }
finally:
    write_status(payload)
    try:
        AddWarningMessage("Task 9 setup remediation status: " + STATUS_PATH)
    except BaseException:
        print(STATUS_PATH)
