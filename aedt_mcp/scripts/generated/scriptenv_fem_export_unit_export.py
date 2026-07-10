
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

import csv
import math

JOB_ID = "unit_export"
PROJECT_COPY = Path(r"tmp/aedt_projects/unit_probe/ipm_1.aedt")
DESIGN_NAME = 'Maxwell2DDesign1'
SETUP_NAME = 'Setup1'
PHASES = ('Phase_A', 'Phase_B', 'Phase_C')
N_ID = 2
N_IQ = 2
I_RATED = 150.0
THETA_RE = 0.0
SOLVE = True
RESUME = True
OUT_CSV = Path(r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp\data\flux_map_fem.csv")
JOB_DIR = Path(r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp\tmp\aedt_jobs\unit_export")
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
    rows = {}
    if not PROGRESS_CSV.exists() or not RESUME:
        return rows
    with PROGRESS_CSV.open(newline="") as f:
        reader = csv.DictReader(f)
        if tuple(reader.fieldnames or ()) != HEADER:
            raise ValueError(f"unexpected progress header: {reader.fieldnames}")
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
        writer.writerow([f"{row[0]:.6f}", f"{row[1]:.6f}", f"{row[2]:.9f}", f"{row[3]:.9f}"])

def set_variables(design, id_val, iq_val):
    ia, ib, ic = abc_from_dq(id_val, iq_val, THETA_RE)
    for name, value in {"Id": id_val, "Iq": iq_val, "Ia": ia, "Ib": ib, "Ic": ic}.items():
        design.ChangeProperty([
            "NAME:AllTabs",
            [
                "NAME:LocalVariableTab",
                ["NAME:PropServers", "LocalVariables"],
                ["NAME:ChangedProps", ["NAME:" + name, "Value:=", f"{value:.9g}A"]],
            ],
        ])

def solve_design(design):
    design.Analyze(SETUP_NAME)

def read_flux(design):
    report = design.GetModule("ReportSetup")
    values = []
    for phase in PHASES:
        expr = f"FluxLinkage({phase})"
        try:
            data = report.GetSolutionDataPerVariation("Standard", SETUP_NAME, [], [expr])
            real_data = data.GetRealDataValues(expr)
            if not real_data:
                raise RuntimeError(f"empty data for {expr}")
            values.append(float(real_data[0]))
        except Exception as exc:
            raise RuntimeError(f"failed reading {expr}: {exc}") from exc
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
        key = (float(f"{id_val:.6f}"), float(f"{iq_val:.6f}"))
        if key in completed:
            continue
        print(f"[fem_export] {index}/{len(grid)} Id={id_val:.3f} Iq={iq_val:.3f}", flush=True)
        set_variables(design, id_val, iq_val)
        if SOLVE:
            solve_design(design)
        psi_a, psi_b, psi_c = read_flux(design)
        phi_d, phi_q = dq_from_abc(psi_a, psi_b, psi_c, THETA_RE)
        row = (key[0], key[1], phi_d, phi_q)
        if not all(math.isfinite(x) for x in row):
            raise RuntimeError(f"non-finite row: {row}")
        append_progress(row)
        completed[key] = row
    rows = [completed[(float(f"{idv:.6f}"), float(f"{iqv:.6f}"))] for idv, iqv in grid]
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        for row in rows:
            writer.writerow([f"{row[0]:.6f}", f"{row[1]:.6f}", f"{row[2]:.9f}", f"{row[3]:.9f}"])
    emit_result({
        "status": "ok",
        "job_id": JOB_ID,
        "rows": len(rows),
        "progress_csv": str(PROGRESS_CSV),
        "out_csv": str(OUT_CSV),
    })
except Exception as exc:
    emit_error("fem_export", exc, "inspect_fem_export_logs")
