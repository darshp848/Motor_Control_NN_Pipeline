import os
import sys

os.environ["PYAEDT_USE_PRE_GRPC_ARGS"] = "True"
os.environ["PYAEDT_DESKTOP_PORT"] = "50052"
os.environ["no_proxy"] = "localhost,127.0.0.1"
os.environ["NO_PROXY"] = "localhost,127.0.0.1"

from ansys.aedt.core import Desktop, settings
import ansys.aedt.core.desktop as desktop_module

settings.grpc_secure_mode = False

def _blocked_launch(*args, **kwargs):
    raise RuntimeError("PyAEDT attempted to launch AEDT during attach-only test; blocked by generated script.")

desktop_module.launch_aedt = _blocked_launch

aedt_pid_raw = os.environ.get("AEDT_ATTACH_PID")
if not aedt_pid_raw:
    raise SystemExit("AEDT_ATTACH_PID is required so PyAEDT cannot silently launch a new session.")
try:
    aedt_pid = int(aedt_pid_raw)
except ValueError as exc:
    raise SystemExit(f"Invalid AEDT_ATTACH_PID={aedt_pid_raw!r}") from exc

desktop = Desktop(
    version="2025.2",
    student_version=True,
    non_graphical=True,
    new_desktop=False,
    machine="localhost",
    port=50052,
    aedt_process_id=aedt_pid,
    close_on_exit=False,
)

print("Connected")
print(desktop.aedt_version_id)
print(desktop.project_list())
