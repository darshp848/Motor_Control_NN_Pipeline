"""User-run AEDT GUI pilot exporter (IronPython 2.7 compatible).

This file is never run by the offline test suite. Run it manually through
Automation -> Run Script only after its project constants are reviewed.
"""

import csv
import json
import math
import os
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
POINTS = os.path.join(ROOT, "eesm_qualification_points.csv")
PROGRESS = os.path.join(ROOT, "eesm_qualification_progress.csv")
STATUS_JSON = os.path.join(ROOT, "eesm_qualification_export_status.json")
EXPORT_DIR = os.path.join(ROOT, "point_exports")
SETUP_NAME = "Setup1"
SOLUTION_NAME = "Setup1 : LastAdaptive"
POLE_PAIRS = 0  # Fail closed until supported by reviewed project evidence.
ROTOR_POSITION_DEG = 0.0
MESH_ELEMENTS = 0  # Reviewed positive integer from the qualified mesh.
ADAPTIVE_PASSES = 0  # Reviewed positive integer from the qualified setup.
TORQUE_OUTPUT_NAME = ""  # Reviewed AEDT output-variable name, including convention.
SMOKE_APPROVED = False  # Set True only after reviewing smoke status/CSV evidence.
SMOKE_POINTS = ("field_only", "q_current", "negative_d", "combined_rated")
REPORT_NAME = "EESM_Qualification_Flux_ABC"
EXPRESSIONS = ["FluxLinkage(PhaseA)", "FluxLinkage(PhaseB)", "FluxLinkage(PhaseC)"]
FIELDS = [
    "PointName", "Id [A]", "Iq [A]", "If [A]", "Flux_d [Wb]",
    "Flux_q [Wb]", "Torque [N*m]", "Project", "Design", "Setup",
    "RotorPosition [deg]", "MeshElements [count]", "AdaptivePasses [count]",
    "SolverStatus", "SolverMessage", "PolePairs [count]",
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


def write_status(payload):
    with open(STATUS_JSON, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def is_finite(value):
    try:
        return not (math.isnan(value) or math.isinf(value))
    except BaseException:
        return False


def dq_from_abc(phi_a, phi_b, phi_c, theta_re):
    phi_d = (2.0 / 3.0) * (phi_a * math.cos(theta_re)
        + phi_b * math.cos(theta_re - 2 * math.pi / 3)
        + phi_c * math.cos(theta_re + 2 * math.pi / 3))
    phi_q = (2.0 / 3.0) * (-phi_a * math.sin(theta_re)
        - phi_b * math.sin(theta_re - 2 * math.pi / 3)
        - phi_c * math.sin(theta_re + 2 * math.pi / 3))
    return phi_d, phi_q


def read_flux_csv(path):
    with open(path, "r") as stream:
        reader = csv.reader(stream)
        header = next(reader)
        rows = list(reader)
    if len(header) < 4 or not rows:
        raise RuntimeError("Incomplete ABC flux CSV: " + path)
    last = rows[-1]
    return float(last[1]), float(last[2]), float(last[3])


def numeric_output(value, name):
    try:
        number = float(str(value).split()[0])
    except BaseException:
        raise RuntimeError(name + " was not a plain numeric value in declared SI units")
    if not is_finite(number):
        raise RuntimeError(name + " was non-finite")
    return number


def export_flux(design, path):
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
    return read_flux_csv(path)


def change_currents(design, row):
    changed = []
    for name in ("Id", "Iq", "If"):
        changed.append(["NAME:" + name, "Value:=", row[name + " [A]"] + "A"])
    required(lambda: design.ChangeProperty(["NAME:AllTabs", ["NAME:LocalVariableTab",
        ["NAME:PropServers", "LocalVariables"], ["NAME:ChangedProps"] + changed]]),
        "Change Id/Iq/If local variables")


def append_result(result):
    exists = os.path.exists(PROGRESS) and os.path.getsize(PROGRESS) > 0
    with open(PROGRESS, "ab") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS, lineterminator="\r\n")
        if not exists:
            writer.writeheader()
        writer.writerow(result)


def read_progress():
    if not os.path.exists(PROGRESS):
        return [], set()
    with open(PROGRESS, "r") as stream:
        rows = list(csv.DictReader(stream))
    failed = [row for row in rows if row.get("SolverStatus", "").lower() == "failed"]
    if failed:
        raise RuntimeError("Refusing resume: progress contains failed row " + failed[0].get("PointName", ""))
    return rows, set(row["PointName"] for row in rows)


def failure_diagnostics(project_name, design_name, design, point, error):
    messages = dict((str(level), call(lambda level=level:
        oDesktop.GetMessages(project_name, design_name, level)))
        for level in range(4))
    global_errors = call(lambda: oDesktop.GetMessages("", "", 2))
    validation = call(design.ValidateDesign)
    return {"point": point, "error": str(error), "validation": validation,
        "messages": messages, "global_errors": global_errors,
        "current_change_method": "LocalVariableTab Id/Iq/If"}


payload = {"status": "running", "completed": [], "failure": None}
try:
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)
    project = required(oDesktop.GetActiveProject, "Get active project")
    design_outcome = call(project.GetActiveDesign)
    if not design_outcome["ok"]:
        raise RuntimeError(
            "No active AEDT design. In Project Manager, double-click the target "
            "Maxwell design before running this script. Original error: "
            + design_outcome["error"]
        )
    design = design_outcome["_raw"]
    project_name = required(project.GetName, "Get project name")
    design_name = required(design.GetName, "Get design name")
    progress_rows, done = read_progress()
    if POLE_PAIRS <= 0 or int(POLE_PAIRS) != POLE_PAIRS:
        raise RuntimeError("POLE_PAIRS must be a reviewed positive integer")
    if MESH_ELEMENTS <= 0 or int(MESH_ELEMENTS) != MESH_ELEMENTS:
        raise RuntimeError("MESH_ELEMENTS must be a reviewed positive integer")
    if ADAPTIVE_PASSES <= 0 or int(ADAPTIVE_PASSES) != ADAPTIVE_PASSES:
        raise RuntimeError("ADAPTIVE_PASSES must be a reviewed positive integer")
    if not TORQUE_OUTPUT_NAME:
        raise RuntimeError("TORQUE_OUTPUT_NAME must be reviewed and configured")
    with open(POINTS, "r") as stream:
        points = list(csv.DictReader(stream))
    if not SMOKE_APPROVED:
        points = [point for point in points if point["PointName"] in SMOKE_POINTS]
        payload["mode"] = "smoke_only"
        payload["smoke_points"] = list(SMOKE_POINTS)
    else:
        payload["mode"] = "approved_full_pilot"
    for point in points:
        if point["PointName"] in done:
            continue
        result = dict((name, "") for name in FIELDS)
        result.update({"PointName": point["PointName"], "Id [A]": point["Id [A]"],
            "Iq [A]": point["Iq [A]"], "If [A]": point["If [A]"],
            "Project": project_name, "Design": design_name, "Setup": SETUP_NAME,
            "RotorPosition [deg]": ROTOR_POSITION_DEG, "PolePairs [count]": POLE_PAIRS})
        try:
            change_currents(design, point)
            solve = call(lambda: design.Analyze(SETUP_NAME))
            if not solve["ok"]:
                payload["failure"] = failure_diagnostics(
                    project_name, design_name, design, point, solve["error"])
                raise RuntimeError("Analyze failed: " + solve["error"])
            solve_result = solve["value"]
            if solve_result not in (0, None):
                payload["failure"] = failure_diagnostics(
                    project_name, design_name, design, point,
                    "Analyze returned " + str(solve_result))
                raise RuntimeError("Analyze returned " + str(solve_result))
            abc_path = os.path.join(EXPORT_DIR, point["PointName"] + "_flux_abc.csv")
            phi_a, phi_b, phi_c = export_flux(design, abc_path)
            phi_d, phi_q = dq_from_abc(phi_a, phi_b, phi_c,
                ROTOR_POSITION_DEG * math.pi / 180.0)
            if not all(is_finite(value) for value in (phi_d, phi_q)):
                raise RuntimeError("Non-finite dq flux")
            result["Flux_d [Wb]"], result["Flux_q [Wb]"] = phi_d, phi_q
            torque_value = required(lambda: design.GetOutputVariableValue(
                TORQUE_OUTPUT_NAME, "", SOLUTION_NAME, "Context:="),
                "Read configured torque output")
            result["Torque [N*m]"] = numeric_output(torque_value, TORQUE_OUTPUT_NAME)
            result["MeshElements [count]"] = MESH_ELEMENTS
            result["AdaptivePasses [count]"] = ADAPTIVE_PASSES
            result["SolverStatus"] = "converged"
            result["SolverMessage"] = "Normal solve; ABC flux report exported"
        except BaseException as exc:
            result["SolverStatus"] = "failed"
            result["SolverMessage"] = str(exc)
            append_result(result)
            payload["status"] = "failed"
            if payload["failure"] is None:
                payload["failure"] = {"point": point, "error": str(exc)}
            break
        append_result(result)
        payload["completed"].append(point["PointName"])
    if payload["status"] == "running":
        payload["status"] = "complete" if SMOKE_APPROVED else "smoke_complete_review_required"
except BaseException as exc:
    payload["status"] = "error"
    payload["failure"] = {"error": str(exc), "traceback": traceback.format_exc().splitlines()}
finally:
    write_status(payload)
    try:
        AddWarningMessage("EESM export status: " + STATUS_JSON)
    except BaseException:
        print(STATUS_JSON)
