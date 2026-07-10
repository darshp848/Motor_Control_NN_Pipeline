
import json
import os
import sys
import traceback
from pathlib import Path

PORT = 50052
RESULT_PREFIX = "AEDT_MCP_RESULT_JSON="
ERROR_PREFIX = "AEDT_MCP_ERROR_JSON="

def emit_result(payload):
    print(RESULT_PREFIX + json.dumps(payload, sort_keys=True))

def emit_error(category, message, next_step="paste_output_back", extra=None):
    payload = {
        "status": "error",
        "category": category,
        "message": str(message),
        "recommended_next_step": next_step,
        "traceback": traceback.format_exc(limit=6),
    }
    if extra:
        payload.update(extra)
    print(ERROR_PREFIX + json.dumps(payload, sort_keys=True))

def desktop_plugin_path():
    roots = [
        os.environ.get("ANSYSEMSV_ROOT252"),
        os.environ.get("ANSYSEM_ROOT252"),
        r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM",
        r"C:\Program Files\ANSYS Inc\v252\AnsysEM",
    ]
    for root in roots:
        if not root:
            continue
        candidate = Path(root) / "PythonFiles" / "DesktopPlugin"
        if candidate.exists():
            return candidate
    raise RuntimeError("DesktopPlugin path not found")

def attach_desktop():
    sys.path.append(str(desktop_plugin_path()))
    import ScriptEnv
    ScriptEnv.Initialize("", False, "localhost", 50052)
    return globals()["oDesktop"]

import shutil

SOURCE_PROJECT = Path(r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\Examples\RMxprt\ipm\ipm_1.aedt")
COPY_DIR = Path(r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp\tmp\aedt_projects\ipm_1_probe")

def copy_project():
    if not SOURCE_PROJECT.exists():
        raise FileNotFoundError(str(SOURCE_PROJECT))
    if SOURCE_PROJECT.suffix.lower() != ".aedt":
        raise ValueError("project must be a .aedt file")
    COPY_DIR.mkdir(parents=True, exist_ok=True)
    target = COPY_DIR / SOURCE_PROJECT.name
    if target.exists():
        target.unlink()
    shutil.copy2(SOURCE_PROJECT, target)
    src_aedb = SOURCE_PROJECT.with_suffix(".aedb")
    dst_aedb = target.with_suffix(".aedb")
    if dst_aedb.exists():
        shutil.rmtree(dst_aedb)
    if src_aedb.exists():
        shutil.copytree(src_aedb, dst_aedb)
    return target

def list_or_empty(fn):
    try:
        return list(fn())
    except BaseException:
        return []

try:
    desktop = attach_desktop()
    copied = copy_project()
    before = set(list_or_empty(desktop.GetProjectList))
    open_error = None
    try:
        desktop.OpenProject(str(copied))
    except BaseException as exc:
        open_error = str(exc)
    projects = list_or_empty(desktop.GetProjectList)
    new_projects = [p for p in projects if p not in before]
    if open_error and copied.stem not in projects and not new_projects:
        raise RuntimeError(f"OpenProject failed and project is not loaded: {open_error}")
    project_name = new_projects[-1] if new_projects else copied.stem
    project = desktop.SetActiveProject(project_name)
    designs = []
    for raw_design in list_or_empty(project.GetTopDesignList):
        design_name = str(raw_design).split(";")[-1]
        item = {"name": design_name, "raw_name": str(raw_design), "type": None, "setups": [], "variables": [], "excitations": []}
        try:
            design = project.SetActiveDesign(design_name)
            item["type"] = design.GetDesignType()
            try:
                item["variables"] = list(design.GetVariables())
            except BaseException:
                item["variables"] = []
            try:
                item["setups"] = list(design.GetModule("AnalysisSetup").GetSetups())
            except BaseException:
                item["setups"] = []
            try:
                item["excitations"] = list(design.GetModule("BoundarySetup").GetExcitations())
            except BaseException:
                item["excitations"] = []
        except BaseException as exc:
            item["error"] = str(exc)
        designs.append(item)
    emit_result({
        "status": "ok",
        "job_id": "ipm_1_probe",
        "source_project": str(SOURCE_PROJECT),
        "copied_project": str(copied),
        "project_name": project_name,
        "projects": projects,
        "designs": designs,
    })
except Exception as exc:
    emit_error("project_probe", exc, "inspect_project_path_or_aedt_state")
