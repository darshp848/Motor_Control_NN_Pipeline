"""Task 9 one-point-per-session AEDT GUI exporter (IronPython 2.7 safe)."""

import csv
import hashlib
import json
import math
import os
import re
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
CAMPAIGN_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "task9_baseline")
RAW_ROOT = os.path.join(CAMPAIGN_ROOT, "raw")
POINTS = os.path.join(CAMPAIGN_ROOT, "frozen_points.csv")
PROGRESS = os.path.join(RAW_ROOT, "campaign_progress.csv")
STATUS_JSON = os.path.join(RAW_ROOT, "campaign_status.json")
EXPORT_DIR = os.path.join(RAW_ROOT, "point_exports")
EVIDENCE_DIR = os.path.join(RAW_ROOT, "solver_evidence")
POINTS_SHA256 = "3ce7f7bd4bc2abbe7aefb425d2923fa488286603c32ec506d20eecbbc361fb6d"
PROJECT_NAME = "eesm_qual"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "eesm_qual", "eesm_qual.aedt"
)
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
POLE_PAIRS = 2
ROTOR_POSITION_DEG = 180.0
TORQUE_OUTPUT_NAME = "Torque_FEM"
MAX_NEW_POINTS_PER_RUN = 1
MAX_MESH_ELEMENTS = 1950
ADAPTIVE_NONCONVERGENCE_MARKER = "adaptive passes did not converge"
REPORT_NAME = "EESM_Task9_Flux_ABC"
EXPRESSIONS = ["FluxLinkage(PhaseA)", "FluxLinkage(PhaseB)", "FluxLinkage(PhaseC)"]
POINT_FIELDS = [
    "PointName", "point_id", "role", "region", "Id [A]", "Iq [A]",
    "If [A]", "campaign_id", "seed", "sample_index",
]
FIELDS = [
    "PointName", "PointID", "Role", "Region", "Id [A]", "Iq [A]", "If [A]",
    "Flux_d [Wb]", "Flux_q [Wb]", "Torque [N*m]", "Project", "Design", "Setup",
    "RotorPosition [deg]", "MeshElements [count]", "AdaptivePasses [count]",
    "SolverStatus", "SolverMessage", "PolePairs [count]", "RawABCFluxPath",
    "MeshEvidencePath", "ConvergenceEvidencePath",
]


def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def call(fn):
    try:
        raw_value = fn()
        return {"ok": True, "value": normalize(raw_value), "_raw": raw_value}
    except BaseException as exc:
        return {"ok": False, "error": str(exc),
                "traceback_tail": traceback.format_exc().splitlines()[-8:]}


