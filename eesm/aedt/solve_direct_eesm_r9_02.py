"""Run one blocking setup solve on a disposable r9_02 project copy."""

import hashlib
import json
import os
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
SOURCE_PROJECT_SHA256 = "7b7fbd31320afc64c4f031fb8480ebca89071b9b43e2945f47e8a6243cf60cb3"
PROJECT_NAME = "eesm_requal_direct_r9_02_solvediag_02"
DESIGN_NAME = "EESM_2D_Direct_R9_Quarter"
SETUP_NAME = "Setup_Qual"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r9")
PREFLIGHT_PATH = os.path.join(OUT_DIR, "solve_preflight_attempt2.json")
STARTED_PATH = os.path.join(OUT_DIR, "solve_started_attempt2.json")
RESULT_PATH = os.path.join(OUT_DIR, "solve_result_attempt2.json")


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
    "operation": 'design.Analyze("Setup_Qual")',
    "source_project_sha256": SOURCE_PROJECT_SHA256,
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
    "variation": {"Id": "0A", "Iq": "0A", "If": "0A", "theta_e": "180deg"},
})
write_json(PREFLIGHT_PATH, preflight)

result = dict(common)
started = time.time()
try:
    if preflight["copy_project_sha256"] != SOURCE_PROJECT_SHA256:
        raise RuntimeError("Disposable r9_02 copy hash does not match immutable source")
    project = oDesktop.OpenProject(PROJECT_PATH)
    if project is None or str(project.GetName()) != PROJECT_NAME:
        raise RuntimeError("Unexpected active project after opening disposable copy")
    design = project.SetActiveDesign(DESIGN_NAME)
    if design is None:
        raise RuntimeError("Expected r9_02 design is missing")
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
