"""PyAEDT launch-owned AEDT procedure and script generation."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import execution_policy as policy
from . import scriptenv_workflow

FEM_HEADER = scriptenv_workflow.FEM_HEADER


def _validate_port(port: int) -> int:
    if port <= 0 or port > 65535:
        raise ValueError("port must be between 1 and 65535")
    return port


def _safe_job_id(job_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", job_id.strip())
    if not cleaned:
        raise ValueError("job_id must not be empty")
    return cleaned


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(policy.PROJECT_ROOT))
    except ValueError:
        return str(path)


def _python_setup_commands() -> list[str]:
    return [
        f"$projectRoot = '{policy.PROJECT_ROOT}'",
        "Set-Location -LiteralPath $projectRoot",
        "$pythonCandidates = @((Join-Path $projectRoot '..\\..\\.venv\\Scripts\\python.exe'), (Join-Path $projectRoot '..\\.venv\\Scripts\\python.exe'), (Join-Path $projectRoot '.venv\\Scripts\\python.exe'))",
        "$pythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1",
        "if (-not $pythonExe) { $pythonExe = 'python' }",
        "$env:PYAEDT_USE_PRE_GRPC_ARGS = 'True'",
        "$env:no_proxy = 'localhost,127.0.0.1'",
        "$env:NO_PROXY = 'localhost,127.0.0.1'",
    ]


def _run_script_commands(script: str, job_id: str, timeout_seconds: int) -> list[str]:
    job_id = _safe_job_id(job_id)
    stem = Path(script).stem
    log_dir = f"tmp\\aedt_jobs\\{job_id}"
    return [
        f"New-Item -ItemType Directory -Force -Path '{log_dir}' | Out-Null",
        f"$proc = Start-Process -FilePath $pythonExe -ArgumentList @('{script}') -RedirectStandardOutput '{log_dir}\\{stem}.log' -RedirectStandardError '{log_dir}\\{stem}.err.log' -NoNewWindow -PassThru",
        f"$null = Wait-Process -Id $proc.Id -Timeout {timeout_seconds} -ErrorAction SilentlyContinue",
        f"if (-not $proc.HasExited) {{ 'PyAEDT helper timed out after {timeout_seconds}s. Run aedt.generate_stop_duplicate_aedt_procedure before retrying.' | Add-Content '{log_dir}\\{stem}.err.log' }}",
    ]


def _common_pyaedt_python(*, job_id: str, port: int = 50052) -> str:
    _validate_port(port)
    job_id = _safe_job_id(job_id)
    return f'''
import csv
import json
import math
import os
import shutil
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(r"{policy.PROJECT_ROOT}")
PORT = {port}
JOB_ID = "{job_id}"
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
    payload = {{
        "status": "error",
        "category": category,
        "message": str(message),
        "recommended_next_step": next_step,
        "traceback": traceback.format_exc(limit=8),
    }}
    if extra:
        payload.update(extra)
    print(ERROR_PREFIX + json.dumps(payload, sort_keys=True))

def require_under(path, root, label):
    resolved = Path(path).resolve()
    root_resolved = Path(root).resolve()
    if resolved != root_resolved and root_resolved not in resolved.parents:
        raise RuntimeError(f"{{label}} must stay under {{root_resolved}}, got {{resolved}}")
    return resolved

def reject_unsafe_source_project(path):
    raw = str(path).lower().replace("/", "\\\\")
    if "\\\\program files\\\\" in raw:
        raise RuntimeError("refusing to mutate or directly use a Program Files project; provide a user project file")
    if "\\\\onedrive\\\\" in raw:
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
'''


def pyaedt_launch_owned_probe_script(*, port: int = 50052, job_id: str = "pyaedt_launch_probe") -> str:
    return _common_pyaedt_python(job_id=job_id, port=port) + '''
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
'''


def pyaedt_project_probe_script(
    *,
    project: str,
    port: int = 50052,
    job_id: str = "pyaedt_project_probe",
) -> str:
    source = str(Path(project))
    return _common_pyaedt_python(job_id=job_id, port=port) + f'''
SOURCE_PROJECT = Path(r"{source}")

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
        item = {{"name": str(design_name), "type": None, "setups": [], "variables": [], "excitations": []}}
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
    emit_result({{
        "status": "ok",
        "job_id": JOB_ID,
        "mode": "pyaedt_launch_owned",
        "source_project": str(SOURCE_PROJECT),
        "copied_project": str(copied),
        "project_name": project_name,
        "designs": designs,
    }})
except Exception as exc:
    emit_error("pyaedt_project_open_failed", exc, "inspect_project_path_or_pyaedt_logs")
'''


def pyaedt_fem_export_script(
    *,
    project_copy: str,
    design: str,
    setup: str,
    port: int = 50052,
    job_id: str = "pyaedt_fem_export_smoke",
    phase_a: str = "Phase_A",
    phase_b: str = "Phase_B",
    phase_c: str = "Phase_C",
    n_id: int = 2,
    n_iq: int = 2,
    i_rated: float = 150.0,
    theta_re: float = 0.0,
    solve: bool = True,
    resume: bool = True,
    out: str = "data/flux_map_fem.csv",
) -> str:
    return _common_pyaedt_python(job_id=job_id, port=port) + f'''
PROJECT_COPY = Path(r"{project_copy}")
DESIGN_NAME = {design!r}
SETUP_NAME = {setup!r}
PHASES = ({phase_a!r}, {phase_b!r}, {phase_c!r})
N_ID = {n_id}
N_IQ = {n_iq}
I_RATED = {i_rated!r}
THETA_RE = {theta_re!r}
SOLVE = {bool(solve)!r}
RESUME = {bool(resume)!r}
OUT_CSV = PROJECT_ROOT / r"{out}"
PROGRESS_CSV = JOB_DIR / "progress.csv"
HEADER = ("Id", "Iq", "Phi_d", "Phi_q")

def abc_from_dq(id_, iq, theta_re=0.0):
    ia = math.cos(theta_re) * id_ - math.sin(theta_re) * iq
    ib = math.cos(theta_re - 2 * math.pi / 3) * id_ - math.sin(theta_re - 2 * math.pi / 3) * iq
    ic = -(ia + ib)
    return ia, ib, ic

def dq_from_abc(psi_a, psi_b, psi_c, theta_re=0.0):
    return (
        (2 / 3) * (psi_a * math.cos(theta_re) + psi_b * math.cos(theta_re - 2 * math.pi / 3) + psi_c * math.cos(theta_re + 2 * math.pi / 3)),
        (2 / 3) * (-psi_a * math.sin(theta_re) - psi_b * math.sin(theta_re - 2 * math.pi / 3) - psi_c * math.sin(theta_re + 2 * math.pi / 3)),
    )

def current_grid():
    if N_ID < 2 or N_IQ < 2:
        raise ValueError("n_id and n_iq must each be at least 2")
    ids = [(-2.0 * I_RATED) + (2.0 * I_RATED) * i / (N_ID - 1) for i in range(N_ID)]
    iqs = [(2.0 * I_RATED) * i / (N_IQ - 1) for i in range(N_IQ)]
    return [(float(idv), float(iqv)) for idv in ids for iqv in iqs]

def set_variables(app, id_val, iq_val):
    ia, ib, ic = abc_from_dq(id_val, iq_val, THETA_RE)
    for name, value in {{"Id": id_val, "Iq": iq_val, "Ia": ia, "Ib": ib, "Ic": ic}}.items():
        app[name] = f"{{value:.9g}}A"

def read_flux(app):
    values = []
    for phase in PHASES:
        expr = f"FluxLinkage({{phase}})"
        try:
            data = app.post.get_solution_data(expressions=[expr], setup_sweep_name=SETUP_NAME)
            raw = getattr(data, "data_real", lambda expression=None: [])(expr)
            if not raw:
                raw = getattr(data, "full_matrix_real_imag", [])
            if not raw:
                raise RuntimeError(f"empty data for {{expr}}")
            values.append(float(raw[0]))
        except Exception as exc:
            raise RuntimeError(f"failed reading {{expr}}: {{exc}}") from exc
    return tuple(values)

def read_progress():
    rows = {{}}
    if not PROGRESS_CSV.exists() or not RESUME:
        return rows
    with PROGRESS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise ValueError(f"unexpected progress header: {{reader.fieldnames}}")
        for row in reader:
            record = tuple(float(row[name]) for name in HEADER)
            rows[(record[0], record[1])] = record
    return rows

def append_progress(row):
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    write_header = not PROGRESS_CSV.exists()
    with PROGRESS_CSV.open("a", newline="") as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(HEADER)
        writer.writerow([f"{{row[0]:.6f}}", f"{{row[1]:.6f}}", f"{{row[2]:.9f}}", f"{{row[3]:.9f}}"])

try:
    require_under(PROJECT_COPY, PROJECT_ROOT / "tmp" / "aedt_projects", "project_copy")
    require_under(OUT_CSV, PROJECT_ROOT / "data", "final FEM CSV")
    if not PROJECT_COPY.exists():
        raise FileNotFoundError(str(PROJECT_COPY))
    JOB_DIR.mkdir(parents=True, exist_ok=True)
    if not RESUME and PROGRESS_CSV.exists():
        PROGRESS_CSV.unlink()
    desktop = launch_desktop(close_on_exit=False)
    from ansys.aedt.core import Maxwell3d
    app = Maxwell3d(project=str(PROJECT_COPY), design=DESIGN_NAME, new_desktop=False)
    if DESIGN_NAME not in list(getattr(app, "design_list", []) or [DESIGN_NAME]):
        raise RuntimeError(f"missing design {{DESIGN_NAME}}")
    setup_names = list(getattr(app, "setup_names", []) or [])
    if setup_names and SETUP_NAME not in setup_names:
        raise RuntimeError(f"missing setup {{SETUP_NAME}}; available={{setup_names}}")
    grid = current_grid()
    completed = read_progress()
    for index, (id_val, iq_val) in enumerate(grid, start=1):
        key = (float(f"{{id_val:.6f}}"), float(f"{{iq_val:.6f}}"))
        if key in completed:
            continue
        print(f"[pyaedt_fem_export] {{index}}/{{len(grid)}} Id={{id_val:.3f}} Iq={{iq_val:.3f}}", flush=True)
        set_variables(app, id_val, iq_val)
        if SOLVE:
            app.analyze_setup(SETUP_NAME)
        psi_a, psi_b, psi_c = read_flux(app)
        phi_d, phi_q = dq_from_abc(psi_a, psi_b, psi_c, THETA_RE)
        row = (key[0], key[1], phi_d, phi_q)
        if not all(math.isfinite(x) for x in row):
            raise RuntimeError(f"non-finite row: {{row}}")
        append_progress(row)
        completed[key] = row
    rows = [completed[(float(f"{{idv:.6f}}"), float(f"{{iqv:.6f}}"))] for idv, iqv in grid]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow([f"{{row[0]:.6f}}", f"{{row[1]:.6f}}", f"{{row[2]:.9f}}", f"{{row[3]:.9f}}"])
    emit_result({{
        "status": "ok",
        "job_id": JOB_ID,
        "mode": "pyaedt_launch_owned",
        "rows": len(rows),
        "progress_csv": str(PROGRESS_CSV),
        "out_csv": str(OUT_CSV),
    }})
except Exception as exc:
    emit_error("pyaedt_fem_export_failed", exc, "inspect_pyaedt_fem_export_logs")
'''


def write_launch_owned_probe_script(port: int, job_id: str) -> str:
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    job_id = _safe_job_id(job_id)
    path = out_dir / f"pyaedt_launch_owned_probe_{job_id}.py"
    path.write_text(pyaedt_launch_owned_probe_script(port=port, job_id=job_id), encoding="utf-8")
    return _relative(path)


def write_project_probe_script(project: str, port: int, job_id: str) -> str:
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    job_id = _safe_job_id(job_id)
    path = out_dir / f"pyaedt_project_probe_{job_id}.py"
    path.write_text(pyaedt_project_probe_script(project=project, port=port, job_id=job_id), encoding="utf-8")
    return _relative(path)


def write_fem_export_script(**kwargs: Any) -> str:
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    job_id = _safe_job_id(str(kwargs["job_id"]))
    path = out_dir / f"pyaedt_fem_export_{job_id}.py"
    path.write_text(pyaedt_fem_export_script(**kwargs), encoding="utf-8")
    return _relative(path)


def launch_owned_probe_procedure(
    port: int = 50052,
    job_id: str = "pyaedt_launch_probe",
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    _validate_port(port)
    job_id = _safe_job_id(job_id)
    script = write_launch_owned_probe_script(port, job_id)
    commands = ["$ErrorActionPreference = 'Stop'", *_python_setup_commands(), *_run_script_commands(script, job_id, timeout_seconds)]
    return policy.user_action_required(
        reason="PyAEDT launch-owned mode must run in native user PowerShell so Codex does not own AEDT process/session state.",
        risk_level="medium",
        procedure_id=f"pyaedt_launch_owned_probe_{job_id}",
        commands=commands,
        expected_output=["AEDT_MCP_RESULT_JSON with mode=pyaedt_launch_owned and aedt_version"],
        paste_back=[f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.log", f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.err.log"],
        log_paths=[f"tmp/aedt_jobs/{job_id}"],
        cleanup=["If it times out or leaves duplicate AEDT processes, run aedt.generate_stop_duplicate_aedt_procedure."],
    )


def project_probe_procedure(
    project: str,
    port: int = 50052,
    job_id: str = "pyaedt_project_probe",
    timeout_seconds: int = 300,
) -> dict[str, Any]:
    _validate_port(port)
    job_id = _safe_job_id(job_id)
    script = write_project_probe_script(project, port, job_id)
    commands = ["$ErrorActionPreference = 'Stop'", *_python_setup_commands(), *_run_script_commands(script, job_id, timeout_seconds)]
    return policy.user_action_required(
        reason="PyAEDT project probing launches/opens AEDT from a user-run process and opens only a workspace copy.",
        risk_level="medium",
        procedure_id=f"pyaedt_project_probe_{job_id}",
        commands=commands,
        expected_output=["AEDT_MCP_RESULT_JSON with copied_project and designs metadata"],
        paste_back=[f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.log", f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.err.log"],
        log_paths=[f"tmp/aedt_jobs/{job_id}", f"tmp/aedt_projects/{job_id}"],
        cleanup=["Use the copied_project path for the following PyAEDT FEM export procedure."],
    )


def fem_export_procedure(
    *,
    project_copy: str,
    design: str,
    setup: str,
    port: int = 50052,
    job_id: str = "pyaedt_fem_export_smoke",
    phase_a: str = "Phase_A",
    phase_b: str = "Phase_B",
    phase_c: str = "Phase_C",
    n_id: int = 2,
    n_iq: int = 2,
    i_rated: float = 150.0,
    theta_re: float = 0.0,
    solve: bool = True,
    resume: bool = True,
    out: str = "data/flux_map_fem.csv",
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    _validate_port(port)
    if n_id < 2 or n_iq < 2:
        raise ValueError("n_id and n_iq must each be at least 2")
    if n_id * n_iq > 1600:
        raise ValueError("grid cannot exceed 1600 points")
    if not design or not setup:
        raise ValueError("design and setup are required")
    job_id = _safe_job_id(job_id)
    script = write_fem_export_script(
        project_copy=project_copy,
        design=design,
        setup=setup,
        port=port,
        job_id=job_id,
        phase_a=phase_a,
        phase_b=phase_b,
        phase_c=phase_c,
        n_id=n_id,
        n_iq=n_iq,
        i_rated=i_rated,
        theta_re=theta_re,
        solve=solve,
        resume=resume,
        out=out,
    )
    commands = ["$ErrorActionPreference = 'Stop'", *_python_setup_commands(), *_run_script_commands(script, job_id, timeout_seconds)]
    return policy.user_action_required(
        reason="PyAEDT FEM export solves/reads AEDT data from native user PowerShell and writes a resumable workspace CSV.",
        risk_level="medium",
        procedure_id=f"pyaedt_fem_export_{job_id}",
        commands=commands,
        expected_output=["AEDT_MCP_RESULT_JSON with progress_csv, out_csv, and row count"],
        paste_back=[f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.log", f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.err.log", f"tmp\\aedt_jobs\\{job_id}\\progress.csv"],
        log_paths=[f"tmp/aedt_jobs/{job_id}", out],
        cleanup=["Start with 2x2, then 5x5, then 40x40 only after validation passes."],
    )


def process_inventory_procedure() -> dict[str, Any]:
    commands = [
        "$ErrorActionPreference = 'Stop'",
        f"$projectRoot = '{policy.PROJECT_ROOT}'",
        "Set-Location -LiteralPath $projectRoot",
        "New-Item -ItemType Directory -Force -Path 'tmp\\aedt_jobs' | Out-Null",
        "$out = 'tmp\\aedt_jobs\\aedt_process_inventory_user_run.log'",
        "Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'ansysedt|ansysedtsv|python|pwsh' } | Select-Object ProcessId,Name,CommandLine | Sort-Object Name,ProcessId | Format-List | Out-File -FilePath $out -Encoding utf8",
        "Get-NetTCPConnection -LocalPort 50052 -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess,CreationTime | Format-List | Add-Content -Path $out",
        "Get-Content -Path $out",
    ]
    return policy.user_action_required(
        reason="AEDT process inventory is a native Windows inspection step; Codex parses the pasted result afterward.",
        risk_level="medium",
        procedure_id="aedt_process_inventory",
        commands=commands,
        expected_output=["ansysedt/ansysedtsv PIDs and any TCP listener ownership for port 50052"],
        paste_back=["tmp\\aedt_jobs\\aedt_process_inventory_user_run.log"],
        log_paths=["tmp/aedt_jobs/aedt_process_inventory_user_run.log"],
        cleanup=["No processes are stopped by this inventory procedure."],
    )


def stop_duplicate_aedt_procedure(keep_pid: int | None = None) -> dict[str, Any]:
    keep_clause = "" if keep_pid is None else f" | Where-Object {{ $_.ProcessId -ne {keep_pid} }}"
    commands = [
        "$ErrorActionPreference = 'Stop'",
        f"$projectRoot = '{policy.PROJECT_ROOT}'",
        "Set-Location -LiteralPath $projectRoot",
        "New-Item -ItemType Directory -Force -Path 'tmp\\aedt_jobs' | Out-Null",
        "$log = 'tmp\\aedt_jobs\\stop_duplicate_aedt_user_run.log'",
        f"$targets = Get-CimInstance Win32_Process | Where-Object {{ $_.Name -match 'ansysedt|ansysedtsv' }}{keep_clause}",
        "$targets | Select-Object ProcessId,Name,CommandLine | Format-List | Out-File -FilePath $log -Encoding utf8",
        "foreach ($target in $targets) { Stop-Process -Id $target.ProcessId -Force; \"Stopped AEDT PID $($target.ProcessId)\" | Add-Content -Path $log }",
        "Get-Content -Path $log",
    ]
    return policy.user_action_required(
        reason="Stopping AEDT is destructive runtime process control and must be explicitly run by the human in PowerShell.",
        risk_level="high",
        procedure_id="stop_duplicate_aedt",
        commands=commands,
        expected_output=["A list of stopped AEDT PIDs, excluding keep_pid when provided."],
        paste_back=["tmp\\aedt_jobs\\stop_duplicate_aedt_user_run.log"],
        log_paths=["tmp/aedt_jobs/stop_duplicate_aedt_user_run.log"],
        cleanup=["Re-run aedt.generate_aedt_process_inventory after cleanup."],
    )


def parse_prefixed_json(text: str) -> dict[str, Any]:
    parsed = scriptenv_workflow.parse_prefixed_json(text)
    if parsed.get("status") == "error":
        error = parsed.get("error", {})
        category = error.get("category", "")
        if category.startswith("pyaedt_"):
            parsed["recommended_next_step"] = error.get("recommended_next_step", "inspect_pyaedt_logs")
    return parsed


def export_status(job_id: str = "pyaedt_fem_export_smoke", out: str = "data/flux_map_fem.csv") -> dict[str, Any]:
    return scriptenv_workflow.fem_export_status(job_id=job_id, out=out)

