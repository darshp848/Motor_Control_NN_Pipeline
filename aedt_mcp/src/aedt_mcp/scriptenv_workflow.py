"""ScriptEnv-first AEDT procedure and script generation."""

from __future__ import annotations

import csv
import json
import math
import re
from pathlib import Path
from typing import Any

from . import execution_policy as policy

FEM_HEADER = ("Id", "Iq", "Phi_d", "Phi_q")


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
    ]


def _start_process_commands(script: str, job_id: str, timeout_seconds: int) -> list[str]:
    job_id = _safe_job_id(job_id)
    log_dir = f"tmp\\aedt_jobs\\{job_id}"
    stem = Path(script).stem
    return [
        f"New-Item -ItemType Directory -Force -Path '{log_dir}' | Out-Null",
        f"$proc = Start-Process -FilePath $pythonExe -ArgumentList @('{script}') -RedirectStandardOutput '{log_dir}\\{stem}.log' -RedirectStandardError '{log_dir}\\{stem}.err.log' -NoNewWindow -PassThru",
        f"$null = Wait-Process -Id $proc.Id -Timeout {timeout_seconds} -ErrorAction SilentlyContinue",
        f"if (-not $proc.HasExited) {{ Stop-Process -Id $proc.Id -Force; 'Script timed out after {timeout_seconds}s and was stopped by the user-run procedure.' | Add-Content '{log_dir}\\{stem}.err.log' }}",
    ]


def _common_scriptenv_python(port: int) -> str:
    return f'''
import json
import os
import sys
import traceback
from pathlib import Path

PORT = {port}
RESULT_PREFIX = "AEDT_MCP_RESULT_JSON="
ERROR_PREFIX = "AEDT_MCP_ERROR_JSON="

def emit_result(payload):
    print(RESULT_PREFIX + json.dumps(payload, sort_keys=True))

def emit_error(category, message, next_step="paste_output_back", extra=None):
    payload = {{
        "status": "error",
        "category": category,
        "message": str(message),
        "recommended_next_step": next_step,
        "traceback": traceback.format_exc(limit=6),
    }}
    if extra:
        payload.update(extra)
    print(ERROR_PREFIX + json.dumps(payload, sort_keys=True))

def desktop_plugin_path():
    roots = [
        os.environ.get("ANSYSEMSV_ROOT252"),
        os.environ.get("ANSYSEM_ROOT252"),
        r"C:\\Program Files\\ANSYS Inc\\ANSYS Student\\v252\\AnsysEM",
        r"C:\\Program Files\\ANSYS Inc\\v252\\AnsysEM",
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
    ScriptEnv.Initialize("", False, "localhost", {port})
    return globals()["oDesktop"]
'''


def scriptenv_probe_script(port: int = 50052) -> str:
    _validate_port(port)
    return _common_scriptenv_python(port) + '''
try:
    desktop = attach_desktop()
    emit_result({
        "status": "ok",
        "port": PORT,
        "aedt_version": desktop.GetVersion(),
    })
except Exception as exc:
    emit_error("scriptenv_attach", exc, "check_aedt_listener_or_launch_procedure")
'''


def scriptenv_project_probe_script(port: int, project: str, job_id: str) -> str:
    _validate_port(port)
    job_id = _safe_job_id(job_id)
    source = str(Path(project))
    copy_dir = policy.PROJECT_ROOT / "tmp" / "aedt_projects" / job_id
    return _common_scriptenv_python(port) + f'''
import shutil

SOURCE_PROJECT = Path(r"{source}")
COPY_DIR = Path(r"{copy_dir}")

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
        raise RuntimeError(f"OpenProject failed and project is not loaded: {{open_error}}")
    project_name = new_projects[-1] if new_projects else copied.stem
    project = desktop.SetActiveProject(project_name)
    designs = []
    for raw_design in list_or_empty(project.GetTopDesignList):
        design_name = str(raw_design).split(";")[-1]
        item = {{"name": design_name, "raw_name": str(raw_design), "type": None, "setups": [], "variables": [], "excitations": []}}
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
    emit_result({{
        "status": "ok",
        "job_id": "{job_id}",
        "source_project": str(SOURCE_PROJECT),
        "copied_project": str(copied),
        "project_name": project_name,
        "projects": projects,
        "designs": designs,
    }})
except Exception as exc:
    emit_error("project_probe", exc, "inspect_project_path_or_aedt_state")
'''


