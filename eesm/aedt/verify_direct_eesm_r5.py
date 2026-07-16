"""Independent read-only verification of the saved r5 quarter-sector model."""

import hashlib
import json
import os
import re
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_direct_r5_01"
DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r5")
BUILD_STATUS_PATH = os.path.join(OUT_DIR, "model_build_status_attempt1.json")
OUT_PATH = os.path.join(OUT_DIR, "model_verification_attempt2.json")
SECTOR_SLOT_MAP = (
    (22, "PhaseB", "Negative", 4),
    (23, "PhaseB", "Negative", 5),
    (24, "PhaseA", "Positive", 5),
    (1, "PhaseA", "Positive", 4),
    (2, "PhaseC", "Negative", 4),
    (3, "PhaseC", "Negative", 5),
)
STATOR_OBJECTS = [
    "StatorCoil_S%02d_%s" % (slot, layer)
    for slot, _phase, _polarity, _turns in SECTOR_SLOT_MAP
    for layer in ("T", "B")
]
FIELD_OBJECTS = ["Field_P01_NegT", "Field_P01_PosT"]


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


def saved_polarity(project_text, terminal):
    pattern = (r"\$begin\s+'" + re.escape(terminal)
               + r"'.*?PolarityType='(Positive|Negative)'.*?\$end\s+'"
               + re.escape(terminal) + r"'")
    match = re.search(pattern, project_text, re.DOTALL)
    return match.group(1) if match else ""


def expected_terminal_map():
    result = {}
    for slot, phase, expected_polarity, turns in SECTOR_SLOT_MAP:
        for layer in ("T", "B"):
            result["%s_S%02d_%s" % (phase, slot, layer)] = {
                "object": "StatorCoil_S%02d_%s" % (slot, layer),
                "turns": turns, "polarity": expected_polarity,
                "winding": phase,
            }
    result.update({
        "Field_P01_NegT_Term": {
            "object": "Field_P01_NegT", "turns": 80,
            "polarity": "Negative", "winding": "Field",
        },
        "Field_P01_PosT_Term": {
            "object": "Field_P01_PosT", "turns": 80,
            "polarity": "Positive", "winding": "Field",
        },
    })
    return result


