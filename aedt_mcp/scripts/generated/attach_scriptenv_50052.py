import sys
import os
from pathlib import Path

roots = [
    os.environ.get("ANSYSEMSV_ROOT252"),
    os.environ.get("ANSYSEM_ROOT252"),
    r"C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM",
    r"C:\Program Files\ANSYS Inc\v252\AnsysEM",
]
plugin = None
for root in roots:
    if not root:
        continue
    candidate = Path(root) / "PythonFiles" / "DesktopPlugin"
    if candidate.exists():
        plugin = candidate
        break
if plugin is None:
    raise SystemExit("DesktopPlugin path not found")
sys.path.append(str(plugin))
import ScriptEnv

ScriptEnv.Initialize("", False, "localhost", 50052)
print(oDesktop.GetVersion())
