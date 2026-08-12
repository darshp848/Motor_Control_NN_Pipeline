"""Export the r9_03 cross-section to DXF for the FEMM path.

Runs inside AEDT (``ansysedtsv.exe -RunScriptAndExit``) against a DISPOSABLE
copy created by run_export_r9_03_dxf.ps1. Never opens the source project.

Geometry export only. This script does not mesh, solve, validate, or authorize
anything, and writes no campaign row. AEDT Student's element cap applies to
solving, not to exporting geometry.

Source: eesm_requal_generated_r9_03_nominal_01 / EESM_2D_Qual, ModelDepth
120 mm -- the contract-correct depth. The 2026-07-21 pilot ran on
eesm_pilot_source_01 at 77.0793 mm, so anchors from that pilot must be scaled
by 120/77.0793 = 1.55684 before comparison. See
research_planning/eesm_protocol/FEMM_MIGRATION_STATE.md.
"""

import json
import os
import time
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))

PROJECT_NAME = "eesm_r9_03_dxf_01"
DESIGN_NAME = "EESM_2D_Qual"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "femm_geometry_r9_03")
DXF_PATH = os.path.join(OUT_DIR, "eesm_r9_03_section.dxf")
RESULT_PATH = os.path.join(OUT_DIR, "dxf_export_result.json")


def write_json(path, payload):
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(path, "w") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)


def main():
    result = {
        "status": "started",
        "project": PROJECT_NAME,
        "design": DESIGN_NAME,
        "project_path": PROJECT_PATH,
        "dxf_path": DXF_PATH,
        "export_attempted": False,
        "dxf_exists": False,
        "dxf_bytes": None,
        "objects": [],
        "model_depth": None,
        "errors": [],
        "solve_attempted": False,
        "qualification_authorized": False,
        "campaign_binding_authorized": False,
        "training_authorized": False,
        "task_10_authorized": False,
    }
    started = time.time()
    try:
        desktop = oDesktop  # noqa: F821  (AEDT injects this)
        desktop.RestoreWindow()
        project = desktop.OpenProject(PROJECT_PATH)
        if project is None:
            project = desktop.SetActiveProject(PROJECT_NAME)
        design = project.SetActiveDesign(DESIGN_NAME)
        editor = design.SetActiveEditor("3D Modeler")

        try:
            result["objects"] = list(editor.GetObjectNames())
        except Exception as exc:
            result["errors"].append("GetObjectNames: %s" % exc)

        try:
            result["model_depth"] = design.GetDesignSettings().Get("ModelDepth")
        except Exception:
            try:
                result["model_depth"] = editor.GetModelUnits()
            except Exception as exc:
                result["errors"].append("model_depth: %s" % exc)

        if not os.path.isdir(OUT_DIR):
            os.makedirs(OUT_DIR)

        result["export_attempted"] = True
        editor.Export([
            "NAME:ExportParameters",
            "AllowRegionDependentPartSelectionForPMLCreation:=", True,
            "AllowRegionSelectionForPMLCreation:=", True,
            "Selections:=", "",
            "File Name:=", DXF_PATH.replace("\\", "/"),
            "Major Version:=", -1,
            "Minor Version:=", -1,
        ])

        result["dxf_exists"] = os.path.isfile(DXF_PATH)
        if result["dxf_exists"]:
            result["dxf_bytes"] = os.path.getsize(DXF_PATH)
            result["status"] = "exported"
        else:
            result["status"] = "export_returned_but_no_file"
    except Exception as exc:
        result["status"] = "failed"
        result["errors"].append("%s: %s" % (type(exc).__name__, exc))
        result["traceback"] = traceback.format_exc()
    finally:
        result["elapsed_seconds"] = time.time() - started
        write_json(RESULT_PATH, result)


main()