def scriptenv_fem_export_script(
    *,
    port: int,
    job_id: str,
    project_copy: str,
    design: str,
    setup: str,
    phase_a: str,
    phase_b: str,
    phase_c: str,
    n_id: int,
    n_iq: int,
    i_rated: float,
    theta_re: float,
    solve: bool,
    resume: bool,
    out: str,
) -> str:
    _validate_port(port)
    job_id = _safe_job_id(job_id)
    return _common_scriptenv_python(port) + f'''
import csv
import math

JOB_ID = "{job_id}"
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
OUT_CSV = Path(r"{policy.PROJECT_ROOT / out}")
JOB_DIR = Path(r"{policy.PROJECT_ROOT / 'tmp' / 'aedt_jobs' / job_id}")
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

def set_variables(design, id_val, iq_val):
    ia, ib, ic = abc_from_dq(id_val, iq_val, THETA_RE)
    for name, value in {{"Id": id_val, "Iq": iq_val, "Ia": ia, "Ib": ib, "Ic": ic}}.items():
        design.ChangeProperty([
            "NAME:AllTabs",
            [
                "NAME:LocalVariableTab",
                ["NAME:PropServers", "LocalVariables"],
                ["NAME:ChangedProps", ["NAME:" + name, "Value:=", f"{{value:.9g}}A"]],
            ],
        ])

def solve_design(design):
    design.Analyze(SETUP_NAME)

def read_flux(design):
    report = design.GetModule("ReportSetup")
    values = []
    for phase in PHASES:
        expr = f"FluxLinkage({{phase}})"
        try:
            data = report.GetSolutionDataPerVariation("Standard", SETUP_NAME, [], [expr])
            real_data = data.GetRealDataValues(expr)
            if not real_data:
                raise RuntimeError(f"empty data for {{expr}}")
            values.append(float(real_data[0]))
        except Exception as exc:
            raise RuntimeError(f"failed reading {{expr}}: {{exc}}") from exc
    return tuple(values)

try:
    if not PROJECT_COPY.exists():
        raise FileNotFoundError(str(PROJECT_COPY))
    desktop = attach_desktop()
    if str(PROJECT_COPY) not in [str(p) for p in getattr(desktop, "GetProjectList", lambda: [])()]:
        desktop.OpenProject(str(PROJECT_COPY))
    project = desktop.SetActiveProject(PROJECT_COPY.stem)
    design = project.SetActiveDesign(DESIGN_NAME)
    grid = current_grid()
    if not RESUME and PROGRESS_CSV.exists():
        PROGRESS_CSV.unlink()
    completed = read_progress()
    for index, (id_val, iq_val) in enumerate(grid, start=1):
        key = (float(f"{{id_val:.6f}}"), float(f"{{iq_val:.6f}}"))
        if key in completed:
            continue
        print(f"[fem_export] {{index}}/{{len(grid)}} Id={{id_val:.3f}} Iq={{iq_val:.3f}}", flush=True)
        set_variables(design, id_val, iq_val)
        if SOLVE:
            solve_design(design)
        psi_a, psi_b, psi_c = read_flux(design)
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
        "rows": len(rows),
        "progress_csv": str(PROGRESS_CSV),
        "out_csv": str(OUT_CSV),
    }})
except Exception as exc:
    emit_error("fem_export", exc, "inspect_fem_export_logs")
'''


def write_scriptenv_probe_script(port: int) -> str:
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"scriptenv_probe_{port}.py"
    path.write_text(scriptenv_probe_script(port), encoding="utf-8")
    return _relative(path)


def write_project_probe_script(port: int, project: str, job_id: str) -> str:
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"scriptenv_project_probe_{port}_{_safe_job_id(job_id)}.py"
    path.write_text(scriptenv_project_probe_script(port, project, job_id), encoding="utf-8")
    return _relative(path)


def write_fem_export_script(**kwargs: Any) -> str:
    out_dir = policy.PROJECT_ROOT / "scripts" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    job_id = _safe_job_id(str(kwargs["job_id"]))
    path = out_dir / f"scriptenv_fem_export_{job_id}.py"
    path.write_text(scriptenv_fem_export_script(**kwargs), encoding="utf-8")
    return _relative(path)


def scriptenv_probe_procedure(port: int = 50052, timeout_seconds: int = 45) -> dict[str, Any]:
    _validate_port(port)
    script = write_scriptenv_probe_script(port)
    job_id = f"scriptenv_probe_{port}"
    commands = ["$ErrorActionPreference = 'Stop'", *_python_setup_commands(), *_start_process_commands(script, job_id, timeout_seconds)]
    return policy.user_action_required(
        reason="ScriptEnv attach must be run from native PowerShell against the live AEDT gRPC process.",
        risk_level="medium",
        procedure_id=job_id,
        commands=commands,
        expected_output=["AEDT_MCP_RESULT_JSON with aedt_version such as 2025.2.0"],
        paste_back=[f"tmp\\aedt_jobs\\{job_id}\\scriptenv_probe_{port}.log", f"tmp\\aedt_jobs\\{job_id}\\scriptenv_probe_{port}.err.log"],
        log_paths=[f"tmp/aedt_jobs/{job_id}"],
        cleanup=["Only the helper Python process is timeout-stopped by the procedure; AEDT remains running."],
    )


