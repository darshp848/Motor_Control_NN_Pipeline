"""Operator-run AEDT procedures and generated attach scripts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import execution_policy as policy


def _validate_port(port: int) -> int:
    if port <= 0 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    return port


def launch_procedure(port: int = 50052) -> dict[str, Any]:
    _validate_port(port)
    project_root = str(policy.PROJECT_ROOT)
    return policy.user_action_required(
        reason="Launching ansysedt.exe is Tier 2: native user-run PowerShell required.",
        risk_level="medium",
        procedure_id=f"launch_aedt_grpc_{port}",
        commands=[
            "$ErrorActionPreference = 'Stop'",
            f"$projectRoot = '{project_root}'",
            "Set-Location -LiteralPath $projectRoot",
            "New-Item -ItemType Directory -Force -Path 'tmp\\aedt_temp','tmp\\aedt_projects','tmp\\aedt_jobs' | Out-Null",
            "$env:TEMP = (Resolve-Path 'tmp\\aedt_temp').Path",
            "$env:TMP = (Resolve-Path 'tmp\\aedt_temp').Path",
            f"$log = (Resolve-Path 'tmp\\aedt_jobs').Path + '\\\\aedt_grpc_{port}_user_run.log'",
            "$roots = @($env:ANSYSEMSV_ROOT252, $env:ANSYSEM_ROOT252, 'C:\\Program Files\\ANSYS Inc\\ANSYS Student\\v252\\AnsysEM', 'C:\\Program Files\\ANSYS Inc\\v252\\AnsysEM') | Where-Object { $_ }",
            "$candidateExe = foreach ($root in $roots) { Join-Path $root 'ansysedtsv.exe'; Join-Path $root 'ansysedt.exe'; Join-Path $root 'ansysedtng.exe'; Join-Path $root 'Win64\\ansysedt.exe' }",
            "$aedtExe = $candidateExe | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1",
            "if (-not $aedtExe) { throw \"Could not find AEDT executable. Paste back `$roots and `$candidateExe.\" }",
            f"& $aedtExe -ng -grpcsrv {port} *> $log",
        ],
        expected_output=[f"GRPC server running on port: {port}", "An ansysedt/ansysedtsv process remains running."],
        paste_back=["The final 80 lines of the log.", "The PID and port if PowerShell reports them."],
        log_paths=[f"tmp/aedt_jobs/aedt_grpc_{port}_user_run.log", "batch.log"],
        cleanup=["Close AEDT manually only if the process hangs."],
    )


def pyaedt_attach_script(port: int = 50052) -> str:
    _validate_port(port)
    return f'''import os
import sys

os.environ["PYAEDT_USE_PRE_GRPC_ARGS"] = "True"
os.environ["PYAEDT_DESKTOP_PORT"] = "{port}"
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
    raise SystemExit(f"Invalid AEDT_ATTACH_PID={{aedt_pid_raw!r}}") from exc

desktop = Desktop(
    version="2025.2",
    student_version=True,
    non_graphical=True,
    new_desktop=False,
    machine="localhost",
    port={port},
    aedt_process_id=aedt_pid,
    close_on_exit=False,
)

print("Connected")
print(desktop.aedt_version_id)
print(desktop.project_list())
'''


def scriptenv_attach_script(port: int = 50052) -> str:
    _validate_port(port)
    return f'''import sys
import os
from pathlib import Path

roots = [
    os.environ.get("ANSYSEMSV_ROOT252"),
    os.environ.get("ANSYSEM_ROOT252"),
    r"C:\\Program Files\\ANSYS Inc\\ANSYS Student\\v252\\AnsysEM",
    r"C:\\Program Files\\ANSYS Inc\\v252\\AnsysEM",
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

ScriptEnv.Initialize("", False, "localhost", {port})
print(oDesktop.GetVersion())
'''


def write_attach_scripts(port: int = 50052, include_scriptenv: bool = True) -> list[str]:
    _validate_port(port)
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    pyaedt_path = out_dir / f"attach_pyaedt_{port}.py"
    pyaedt_path.write_text(pyaedt_attach_script(port), encoding="utf-8")
    written.append(str(pyaedt_path))
    if include_scriptenv:
        scriptenv_path = out_dir / f"attach_scriptenv_{port}.py"
        scriptenv_path.write_text(scriptenv_attach_script(port), encoding="utf-8")
        written.append(str(scriptenv_path))
    return written


def attach_test_procedure(port: int = 50052, include_scriptenv: bool = True) -> dict[str, Any]:
    _validate_port(port)
    written = write_attach_scripts(port, include_scriptenv)
    commands = [
        "$ErrorActionPreference = 'Stop'",
        f"$projectRoot = '{policy.PROJECT_ROOT}'",
        "Set-Location -LiteralPath $projectRoot",
        "$pythonCandidates = @((Join-Path $projectRoot '..\\..\\.venv\\Scripts\\python.exe'), (Join-Path $projectRoot '..\\.venv\\Scripts\\python.exe'), (Join-Path $projectRoot '.venv\\Scripts\\python.exe'))",
        "$pythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1",
        "if (-not $pythonExe) { $pythonExe = 'python' }",
        f"$aedtConn = Get-NetTCPConnection -LocalPort {port} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1",
        f"if (-not $aedtConn) {{ throw 'No AEDT listener found on port {port}.' }}",
        "$env:AEDT_ATTACH_PID = [string]$aedtConn.OwningProcess",
        "$env:PYAEDT_USE_PRE_GRPC_ARGS = 'True'",
        f"$env:PYAEDT_DESKTOP_PORT = '{port}'",
        "$env:no_proxy = 'localhost,127.0.0.1'",
        "$env:NO_PROXY = 'localhost,127.0.0.1'",
        f"$pyaedt = Start-Process -FilePath $pythonExe -ArgumentList @('scripts\\generated\\attach_pyaedt_{port}.py') -RedirectStandardOutput tmp\\aedt_jobs\\attach_pyaedt_{port}_user_run.log -RedirectStandardError tmp\\aedt_jobs\\attach_pyaedt_{port}_user_run.err.log -NoNewWindow -PassThru",
        "$null = Wait-Process -Id $pyaedt.Id -Timeout 45 -ErrorAction SilentlyContinue",
        f"if (-not $pyaedt.HasExited) {{ Stop-Process -Id $pyaedt.Id -Force; 'PyAEDT attach timed out after 45s and was stopped by the user-run procedure.' | Add-Content tmp\\aedt_jobs\\attach_pyaedt_{port}_user_run.err.log }}",
    ]
    if include_scriptenv:
        commands.append(f"$scriptenv = Start-Process -FilePath $pythonExe -ArgumentList @('scripts\\generated\\attach_scriptenv_{port}.py') -RedirectStandardOutput tmp\\aedt_jobs\\attach_scriptenv_{port}_user_run.log -RedirectStandardError tmp\\aedt_jobs\\attach_scriptenv_{port}_user_run.err.log -NoNewWindow -PassThru")
        commands.append("$null = Wait-Process -Id $scriptenv.Id -Timeout 45 -ErrorAction SilentlyContinue")
        commands.append(f"if (-not $scriptenv.HasExited) {{ Stop-Process -Id $scriptenv.Id -Force; 'ScriptEnv attach timed out after 45s and was stopped by the user-run procedure.' | Add-Content tmp\\aedt_jobs\\attach_scriptenv_{port}_user_run.err.log }}")
    response = policy.user_action_required(
        reason="Attach is separate from launch and must use new_desktop=False.",
        risk_level="medium",
        procedure_id=f"attach_existing_aedt_{port}",
        commands=commands,
        expected_output=["Connected", "AEDT version text", "Project list or ScriptEnv desktop version"],
        paste_back=["The PyAEDT attach log.", "The ScriptEnv attach log if generated."],
        log_paths=[f"tmp/aedt_jobs/attach_pyaedt_{port}_user_run.log", f"tmp/aedt_jobs/attach_scriptenv_{port}_user_run.log"],
        cleanup=["Do not start a second AEDT process for attach tests."],
    )
    response["generated_scripts"] = [str(Path(path).relative_to(policy.PROJECT_ROOT)) for path in written]
    return response


def render_markdown(procedure: dict[str, Any]) -> str:
    lines = [
        f"# {procedure['procedure_id']}",
        "",
        f"Status: `{procedure['status']}`",
        f"Risk: `{procedure['risk_level']}`",
        "",
        "## Reason",
        procedure["reason"],
        "",
        "## Commands",
        "```powershell",
        *procedure["commands"],
        "```",
        "",
        "## Expected Output",
        *[f"- {item}" for item in procedure["expected_output"]],
        "",
        "## Paste Back",
        *[f"- {item}" for item in procedure["paste_back"]],
        "",
        "## Log Paths",
        *[f"- {item}" for item in procedure["log_paths"]],
        "",
        "## Cleanup",
        *[f"- {item}" for item in procedure["cleanup"]],
        "",
    ]
    return "\n".join(lines)
