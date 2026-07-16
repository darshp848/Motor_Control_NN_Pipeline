"""Generate only the initial mesh for a disposable r9_02 project copy.

This diagnostic deliberately makes one AEDT model call.  It does not validate,
inspect, save, solve, or authorize downstream work.  The PowerShell runner
creates the byte-identical one-use copy before AEDT starts.
"""

import hashlib
import json
import os
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
SOURCE_PROJECT_SHA256 = "7b7fbd31320afc64c4f031fb8480ebca89071b9b43e2945f47e8a6243cf60cb3"
PROJECT_NAME = "eesm_requal_direct_r9_02_meshdiag_02"
DESIGN_NAME = "EESM_2D_Direct_R9_Quarter"
SETUP_NAME = "Setup_Qual"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r9")
PREFLIGHT_PATH = os.path.join(OUT_DIR, "mesh_generate_preflight_attempt2.json")
RESULT_PATH = os.path.join(OUT_DIR, "mesh_generate_result_attempt2.json")


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
    "operation": 'design.GenerateMesh(["Setup_Qual"])',
    "source_project_sha256": SOURCE_PROJECT_SHA256,
    "maxwell_solve_attempted": False,
    "field_solve_attempted": False,
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
    return_code = int(design.GenerateMesh(["Setup_Qual"]))
    result.update({
        "status": "mesh_generated" if return_code == 0 else "mesh_failed",
        "return_code": return_code,
        "elapsed_seconds": time.time() - started,
    })
except BaseException as exc:
    result.update({
        "status": "error",
        "return_code": None,
        "elapsed_seconds": time.time() - started,
        "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    })
finally:
    write_json(RESULT_PATH, result)
