
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
JOB_ID = "unit_pyaedt_probe"
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

try:
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    desktop = launch_desktop(close_on_exit=False)
    emit_result({
        "status": "ok",
        "job_id": JOB_ID,
        "port": PORT,
        "aedt_version": getattr(desktop, "aedt_version_id", None),
        "process_id": getattr(desktop, "aedt_process_id", None),
        "project_list": desktop.project_list(),
        "mode": "pyaedt_launch_owned",
    })
except Exception as exc:
    emit_error("pyaedt_launch_failed", exc, "inspect_license_security_or_install")
