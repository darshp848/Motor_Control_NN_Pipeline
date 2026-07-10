
import csv
import json
import math
import os
import shutil
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp")
PORT = 50052
JOB_ID = "unit_pyaedt_project"
JOB_DIR = PROJECT_ROOT / "tmp" / "aedt_jobs" / JOB_ID
PROJECT_COPY_DIR = PROJECT_ROOT / "tmp" / "aedt_projects" / JOB_ID
RESULT_PREFIX = "AEDT_MCP_RESULT_JSON="
ERROR_PREFIX = "AEDT_MCP_ERROR_JSON="

os.environ["PYAEDT_USE_PRE_GRPC_ARGS"] = "True"
os.environ["PYAEDT_DESKTOP_PORT"] = str(PORT)
os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

def emit_result(payload):
    print(RESULT_PREFIX + json.dumps(payload, sort_keys=True))

def emit_error(category, message, next_step="paste_output_back", extra=None):
    payload = {
        "status": "error",
        "category": category,
        "message": str(message),
        "recommended_next_step": next_step,
        "traceback": traceback.format_exc(limit=8),
    }
    if extra:
        payload.update(extra)
    print(ERROR_PREFIX + json.dumps(payload, sort_keys=True))

def require_under(path, root, label):
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise RuntimeError(f"{label} must stay under {root_resolved}, got {resolved}")
    return resolved

def reject_unsafe_source_project(path):
    raw = str(path).lower().replace("/", "\\")
    if "\\program files\\" in raw:
        raise RuntimeError("refusing to mutate or directly use a Program Files project; provide a user project file")
    if "\\onedrive\\" in raw:
        raise RuntimeError("refusing OneDrive-backed AEDT project mutation; copy the project to a normal local folder first")

def copy_project(source_project):
    source = Path(source_project)
    if not source.exists():
        raise FileNotFoundError(str(source))
    if source.suffix.lower() != ".aedt":
        raise ValueError("project must be a .aedt file")
    reject_unsafe_source_project(source)
    require_under(PROJECT_COPY_DIR, PROJECT_ROOT / "tmp" / "aedt_projects", "project copy directory")
    PROJECT_COPY_DIR.mkdir(parents=True, exist_ok=True)
    target = PROJECT_COPY_DIR / source.name
    if target.exists():
        target.unlink()
    shutil.copy2(source, target)
    src_aedb = source.with_suffix(".aedb")
    dst_aedb = target.with_suffix(".aedb")
    if dst_aedb.exists():
        shutil.rmtree(dst_aedb)
    if src_aedb.exists():
        shutil.copytree(src_aedb, dst_aedb)
    return target

def launch_desktop(close_on_exit=False):
    from ansys.aedt.core import Desktop, settings
    settings.grpc_secure_mode = False
    return Desktop(
        version="2025.2",
        student_version=True,
        non_graphical=True,
        new_desktop=True,
        port=PORT,
        close_on_exit=close_on_exit,
    )

SOURCE_PROJECT = Path(r"C:\Users\darsh\TAMU\project.aedt")

def list_attr(obj, attr):
    try:
        value = getattr(obj, attr)
        if callable(value):
            value = value()
        return list(value or [])
    except Exception:
        return []

try:
    copied = copy_project(SOURCE_PROJECT)
    desktop = launch_desktop(close_on_exit=False)
    from ansys.aedt.core import Maxwell3d
    app = Maxwell3d(project=str(copied), new_desktop=False)
    project_name = getattr(app, "project_name", copied.stem)
    designs = []
    for design_name in list_attr(app, "design_list"):
        item = {"name": str(design_name), "type": None, "setups": [], "variables": [], "excitations": []}
        try:
            candidate = Maxwell3d(project=project_name, design=str(design_name), new_desktop=False)
            item["type"] = getattr(candidate, "design_type", None)
            item["setups"] = list_attr(candidate, "setup_names")
            item["variables"] = sorted(set(list_attr(candidate.variable_manager, "design_variable_names") + list_attr(candidate.variable_manager, "project_variable_names")))
            try:
                item["excitations"] = list(candidate.get_excitations_name())
            except Exception:
                item["excitations"] = []
        except Exception as exc:
            item["error"] = str(exc)
        designs.append(item)
    emit_result({
        "status": "ok",
        "job_id": JOB_ID,
        "mode": "pyaedt_launch_owned",
        "source_project": str(SOURCE_PROJECT),
        "copied_project": str(copied),
        "project_name": project_name,
        "designs": designs,
    })
except Exception as exc:
    emit_error("pyaedt_project_open_failed", exc, "inspect_project_path_or_pyaedt_logs")
