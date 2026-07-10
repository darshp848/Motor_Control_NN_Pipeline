
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
JOB_ID = "unit_pyaedt_export"
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

PROJECT_COPY = Path(r"C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp\tmp\aedt_projects\unit_pyaedt_project\project.aedt")
DESIGN_NAME = 'Maxwell3DDesign1'
SETUP_NAME = 'Setup1'
PHASES = ('Phase_A', 'Phase_B', 'Phase_C')
N_ID = 2
N_IQ = 2
I_RATED = 150.0
THETA_RE = 0.0
SOLVE = True
RESUME = True
OUT_CSV = PROJECT_ROOT / r"data/flux_map_fem.csv"
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
    for name, value in {"Id": id_val, "Iq": iq_val, "Ia": ia, "Ib": ib, "Ic": ic}.items():
        app[name] = f"{value:.9g}A"

def read_flux(app):
    values = []
    for phase in PHASES:
        expr = f"FluxLinkage({phase})"
        try:
            data = app.post.get_solution_data(expressions=[expr], setup_sweep_name=SETUP_NAME)
            raw = getattr(data, "data_real", lambda expression=None: [])(expr)
            if not raw:
                raw = getattr(data, "full_matrix_real_imag", [])
            if not raw:
                raise RuntimeError(f"empty data for {expr}")
            values.append(float(raw[0]))
        except Exception as exc:
            raise RuntimeError(f"failed reading {expr}: {exc}") from exc
    return tuple(values)

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
        raise RuntimeError(f"missing design {DESIGN_NAME}")
    setup_names = list(getattr(app, "setup_names", []) or [])
    if setup_names and SETUP_NAME not in setup_names:
        raise RuntimeError(f"missing setup {SETUP_NAME}; available={setup_names}")
    grid = current_grid()
    completed = read_progress()
    for index, (id_val, iq_val) in enumerate(grid, start=1):
        key = (float(f"{id_val:.6f}"), float(f"{iq_val:.6f}"))
        if key in completed:
            continue
        print(f"[pyaedt_fem_export] {index}/{len(grid)} Id={id_val:.3f} Iq={iq_val:.3f}", flush=True)
        set_variables(app, id_val, iq_val)
        if SOLVE:
            app.analyze_setup(SETUP_NAME)
        psi_a, psi_b, psi_c = read_flux(app)
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
        "mode": "pyaedt_launch_owned",
        "rows": len(rows),
        "progress_csv": str(PROGRESS_CSV),
        "out_csv": str(OUT_CSV),
    })
except Exception as exc:
    emit_error("pyaedt_fem_export_failed", exc, "inspect_pyaedt_fem_export_logs")