payload = {
    "status": "running", "read_only_verification": True,
    "project": PROJECT_NAME, "project_path": PROJECT_PATH,
    "design": DESIGN_NAME, "maxwell_solve_attempted": False,
    "task_10_authorized": False,
}
try:
    require(os.path.isfile(BUILD_STATUS_PATH), "Direct r5 build status is missing")
    with open(BUILD_STATUS_PATH, "r") as stream:
        build_status = json.load(stream)
    require(build_status.get("status") == "built", "Direct r5 build did not succeed")
    require(build_status.get("maxwell_solve_attempted") is False,
            "Build status claims a solve")
    require(build_status.get("Task10Authorized") is False,
            "Build status improperly authorizes Task 10")
    require(os.path.isfile(PROJECT_PATH), "Direct r5 project is missing")
    project_hash = sha256(PROJECT_PATH)
    require(project_hash == build_status.get("project_sha256"),
            "Direct r5 project hash does not match build status")
    with open(PROJECT_PATH, "rb") as stream:
        project_text = str(stream.read())

    project = oDesktop.GetActiveProject()
    require(project is not None and project.GetName() == PROJECT_NAME,
            "Unexpected active project")
    active_path = os.path.abspath(os.path.join(
        str(project.GetPath()), project.GetName() + ".aedt"
    ))
    require(os.path.normcase(active_path) == os.path.normcase(os.path.abspath(PROJECT_PATH)),
            "Active project path drifted")
    design_names = [item.GetName() for item in list(project.GetDesigns())]
    require(design_names == [DESIGN_NAME], "Unexpected direct r5 designs: " + str(design_names))
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    output = design.GetModule("OutputVariable")
    sheets = set(editor.GetObjectsInGroup("Sheets"))
    excitations = list(boundary.GetExcitations())[0::2]
    boundaries = list(boundary.GetBoundaries())

    require(str(design.GetSolutionType()) == "Magnetostatic", "Solution is not Magnetostatic")
    require(str(design.GetGeometryMode()) == "XY", "Geometry is not XY")
    require(list(analysis.GetSetups()) == ["Setup_Qual"], "Unexpected setups")
    require(len(sheets) == 19, "Expected exactly 19 sheets, got " + str(len(sheets)))
    require(set(STATOR_OBJECTS).issubset(sheets), "Stator sector inventory is incomplete")
    require(set(FIELD_OBJECTS).issubset(sheets), "Field sector inventory is incomplete")
    require({"Stator", "RotorYoke", "Shaft", "PoleAssembly_01", "Region"}.issubset(sheets),
            "Core/background inventory is incomplete")
    require(not [name for name in sheets if name.startswith(("Bar", "Damper", "Mag"))
                 or name in ("Band", "InnerRegion")], "Prohibited objects remain")

    winding_names = ("PhaseA", "PhaseB", "PhaseC", "Field")
    winding_props = dict((name, properties(design, name)) for name in winding_names)
    require(all(str(winding_props[name].get("Number of Parallel Branches")) == "1"
                for name in winding_names), "A winding branch count drifted")
    terminal_names = [name for name in excitations if name not in winding_names]
    require(len(terminal_names) == 14, "Expected 14 sector terminals")
    expected_map = expected_terminal_map()
    require(set(terminal_names) == set(expected_map), "Terminal names drifted")
    observed_terminal_map = {}
    for name in terminal_names:
        props = properties(design, name)
        observed_polarity = saved_polarity(project_text, name)
        observed_terminal_map[name] = {
            "turns": conductor_turns(props),
            "polarity": observed_polarity,
            "properties": props,
        }
        require(conductor_turns(props) == expected_map[name]["turns"],
                name + " turn count drifted")
        require(observed_polarity == expected_map[name]["polarity"],
                name + " saved polarity drifted: " + observed_polarity)

    conductor_turns_by_phase = {}
    for phase in ("PhaseA", "PhaseB", "PhaseC"):
        phase_terminals = [name for name in terminal_names if name.startswith(phase + "_")]
        require(len(phase_terminals) == 4, phase + " terminal count drifted")
        conductor_turns_by_phase[phase] = sum(
            conductor_turns(properties(design, name)) for name in phase_terminals
        )
    require(conductor_turns_by_phase == {"PhaseA": 18, "PhaseB": 18, "PhaseC": 18},
            "Sector conductor turns drifted: " + str(conductor_turns_by_phase))
    require(dict((phase, turns // 2 * 4)
                 for phase, turns in conductor_turns_by_phase.items()) ==
            {"PhaseA": 36, "PhaseB": 36, "PhaseC": 36},
            "Replicated full-machine phase turns drifted")

    require(boundaries == [
        "Outer_A0", "Vector Potential",
        "Quarter_Independent", "Independent",
        "Quarter_Dependent", "Dependent",
    ], "Boundary inventory/order drifted: " + str(boundaries))
    require(output.DoesOutputVariableExist("Torque_FEM_Sector"),
            "Raw sector torque output is missing")
    require(output.DoesOutputVariableExist("Torque_FEM"),
            "Scaled full-machine torque output is missing")

    materials = dict((name, normalize(editor.GetPropertyValue(
        "Geometry3DAttributeTab", name, "Material"
    ))) for name in [
        "Stator", "RotorYoke", "Shaft", "PoleAssembly_01", "Region"
    ] + STATOR_OBJECTS + FIELD_OBJECTS)
    require("steel_1008" in str(materials["Stator"]) and
            "steel_1008" in str(materials["RotorYoke"]) and
            "steel_1008" in str(materials["PoleAssembly_01"]),
            "Core material drifted")
    require("EESM_Nonmagnetic_Stainless_R5" in str(materials["Shaft"]),
            "Shaft material drifted")
    require("vacuum" in str(materials["Region"]), "Region material drifted")
    require(all("copper" in str(materials[name])
                for name in STATOR_OBJECTS + FIELD_OBJECTS),
            "A conductor is not copper")

    validation = normalize(design.ValidateDesign())
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    require(validation in (0, None, True), "ValidateDesign failed: " + str(validation))
    require(not errors, "AEDT recorded design errors: " + str(errors))
    require("ModelDepth='120mm'" in project_text, "Saved depth is not 120 mm")
    require("SameAsMaster=false" in project_text,
            "Dependent boundary is not explicitly anti-periodic")
    require("Quarter_Independent" in project_text and "Quarter_Dependent" in project_text,
            "Saved radial boundary pair is incomplete")
    require("Torque_FEM_Sector" in project_text and "4*TorqueRotor.Torque" in project_text,
            "Saved torque scaling outputs are incomplete")
    require(build_status.get("aedt_magnetostatic_symmetry_multiplier_used") is False,
            "Build status improperly claims an AEDT symmetry multiplier")
    scaling = build_status.get("scaling_contract", {})
    require(scaling.get("qualification_runner_scaling_required") is True and
            scaling.get("independent_solve_validation_required") is True,
            "Scaling caveat was not preserved")
    require(build_status.get("offset_motion_contract", {}).get("keep_fixed_axisymmetric") ==
            ["RotorYoke", "Shaft"], "Offset motion contract drifted")
    require(build_status.get("offset_motion_contract", {}).get("rotate_without_reclip") ==
            ["PoleAssembly_01", "Field_P01_NegT", "Field_P01_PosT"],
            "Offset moving-object contract drifted")

    payload.update({
        "status": "verified", "project_sha256": project_hash,
        "designs": design_names, "sheet_count": len(sheets),
        "excitation_count": len(excitations), "terminal_count": len(terminal_names),
        "boundaries": boundaries,
        "sector_conductor_turns": conductor_turns_by_phase,
        "replicated_full_phase_turns": {"PhaseA": 36, "PhaseB": 36, "PhaseC": 36},
        "terminal_map": observed_terminal_map,
        "winding_properties": winding_props,
        "scaling_contract": scaling,
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
        AddWarningMessage("Direct EESM r5 verification: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
