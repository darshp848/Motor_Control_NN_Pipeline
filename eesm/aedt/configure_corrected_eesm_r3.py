"""Configure the preserved r3 RMxprt-conversion autosave without re-solving."""

import json
import os
import sys
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_corrected_eesm_r3 as corrected


base = corrected.base
base.oDesktop = oDesktop
STATUS_PATH = os.path.join(corrected.OUT_ROOT, "model_build_status.json")

payload = {
    "status": "running",
    "project_path": corrected.PROJECT_PATH,
    "project": corrected.PROJECT_NAME,
    "design": base.DESIGN_NAME,
    "setup": base.SETUP_NAME,
    "recovery_source": "preserved_rmxprt_conversion_autosave",
    "rmxprt_solve_attempted": False,
    "maxwell_solve_attempted": False,
}
try:
    project = oDesktop.OpenProject(corrected.PROJECT_PATH)
    if project is None:
        project = oDesktop.SetActiveProject(corrected.PROJECT_NAME)
    if corrected.PROJECT_NAME != project.GetName():
        raise RuntimeError("Recovered project name mismatch")
    if base.DESIGN_NAME not in base.project_design_names(project):
        raise RuntimeError("Recovered autosave lacks converted design")
    payload["qualification_contract"] = corrected.configure_corrected_maxwell(project)
    project.Save()
    payload["status"] = "built"
except BaseException as exc:
    payload["status"] = "error"
    payload["error"] = str(exc)
    payload["traceback"] = traceback.format_exc().splitlines()
    try:
        payload["aedt_messages"] = base.collect_aedt_messages()
    except BaseException:
        pass
finally:
    with open(STATUS_PATH, "w") as stream:
        json.dump(base.normalize(payload), stream, indent=2)
    try:
        AddWarningMessage("Corrected EESM r3 status: " + STATUS_PATH)
    except BaseException:
        print(STATUS_PATH)