def project_probe_procedure(project: str, port: int = 50052, job_id: str = "project_probe", timeout_seconds: int = 120) -> dict[str, Any]:
    _validate_port(port)
    job_id = _safe_job_id(job_id)
    script = write_project_probe_script(port, project, job_id)
    commands = ["$ErrorActionPreference = 'Stop'", *_python_setup_commands(), *_start_process_commands(script, job_id, timeout_seconds)]
    return policy.user_action_required(
        reason="Opening AEDT projects is a user-run native AEDT action; this probes only a workspace copy.",
        risk_level="medium",
        procedure_id=f"project_probe_{job_id}",
        commands=commands,
        expected_output=["AEDT_MCP_RESULT_JSON with copied_project and designs metadata"],
        paste_back=[f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.log", f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.err.log"],
        log_paths=[f"tmp/aedt_jobs/{job_id}", f"tmp/aedt_projects/{job_id}"],
        cleanup=["Leave AEDT running for the following FEM export procedure."],
    )


def fem_export_plan(stage: str = "smoke", i_rated: float = 150.0, theta_re: float = 0.0) -> dict[str, Any]:
    stages = {"smoke": (2, 2), "validation": (5, 5), "full": (40, 40)}
    if stage not in stages:
        raise ValueError("stage must be one of smoke, validation, full")
    n_id, n_iq = stages[stage]
    return {
        "status": "ok",
        "stage": stage,
        "n_id": n_id,
        "n_iq": n_iq,
        "rows": n_id * n_iq,
        "i_rated": i_rated,
        "theta_re": theta_re,
        "csv_header": FEM_HEADER,
        "next_step": "generate_fem_export_procedure",
    }


def fem_export_procedure(
    *,
    project_copy: str,
    design: str,
    setup: str,
    port: int = 50052,
    job_id: str = "fem_export_smoke",
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
        port=port,
        job_id=job_id,
        project_copy=project_copy,
        design=design,
        setup=setup,
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
    commands = ["$ErrorActionPreference = 'Stop'", *_python_setup_commands(), *_start_process_commands(script, job_id, timeout_seconds)]
    return policy.user_action_required(
        reason="FEM export solves/reads AEDT data and must run in native PowerShell through ScriptEnv.",
        risk_level="medium",
        procedure_id=f"fem_export_{job_id}",
        commands=commands,
        expected_output=["AEDT_MCP_RESULT_JSON with progress_csv, out_csv, and row count"],
        paste_back=[f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.log", f"tmp\\aedt_jobs\\{job_id}\\{Path(script).stem}.err.log", f"tmp\\aedt_jobs\\{job_id}\\progress.csv"],
        log_paths=[f"tmp/aedt_jobs/{job_id}", out],
        cleanup=["Start with 2x2, then 5x5, then 40x40 only after validation passes."],
    )


def parse_prefixed_json(text: str) -> dict[str, Any]:
    result = None
    error = None
    for line in text.splitlines():
        if line.startswith("AEDT_MCP_RESULT_JSON="):
            result = json.loads(line.split("=", 1)[1])
        elif line.startswith("AEDT_MCP_ERROR_JSON="):
            error = json.loads(line.split("=", 1)[1])
    if result is not None:
        return {"status": "ok", "result": result, "recommended_next_step": _next_step_from_result(result)}
    if error is not None:
        return {"status": "error", "error": error, "recommended_next_step": error.get("recommended_next_step", "inspect_logs")}
    return {"status": "unknown", "recommended_next_step": _classify_unstructured(text)}


def _next_step_from_result(result: dict[str, Any]) -> str:
    if "aedt_version" in result:
        return "generate_project_probe_procedure"
    if "designs" in result:
        return "select_maxwell_design_and_generate_fem_export_plan"
    if "out_csv" in result:
        return "validate_fem_export_status"
    return "continue"


def _classify_unstructured(text: str) -> str:
    lowered = text.lower()
    if "non-finite" in lowered:
        return "inspect_non_finite_rows"
    if "setup" in lowered and ("not found" in lowered or "missing" in lowered):
        return "select_valid_setup_from_project_probe"
    if "design" in lowered and ("not found" in lowered or "missing" in lowered):
        return "select_valid_design_from_project_probe"
    if "timed out" in lowered or "timeout" in lowered:
        return "reduce_grid_or_check_solve_hang"
    if "license" in lowered:
        return "manual_aedt_gui_license_check"
    return "paste_full_logs_or_run_parse_logs"


def fem_export_status(job_id: str = "fem_export_smoke", out: str = "data/flux_map_fem.csv") -> dict[str, Any]:
    job_id = _safe_job_id(job_id)
    progress = policy.PROJECT_ROOT / "tmp" / "aedt_jobs" / job_id / "progress.csv"
    final = policy.PROJECT_ROOT / out
    return {
        "status": "ok",
        "job_id": job_id,
        "progress_csv": _csv_status(progress),
        "final_csv": _csv_status(final),
        "expected_header": FEM_HEADER,
    }


def _csv_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "path": str(path)}
    rows = 0
    finite = True
    header_ok = False
    with path.open(newline="") as f:
        reader = csv.DictReader(f)
        header_ok = tuple(reader.fieldnames or ()) == FEM_HEADER
        for row in reader:
            rows += 1
            try:
                finite = finite and all(math.isfinite(float(row[name])) for name in FEM_HEADER)
            except (KeyError, TypeError, ValueError):
                finite = False
    return {"exists": True, "path": str(path), "relative_path": _relative(path), "header_ok": header_ok, "row_count": rows, "finite": finite}
