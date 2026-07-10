
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

try:
    desktop = attach_desktop()
    emit_result({
        "status": "ok",
        "port": PORT,
        "aedt_version": desktop.GetVersion(),
    })
except Exception as exc:
    emit_error("scriptenv_attach", exc, "check_aedt_listener_or_launch_procedure")
