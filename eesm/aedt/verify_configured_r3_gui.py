"""Independent read-only verification of the saved corrected r3 working project."""

import hashlib
import json
import os
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_r3_gui_working_20260716_01"
DESIGN_NAME = "EESM_2D_Qual"
PROJECT_DIR = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects",
    "eesm_requal_r3_gui_recovery_20260716_01",
)
PROJECT_PATH = os.path.join(PROJECT_DIR, PROJECT_NAME + ".aedt")
OUT_DIR = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r3_gui_recovery_20260716_01"
)
OUT_PATH = os.path.join(OUT_DIR, "model_configuration_verification.json")
PRIMARY_STATUS_PATH = os.path.join(OUT_DIR, "model_configuration_status.json")
EXPECTED_BARS = {"Bar", "Bar_Separate1", "Bar_Separate2"}
REQUIRED_VARIABLES = {
    "Id", "Iq", "If", "theta_e", "I_phase_a", "I_phase_b", "I_phase_c"
}


def normalized(value):
    if isinstance(value, bool):
        return bool(value)
    if value is None or isinstance(value, (float, int, str)):
        return value
    if isinstance(value, dict):
        return {str(key): normalized(item) for key, item in value.items()}
    try:
        return [normalized(item) for item in list(value)]
    except TypeError:
        return str(value)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def same_path(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def excitation_names(boundary):
    return list(boundary.GetExcitations())[0::2]


def excitation_properties(design, name):
    node = design.GetChildObject("Excitations").GetChildObject(name)
    return {prop: normalized(node.GetPropValue(prop)) for prop in list(node.GetPropNames())}


def conductor_turns(properties):
    return properties.get("Number of Conductors", properties.get("Conductor number"))


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest().upper()


payload = {
    "status": "running",
    "read_only_verification": True,
    "project_path": PROJECT_PATH,
    "design": DESIGN_NAME,
    "rmxprt_solve_attempted": False,
    "maxwell_solve_attempted": False,
}
try:
    require(os.path.isfile(PROJECT_PATH), "Configured working project is missing")
    project = oDesktop.GetActiveProject()
    require(project is not None, "AEDT has no active project")
    require(project.GetName() == PROJECT_NAME, "Unexpected active project: " + project.GetName())
    active_path = os.path.join(str(project.GetPath()), project.GetName() + ".aedt")
    require(same_path(active_path, PROJECT_PATH), "Active project path mismatch")

    design_names = [item.GetName() for item in list(project.GetDesigns())]
    require(set(design_names) == {"RMxprtDesign1", DESIGN_NAME},
            "Unexpected project designs: " + str(design_names))
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    output_variables = design.GetModule("OutputVariable")

    sheets = set(editor.GetObjectsInGroup("Sheets"))
    bars = {name for name in sheets if name.startswith("Bar")}
    excitations = set(excitation_names(boundary))
    windings = {
        name: excitation_properties(design, name)
        for name in ("PhaseA", "PhaseB", "PhaseC", "Field")
    }
    field_coils = {
        name: excitation_properties(design, name)
        for name in ("Field_0", "FieldRe_0")
    }
    materials = {
        name: normalized(editor.GetPropertyValue(
            "Geometry3DAttributeTab", name, "Material"
        ))
        for name in sorted(EXPECTED_BARS)
    }
    validation = normalized(design.ValidateDesign())
    errors = normalized(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))

    require(str(design.GetSolutionType()) == "Magnetostatic", "Solution is not Magnetostatic")
    require(str(design.GetGeometryMode()) == "XY", "Geometry is not XY")
    require(list(analysis.GetSetups()) == ["Setup_Qual"], "Unexpected qualification setups")
    require(bars == EXPECTED_BARS, "Unexpected bar-fill objects")
    require("Band" not in sheets and "InnerRegion" not in sheets,
            "Transient conversion-only sheets remain")
    require("EndConnection1" not in excitations, "Temporary damper end connection remains")
    require(all("steel_1008" in str(value) for value in materials.values()),
            "Bar-fill sheets are not rotor steel")
    require(all(windings[name].get("Number of Parallel Branches") == "4"
                for name in ("PhaseA", "PhaseB", "PhaseC")),
            "A phase does not have four parallel branches")
    require(windings["Field"].get("Number of Parallel Branches") == "1",
            "Field does not have one branch")
    require(all(conductor_turns(props) == "80" for props in field_coils.values()),
            "A field coil does not have 80 turns")
    require(REQUIRED_VARIABLES.issubset(set(design.GetVariables())),
            "Qualification variables are incomplete")
    require(output_variables.DoesOutputVariableExist("Torque_FEM"),
            "Torque_FEM is missing")
    require(validation in (0, None, True), "ValidateDesign failed: " + str(validation))
    require(not errors, "AEDT recorded design errors: " + str(errors))

    with open(PROJECT_PATH, "rb") as stream:
        project_text = str(stream.read())
    require("ModelDepth='120mm'" in project_text, "Saved depth is not 120 mm")
    require(project_text.count("'Conductor number'='80'") >= 2,
            "Saved project lacks two 80-turn field coils")
    require("TorqueRotor" in project_text and "Torque_FEM" in project_text,
            "Saved torque parameter/output is incomplete")
    require("EndConnection1" not in project_text,
            "Saved project still contains EndConnection1")

    payload.update({
        "status": "configured",
        "project_sha256": sha256(PROJECT_PATH),
        "designs": design_names,
        "solution_type": normalized(design.GetSolutionType()),
        "geometry_mode": normalized(design.GetGeometryMode()),
        "setups": normalized(analysis.GetSetups()),
        "bar_fill_materials": materials,
        "winding_properties": windings,
        "field_coil_properties": field_coils,
        "validation": validation,
        "errors": errors,
        "frozen_contract": {
            "model_depth": "120mm",
            "stator_series_turns_per_phase": 36,
            "stator_parallel_branches": 4,
            "field_turns_per_pole": 80,
            "damper_cage": False,
            "temporary_bar_sheets_reassigned_to_rotor_steel": sorted(EXPECTED_BARS),
            "torque_parameter": "TorqueRotor",
            "torque_output_variable": "Torque_FEM",
        },
    })
except BaseException as exc:
    payload.update({
        "status": "error",
        "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    })
finally:
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    with open(OUT_PATH, "w") as stream:
        json.dump(normalized(payload), stream, indent=2)
    if payload.get("status") == "configured":
        with open(PRIMARY_STATUS_PATH, "w") as stream:
            json.dump(normalized(payload), stream, indent=2)
    try:
        AddWarningMessage("Corrected EESM r3 verification: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
