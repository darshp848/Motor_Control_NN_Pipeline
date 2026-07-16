"""Independent read-only verification of the saved direct-Maxwell r4 model."""

import hashlib
import json
import math
import os
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_direct_r4_04"
DESIGN_NAME = "EESM_2D_Direct_R4"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
PROJECT_SHA256 = "4ff65ae2c158679c8caa6ece2d38a86b931cf6d0e945ea745aaa6714e03236a7"
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r4")
OUT_PATH = os.path.join(OUT_DIR, "model_verification_attempt4.json")
FIELD_OBJECTS = [
    "Field_P%02d_%s" % (pole, side)
    for pole in range(1, 5) for side in ("NegT", "PosT")
]
STATOR_OBJECTS = [
    "StatorCoil_S%02d_%s" % (slot, layer)
    for slot in range(1, 25) for layer in ("T", "B")
]


def normalize(value):
    if str(value) == "True":
        return True
    if str(value) == "False":
        return False
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def properties(design, name):
    node = design.GetChildObject("Excitations").GetChildObject(name)
    return dict((prop, normalize(node.GetPropValue(prop)))
                for prop in list(node.GetPropNames()))


def conductor_turns(props):
    return int(str(props.get("Number of Conductors", props.get("Conductor number"))))


payload = {
    "status": "running", "read_only_verification": True,
    "project": PROJECT_NAME, "project_path": PROJECT_PATH, "design": DESIGN_NAME,
    "maxwell_solve_attempted": False, "task_10_authorized": False,
}
try:
    require(os.path.isfile(PROJECT_PATH), "Direct r4 project is missing")
    require(sha256(PROJECT_PATH) == PROJECT_SHA256, "Direct r4 project hash drifted")
    project = oDesktop.GetActiveProject()
    require(project is not None and project.GetName() == PROJECT_NAME,
            "Unexpected active project")
    active_path = os.path.abspath(os.path.join(
        str(project.GetPath()), project.GetName() + ".aedt"
    ))
    require(os.path.normcase(active_path) == os.path.normcase(os.path.abspath(PROJECT_PATH)),
            "Active project path drifted")
    design_names = [item.GetName() for item in list(project.GetDesigns())]
    require(design_names == [DESIGN_NAME], "Unexpected direct r4 designs: " + str(design_names))
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    output = design.GetModule("OutputVariable")
    sheets = set(editor.GetObjectsInGroup("Sheets"))
    excitations = list(boundary.GetExcitations())[0::2]
    excitation_set = set(excitations)

    require(str(design.GetSolutionType()) == "Magnetostatic", "Solution is not Magnetostatic")
    require(str(design.GetGeometryMode()) == "XY", "Geometry is not XY")
    require(list(analysis.GetSetups()) == ["Setup_Qual"], "Unexpected setups")
    require(len(sheets) == 60, "Expected exactly 60 sheets, got " + str(len(sheets)))
    require(set(STATOR_OBJECTS).issubset(sheets), "Stator conductor inventory is incomplete")
    require(set(FIELD_OBJECTS).issubset(sheets), "Field conductor inventory is incomplete")
    require({"Stator", "Rotor", "Shaft", "Region"}.issubset(sheets),
            "Core/background inventory is incomplete")
    require(not [name for name in sheets if name.startswith(("Bar", "Damper", "Mag"))
                 or name in ("Band", "InnerRegion")], "Prohibited objects remain")

    winding_props = dict((name, properties(design, name))
                         for name in ("PhaseA", "PhaseB", "PhaseC", "Field"))
    require(all(str(winding_props[name].get("Number of Parallel Branches")) == "1"
                for name in winding_props), "A winding branch count drifted")
    terminal_names = [name for name in excitations if name not in winding_props]
    require(len(terminal_names) == 56, "Expected 56 terminals")
    phase_turns = {}
    for phase in ("PhaseA", "PhaseB", "PhaseC"):
        terminals = [name for name in terminal_names if name.startswith(phase + "_")]
        require(len(terminals) == 16, phase + " terminal count drifted")
        phase_turns[phase] = sum(conductor_turns(properties(design, name))
                                 for name in terminals) // 2
    require(phase_turns == {"PhaseA": 36, "PhaseB": 36, "PhaseC": 36},
            "Phase turns drifted: " + str(phase_turns))
    field_terminals = [name for name in terminal_names if name.startswith("Field_")]
    require(len(field_terminals) == 8 and all(
        conductor_turns(properties(design, name)) == 80 for name in field_terminals
    ), "Field terminal turns drifted")

    materials = dict((name, normalize(editor.GetPropertyValue(
        "Geometry3DAttributeTab", name, "Material"
    ))) for name in ["Stator", "Rotor", "Shaft", "Region"] + STATOR_OBJECTS + FIELD_OBJECTS)
    require("steel_1008" in str(materials["Stator"]) and
            "steel_1008" in str(materials["Rotor"]), "Core material drifted")
    require("EESM_Nonmagnetic_Stainless_R4" in str(materials["Shaft"]),
            "Shaft material drifted")
    require("vacuum" in str(materials["Region"]), "Region material drifted")
    require(all("copper" in str(materials[name])
                for name in STATOR_OBJECTS + FIELD_OBJECTS), "A conductor is not copper")

    field_bounds = dict((name, [float(item) for item in editor.GetObjectBoundingBox(name)])
                        for name in FIELD_OBJECTS)
    require(all(max(math.hypot(box[x], box[y]) for x in (0, 3) for y in (1, 4)) <= 66.5
                for box in field_bounds.values()), "A field sheet bounding box is implausible")
    validation = normalize(design.ValidateDesign())
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    require(validation in (0, None, True), "ValidateDesign failed: " + str(validation))
    require(not errors, "AEDT recorded design errors: " + str(errors))
    require(output.DoesOutputVariableExist("Torque_FEM"), "Torque_FEM is missing")

    with open(PROJECT_PATH, "rb") as stream:
        project_text = str(stream.read())
    require("ModelDepth='120mm'" in project_text, "Saved depth is not 120 mm")
    require("TorqueRotor" in project_text and "Torque_FEM" in project_text,
            "Saved torque parameter/output is incomplete")
    require("Outer_A0" in project_text, "Saved exterior boundary is missing")
    payload.update({
        "status": "verified", "project_sha256": PROJECT_SHA256,
        "designs": design_names, "sheet_count": len(sheets),
        "excitation_count": len(excitations), "terminal_count": len(terminal_names),
        "phase_turns": phase_turns, "field_turns_per_pole": 80,
        "winding_properties": winding_props, "field_bounds": field_bounds,
        "validation": validation, "errors": errors,
    })
except BaseException as exc:
    payload.update({
        "status": "error", "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    })
finally:
    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)
    with open(OUT_PATH, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)
    try:
        AddWarningMessage("Direct EESM r4 verification: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
