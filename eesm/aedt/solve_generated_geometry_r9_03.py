"""Solve the nominal field-only point on corrected generated geometry."""

import hashlib
import json
import os
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
SOURCE_PROJECT_SHA256 = "e99d4aba12ac4dc139e8797482bb54c2240a1134d277ef74ee7fcb4f19aa57a9"
PROJECT_NAME = "eesm_requal_generated_r9_03_nominal_01"
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r9")
PREFLIGHT_PATH = os.path.join(OUT_DIR, "generated_geometry_preflight_attempt1.json")
STARTED_PATH = os.path.join(OUT_DIR, "generated_geometry_solve_started_attempt1.json")
RESULT_PATH = os.path.join(OUT_DIR, "generated_geometry_solve_result_attempt1.json")


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def write_json(path, payload):
    with open(path, "w") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.flush()


common = {
    "project": PROJECT_NAME,
    "project_path": PROJECT_PATH,
    "design": DESIGN_NAME,
    "setup": SETUP_NAME,
    "source_project_sha256": SOURCE_PROJECT_SHA256,
    "source_contract": "corrected_r3_generated_geometry_model_audit_pass",
    "geometry_rotation_attempted": False,
    "campaign_binding_authorized": False,
    "qualification_authorized": False,
    "training_authorized": False,
    "task_10_authorized": False,
}

if not os.path.isdir(OUT_DIR):
    os.makedirs(OUT_DIR)

preflight = dict(common)
preflight.update({
    "status": "ready",
    "copy_project_sha256": sha256(PROJECT_PATH) if os.path.isfile(PROJECT_PATH) else None,
    "maxwell_solve_attempted": False,
    "field_solve_attempted": False,
    "variation": {"Id": "0A", "Iq": "0A", "If": "2A", "theta_e": "180deg"},
})
write_json(PREFLIGHT_PATH, preflight)

result = dict(common)
started = time.time()
try:
    if preflight["copy_project_sha256"] != SOURCE_PROJECT_SHA256:
        raise RuntimeError("Generated-geometry copy hash does not match corrected source")
    project = oDesktop.OpenProject(PROJECT_PATH)
    if project is None or str(project.GetName()) != PROJECT_NAME:
        raise RuntimeError("Unexpected active project after opening disposable copy")
    design = project.SetActiveDesign(DESIGN_NAME)
    if design is None:
        raise RuntimeError("Expected corrected generated-geometry design is missing")
    design.ChangeProperty([
        "NAME:AllTabs",
        ["NAME:LocalVariableTab", ["NAME:PropServers", "LocalVariables"],
         ["NAME:ChangedProps",
          ["NAME:Id", "Value:=", "0A"],
          ["NAME:Iq", "Value:=", "0A"],
          ["NAME:If", "Value:=", "2A"],
          ["NAME:theta_e", "Value:=", "180deg"]]],
    ])
    solve_started = dict(common)
    solve_started.update({
        "status": "solve_started",
        "maxwell_solve_attempted": True,
        "field_solve_attempted": True,
    })
    write_json(STARTED_PATH, solve_started)
    raw_return_code = design.Analyze("Setup_Qual")
    return_code = 0 if raw_return_code is None else int(raw_return_code)
    result.update({
        "status": "solve_completed" if return_code == 0 else "solve_failed",
        "return_code": return_code,
        "elapsed_seconds": time.time() - started,
        "maxwell_solve_attempted": True,
        "field_solve_attempted": True,
        "solve_completed": return_code == 0,
    })
except BaseException as exc:
    result.update({
        "status": "error",
        "return_code": None,
        "elapsed_seconds": time.time() - started,
        "maxwell_solve_attempted": os.path.isfile(STARTED_PATH),
        "field_solve_attempted": os.path.isfile(STARTED_PATH),
        "solve_completed": False,
        "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    })
finally:
    write_json(RESULT_PATH, result)
