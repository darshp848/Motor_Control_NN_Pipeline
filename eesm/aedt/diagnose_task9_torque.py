"""Fail-closed AEDT preflight for Task 9 torque requalification r2.

The original model is copied before this script is invoked. Physics solves are
prohibited until its frozen geometry/winding contract passes; this prevents a
sign, scale, or tolerance change from masking a noncompliant machine.
"""

import json
import os
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
REQUAL_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r2")
PROJECT_NAME = "eesm_requal_r2"
PROJECT_PATH = os.path.join(REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME, PROJECT_NAME + ".aedt")
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
SOLUTION_NAME = "Setup_Qual : LastAdaptive"
MODEL_AUDIT = os.path.join(REQUAL_ROOT, "model_contract_audit.json")
STATUS_PATH = os.path.join(REQUAL_ROOT, "diagnostic_status.json")
TORQUE_CLOSURE_TOLERANCE_NM = 1.1
TASK10_AUTHORIZED = False
COENERGY_DELTA_MECH_DEG = 1.0
MAX_NEW_POINTS_PER_RUN = 1
PRESERVATION_POLICY = "source_project_copy_only_no_overwrite"
FIELDS = [
    "PointID", "TorqueVirtualFEM [N*m]", "TorqueController [N*m]",
    "TorquePhaseFlux [N*m]", "TorqueCoenergy [N*m]",
    "TorqueCoenergyCoarse [N*m]", "CoenergyMinus [J]", "CoenergyPlus [J]",
]
CHANNEL_KEYS = {
    "virtual_torque_nm": "TorqueVirtualFEM [N*m]",
    "phase_flux_torque_nm": "TorquePhaseFlux [N*m]",
    "coenergy_derivative_torque_nm": "TorqueCoenergy [N*m]",
}


def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def write_status(payload):
    with open(STATUS_PATH, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def integrated_coenergy(design, field_path):
    """Evaluate Maxwell's case-sensitive coEnergy quantity on a solved copy."""
    fields = design.GetModule("FieldsReporter")
    fields.CalcStack("clear")
    fields.EnterQty("coEnergy")
    fields.EnterVol("AllObjects")
    fields.CalcOp("Integrate")
    fields.CalculatorWrite(field_path, ["Solution:=", SOLUTION_NAME], [])
    fields.CalcStack("clear")


payload = {
    "status": "running",
    "stage": "model_contract_preflight",
    "project": PROJECT_NAME,
    "design": DESIGN_NAME,
    "setup": SETUP_NAME,
    "preservation_policy": PRESERVATION_POLICY,
    "task_10_authorized": TASK10_AUTHORIZED,
    "failure": None,
}
try:
    if not os.path.isfile(MODEL_AUDIT):
        raise RuntimeError("Missing frozen model contract audit")
    with open(MODEL_AUDIT, "r") as stream:
        audit = json.load(stream)
    payload["model_contract_audit"] = audit
    if audit.get("status") != "pass":
        payload["status"] = "blocked_model_contract"
        payload["stage"] = "idle"
        payload["failure"] = {
            "reason": "Refusing to modify the frozen Task 9 baseline or solve its noncompliant copy",
            "required_action": "build_new_compliant_r3_project",
        }
    else:
        raise RuntimeError("r2 is an audit of the failed source model; corrected solves require r3")
except BaseException as exc:
    payload["status"] = "error"
    payload["failure"] = {"error": str(exc), "traceback": traceback.format_exc().splitlines()}
finally:
    write_status(payload)
    try:
        AddWarningMessage("Task 9 requalification status: " + STATUS_PATH)
    except BaseException:
        print(STATUS_PATH)