def required(fn, label):
    outcome = call(fn)
    if not outcome["ok"]:
        raise RuntimeError(label + ": " + outcome["error"])
    return outcome["_raw"]


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(65536)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def write_status(payload):
    if not os.path.exists(RAW_ROOT):
        os.makedirs(RAW_ROOT)
    with open(STATUS_JSON, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def mark_stage(payload, point_name, stage):
    payload["active_point"] = point_name
    payload["stage"] = stage
    write_status(payload)


def is_finite(value):
    try:
        return not (math.isnan(value) or math.isinf(value))
    except BaseException:
        return False


def _format_current(value):
    rounded = round(float(value), 9)
    if rounded == 0.0:
        rounded = 0.0
    return "%.9f" % rounded


def canonical_point_id(values):
    payload = "|".join(_format_current(value) for value in values)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()[:16]


def dq_from_abc(phi_a, phi_b, phi_c, theta_re):
    phi_d = (2.0 / 3.0) * (phi_a * math.cos(theta_re)
        + phi_b * math.cos(theta_re - 2 * math.pi / 3)
        + phi_c * math.cos(theta_re + 2 * math.pi / 3))
    phi_q = (2.0 / 3.0) * (-phi_a * math.sin(theta_re)
        - phi_b * math.sin(theta_re - 2 * math.pi / 3)
        - phi_c * math.sin(theta_re + 2 * math.pi / 3))
    return phi_d, phi_q


def abc_from_dq(id_value, iq_value, theta_re):
    return tuple(id_value * math.cos(angle) - iq_value * math.sin(angle)
        for angle in (theta_re, theta_re - 2 * math.pi / 3,
                      theta_re + 2 * math.pi / 3))


def numeric_output(value, name):
    try:
        number = float(str(value).split()[0])
    except BaseException:
        raise RuntimeError(name + " was not a plain numeric value in declared SI units")
    if not is_finite(number):
        raise RuntimeError(name + " was non-finite")
    return number


def read_flux_csv(path):
    with open(path, "r") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        rows = list(reader)
    if len(header) < 4 or not rows:
        raise RuntimeError("Incomplete ABC flux CSV: " + path)
    last = rows[-1]
    values = (float(last[1]), float(last[2]), float(last[3]))
    if not all(is_finite(value) for value in values):
        raise RuntimeError("Non-finite ABC flux CSV: " + path)
    return values


def _positive_integers(text):
    return [int(item) for item in re.findall(r"(?<![.\d])-?\d+(?![.\d])", text)
            if int(item) > 0]


def export_solver_evidence(design, point_name):
    mesh_path = os.path.join(EVIDENCE_DIR, point_name + "_mesh.ms")
    convergence_path = os.path.join(EVIDENCE_DIR, point_name + "_convergence.conv")
    for path in (mesh_path, convergence_path):
        if os.path.exists(path):
            raise RuntimeError("Refusing to overwrite orphaned solver evidence: " + path)
    required(lambda: design.ExportMeshStats(SETUP_NAME, "", mesh_path, True),
        "Export measured mesh statistics")
    required(lambda: design.ExportConvergence(SETUP_NAME, "", convergence_path, True),
        "Export measured convergence history")
    for path in (mesh_path, convergence_path):
        if not (os.path.exists(path) and os.path.getsize(path) > 0):
            raise RuntimeError("Missing/empty solver evidence: " + path)
    with open(mesh_path, "r") as stream:
        total_lines = [line for line in stream.readlines() if "total" in line.lower()]
    mesh_values = []
    for line in total_lines:
        mesh_values.extend(_positive_integers(line))
    if not mesh_values:
        raise RuntimeError("Could not derive total mesh elements from " + mesh_path)
    with open(convergence_path, "r") as stream:
        convergence_lines = stream.readlines()
    pass_values = []
    in_pass_summary = False
    for line in convergence_lines:
        lowered = line.lower()
        if "number of passes" in lowered:
            in_pass_summary = True
            continue
        if in_pass_summary and "completed" in lowered:
            pass_values.extend(_positive_integers(line))
            break
    if not pass_values:
        raise RuntimeError("Could not derive adaptive passes from " + convergence_path)
    mesh_elements = max(mesh_values)
    if mesh_elements > MAX_MESH_ELEMENTS:
        raise RuntimeError("AEDT Student mesh limit exceeded: " + str(mesh_elements))
    return mesh_elements, max(pass_values), mesh_path, convergence_path


def export_flux(design, path):
    if os.path.exists(path):
        raise RuntimeError("Refusing to overwrite orphaned ABC flux evidence: " + path)
    report = required(lambda: design.GetModule("ReportSetup"), "Get ReportSetup")
    names = required(report.GetAllReportNames, "Get report names")
    if REPORT_NAME in list(names):
        required(lambda: report.DeleteReports([REPORT_NAME]), "Delete owned report")
    required(lambda: report.CreateReport(REPORT_NAME, "Magnetostatic", "Data Table",
        SOLUTION_NAME, [], ["fractions:=", ["All"]],
        ["X Component:=", "fractions", "Y Component:=", EXPRESSIONS]),
        "Create ABC flux report")
    required(lambda: report.ExportToFile(REPORT_NAME, path), "Export ABC flux report")
    if not (os.path.exists(path) and os.path.getsize(path) > 0):
        raise RuntimeError("ExportToFile returned but file missing/empty: " + path)
    values = read_flux_csv(path)
    required(lambda: report.DeleteReports([REPORT_NAME]), "Delete exported ABC flux report")
    return values


def change_currents(design, row):
    changed = []
    for name in ("Id", "Iq", "If"):
        changed.append(["NAME:" + name, "Value:=", row[name + " [A]"] + "A"])
    required(lambda: design.ChangeProperty(["NAME:AllTabs", ["NAME:LocalVariableTab",
        ["NAME:PropServers", "LocalVariables"], ["NAME:ChangedProps"] + changed]]),
        "Change Id/Iq/If local variables")
    theta_re = ROTOR_POSITION_DEG * math.pi / 180.0
    phase_values = abc_from_dq(float(row["Id [A]"]), float(row["Iq [A]"]), theta_re)
    boundary = required(lambda: design.GetModule("BoundarySetup"), "Get BoundarySetup")
    for phase, value in zip(("PhaseA", "PhaseB", "PhaseC"), phase_values):
        current = "%.12gA" % value
        required(lambda phase=phase, current=current: boundary.EditWindingGroup(
            phase, ["NAME:" + phase, "Type:=", "Current", "Current:=", current]),
            "Apply numeric current to " + phase)
    field_current = "%.12gA" % float(row["If [A]"])
    required(lambda: boundary.EditWindingGroup("Field", [
        "NAME:Field", "Type:=", "Current", "Current:=", field_current]),
        "Apply numeric field current")


def restore_parametric_currents(design):
    boundary = required(lambda: design.GetModule("BoundarySetup"), "Get BoundarySetup")
    expressions = {"PhaseA": "I_phase_a", "PhaseB": "I_phase_b",
                   "PhaseC": "I_phase_c", "Field": "If"}
    for winding, expression in expressions.items():
        required(lambda winding=winding, expression=expression:
            boundary.EditWindingGroup(winding, ["NAME:" + winding,
                "Type:=", "Current", "Current:=", expression]),
            "Restore parametric current for " + winding)


def read_points():
    if sha256_file(POINTS) != POINTS_SHA256:
        raise RuntimeError("Frozen Task 9 point CSV hash mismatch")
    with open(POINTS, "r") as stream:
        reader = csv.DictReader(stream)
        if list(reader.fieldnames or []) != POINT_FIELDS:
            raise RuntimeError("Malformed frozen Task 9 point header")
        points = list(reader)
    if len(points) != 64:
        raise RuntimeError("Frozen Task 9 point budget must be exactly 64")
    names = [row["PointName"] for row in points]
    currents = []
    for row in points:
        values = tuple(float(row[name]) for name in ("Id [A]", "Iq [A]", "If [A]"))
        currents.append(values)
        if row["PointName"] != row["point_id"] or row["point_id"] != canonical_point_id(values):
            raise RuntimeError("Point identity mismatch: " + row["PointName"])
        if values == (0.0, 0.0, 0.0):
            raise RuntimeError("Source-free origin must remain analytic")
        if row["role"] not in ("train", "selection", "reference", "scheduler_audit"):
            raise RuntimeError("Unknown frozen point role")
    if len(set(names)) != len(names) or len(set(currents)) != len(currents):
        raise RuntimeError("Duplicate frozen Task 9 point")
    return points


def append_result(result):
    exists = os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0
    with open(PROGRESS, "ab") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\r\n")
        if not exists:
            writer.writeheader()
        writer.writerow(result)


def read_progress(expected):
    if not os.path.exists(PROGRESS):
        return [], set()
    with open(PROGRESS, "r") as stream:
        reader = csv.DictReader(stream)
        if list(reader.fieldnames or []) != FIELDS:
            raise RuntimeError("Refusing resume: malformed progress header")
        rows = list(reader)
    names = [row.get("PointName", "") for row in rows]
    if len(set(names)) != len(names):
        raise RuntimeError("Refusing resume: duplicated progress row")
    expected_by_name = dict((row["PointName"], row) for row in expected)
    for row in rows:
        name = row.get("PointName", "")
        if name not in expected_by_name:
            raise RuntimeError("Refusing resume: unknown progress point " + name)
        if row.get("SolverStatus", "").lower() != "converged":
            raise RuntimeError("Refusing resume: progress contains failed row " + name)
        frozen = expected_by_name[name]
        exact = (row.get("PointID") == frozen["point_id"]
            and row.get("Role") == frozen["role"] and row.get("Region") == frozen["region"]
            and all(float(row[key]) == float(frozen[key]) for key in ("Id [A]", "Iq [A]", "If [A]"))
            and row.get("Project") == PROJECT_NAME and row.get("Design") == DESIGN_NAME
            and row.get("Setup") == SETUP_NAME
            and float(row.get("RotorPosition [deg]", "nan")) == ROTOR_POSITION_DEG
            and int(float(row.get("PolePairs [count]", "0"))) == POLE_PAIRS)
        if not exact:
            raise RuntimeError("Refusing resume: inconsistent progress row " + name)
        expected_paths = {
            "RawABCFluxPath": os.path.join(EXPORT_DIR, name + "_flux_abc.csv"),
            "MeshEvidencePath": os.path.join(EVIDENCE_DIR, name + "_mesh.ms"),
            "ConvergenceEvidencePath": os.path.join(EVIDENCE_DIR, name + "_convergence.conv"),
        }
        for key, expected_path in expected_paths.items():
            path = row.get(key, "")
            if (os.path.normcase(os.path.abspath(path)) != os.path.normcase(os.path.abspath(expected_path))
                    or not os.path.exists(path) or os.path.getsize(path) <= 0):
                raise RuntimeError("Refusing resume: missing raw evidence for " + name)
        try:
            message_payload = json.loads(row.get("SolverMessage", "{}"))
            warnings = message_payload.get("warnings", [])
        except BaseException:
            raise RuntimeError("Refusing resume: malformed solver messages for " + name)
        if any(ADAPTIVE_NONCONVERGENCE_MARKER in str(item).lower() for item in warnings):
            raise RuntimeError("Refusing resume: adaptive convergence criteria were not met for " + name)
    return rows, set(names)


def read_prior_status():
    if not os.path.exists(STATUS_JSON):
        if os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0:
            raise RuntimeError("Refusing resume: progress exists without campaign status")
        return None
    try:
        with open(STATUS_JSON, "r") as stream:
            prior = json.load(stream)
    except BaseException:
        raise RuntimeError("Refusing resume: campaign status is malformed")
    if not (os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0):
        raise RuntimeError("Refusing resume: status exists without progress")
    allowed = (prior.get("status") == "partial_resume_required"
        and prior.get("stage") == "idle" and prior.get("active_point") is None
        and not prior.get("failure") and not prior.get("restore_error")
        and prior.get("points_sha256") == POINTS_SHA256)
    legacy_close = prior.get("close_error") in (None, "QuitApplication")
    if not (allowed and legacy_close):
        raise RuntimeError("Refusing resume: prior campaign status requires operator review")
    return prior


def solver_messages(project_name, design_name, solve_return):
    errors = normalize(required(lambda: oDesktop.GetMessages(project_name, design_name, 2),
        "Read AEDT error messages"))
    warnings = normalize(required(lambda: oDesktop.GetMessages(project_name, design_name, 1),
        "Read AEDT warning messages"))
    return {"solve_return": solve_return, "errors": errors or [], "warnings": warnings or []}


payload = {"status": "running", "completed": [], "failure": None,
           "campaign_id": "eesm_task9_real_baseline_20260715",
           "points_sha256": POINTS_SHA256, "max_new_points_per_run": MAX_NEW_POINTS_PER_RUN}
try:
    for directory in (RAW_ROOT, EXPORT_DIR, EVIDENCE_DIR):
        if not os.path.exists(directory):
            os.makedirs(directory)
    points = read_points()
    prior_status = read_prior_status()
    project = required(oDesktop.GetActiveProject, "Get active project")
    if project is None:
        project = required(lambda: oDesktop.OpenProject(PROJECT_PATH),
                           "Open qualified project")
    project_name = required(project.GetName, "Get project name")
    if project_name != PROJECT_NAME:
        raise RuntimeError("Active project must be " + PROJECT_NAME)
    design_outcome = call(lambda: project.SetActiveDesign(DESIGN_NAME))
    if not design_outcome["ok"]:
        raise RuntimeError("No active AEDT design: " + design_outcome["error"])
    design = design_outcome["_raw"]
    design_name = required(design.GetName, "Get design name")
    if design_name != DESIGN_NAME:
        raise RuntimeError("Active design must be " + DESIGN_NAME)
    progress_rows, done = read_progress(points)
    if prior_status is not None and prior_status.get("completed") != [row["PointName"] for row in progress_rows]:
        raise RuntimeError("Refusing resume: prior status and progress rows disagree")
    payload["completed"] = [row["PointName"] for row in progress_rows]
    new_points = 0
    for point in points:
        if point["PointName"] in done:
            continue
        result = dict((name, "") for name in FIELDS)
        result.update({"PointName": point["PointName"], "PointID": point["point_id"],
            "Role": point["role"], "Region": point["region"], "Id [A]": point["Id [A]"],
            "Iq [A]": point["Iq [A]"], "If [A]": point["If [A]"],
            "Project": project_name, "Design": design_name, "Setup": SETUP_NAME,
            "RotorPosition [deg]": ROTOR_POSITION_DEG, "PolePairs [count]": POLE_PAIRS})
        try:
            mark_stage(payload, point["PointName"], "apply_currents")
            change_currents(design, point)
            mark_stage(payload, point["PointName"], "analyze")
            solve = call(lambda: design.Analyze(SETUP_NAME))
            if not solve["ok"] or solve["value"] not in (0, None):
                raise RuntimeError("Analyze failed: " + (solve.get("error") or str(solve["value"])))
            mark_stage(payload, point["PointName"], "export_flux")
            abc_path = os.path.join(EXPORT_DIR, point["PointName"] + "_flux_abc.csv")
            phi_a, phi_b, phi_c = export_flux(design, abc_path)
            phi_d, phi_q = dq_from_abc(phi_a, phi_b, phi_c, ROTOR_POSITION_DEG * math.pi / 180.0)
            if not all(is_finite(value) for value in (phi_d, phi_q)):
                raise RuntimeError("Non-finite dq flux")
            result["Flux_d [Wb]"], result["Flux_q [Wb]"] = phi_d, phi_q
            result["RawABCFluxPath"] = abc_path
            mark_stage(payload, point["PointName"], "read_torque")
            output_variables = design.GetModule("OutputVariable")
            torque_value = required(lambda: output_variables.GetOutputVariableValue(
                TORQUE_OUTPUT_NAME, "", SOLUTION_NAME, "Magnetostatic", []),
                "Read configured torque output")
            result["Torque [N*m]"] = numeric_output(torque_value, TORQUE_OUTPUT_NAME)
            mark_stage(payload, point["PointName"], "export_solver_evidence")
            mesh, passes, mesh_path, convergence_path = export_solver_evidence(design, point["PointName"])
            result["MeshElements [count]"] = mesh
            result["AdaptivePasses [count]"] = passes
            result["MeshEvidencePath"] = mesh_path
            result["ConvergenceEvidencePath"] = convergence_path
            messages = solver_messages(project_name, design_name, solve["value"])
            if messages["errors"]:
                raise RuntimeError("AEDT reported unresolved solver errors: " + json.dumps(messages["errors"]))
            if any(ADAPTIVE_NONCONVERGENCE_MARKER in str(item).lower()
                    for item in messages["warnings"]):
                raise RuntimeError("AEDT adaptive convergence criteria were not met: "
                    + json.dumps(messages["warnings"]))
            result["SolverStatus"] = "converged"
            result["SolverMessage"] = json.dumps(messages, sort_keys=True)
        except BaseException as exc:
            result["SolverStatus"] = "failed"
            result["SolverMessage"] = json.dumps({"errors": [str(exc)]}, sort_keys=True)
            append_result(result)
            payload["status"] = "failed"
            payload["failure"] = {"point": point, "error": str(exc),
                                  "traceback": traceback.format_exc().splitlines()}
            break
        append_result(result)
        payload["completed"].append(point["PointName"])
        mark_stage(payload, point["PointName"], "point_complete")
        new_points += 1
        if new_points >= MAX_NEW_POINTS_PER_RUN:
            break
    if payload["status"] == "running":
        payload["status"] = "complete" if len(payload["completed"]) == len(points) else "partial_resume_required"
    payload["active_point"] = None
    payload["stage"] = "idle"
except BaseException as exc:
    payload["status"] = "error"
    payload["failure"] = {"error": str(exc), "traceback": traceback.format_exc().splitlines()}
finally:
    try:
        if "design" in globals():
            restore_parametric_currents(design)
        if "project" in globals():
            project.Save()
    except BaseException as restore_exc:
        payload["restore_error"] = str(restore_exc)
        payload["status"] = "error"
    write_status(payload)
    try:
        AddWarningMessage("Task 9 export status: " + STATUS_JSON)
    except BaseException:
        print(STATUS_JSON)
