"""Fail-closed correction of the exact interactively recovered r3 checkpoint.

This script is intended for AEDT's Automation > Run Script command.  It never
opens a project, never analyzes a setup, and saves mutations only to a new
working project after validating the active checkpoint identity.
"""

import hashlib
import json
import os
import sys
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_corrected_eesm_r3 as corrected


CHECKPOINT_NAME = "eesm_requal_r3_gui_checkpoint_20260716_01"
WORKING_NAME = "eesm_requal_r3_gui_working_20260716_01"
PROJECT_DIR = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects",
    "eesm_requal_r3_gui_recovery_20260716_01",
)
CHECKPOINT_PATH = os.path.join(PROJECT_DIR, CHECKPOINT_NAME + ".aedt")
WORKING_PATH = os.path.join(PROJECT_DIR, WORKING_NAME + ".aedt")
OUT_DIR = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r3_gui_recovery_20260716_01"
)
STATUS_PATH = os.path.join(OUT_DIR, "model_configuration_status.json")
REPLAY_STATUS_PATH = os.path.join(OUT_DIR, "model_configuration_replay_refused.json")
DESIGN_NAME = corrected.base.DESIGN_NAME
QUALIFICATION_VARIABLES = {
    "Id", "Iq", "If", "theta_e", "I_phase_a", "I_phase_b", "I_phase_c"
}
EXPECTED_BARS = {"Bar", "Bar_Separate1", "Bar_Separate2"}


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


def exact_project_path(project):
    return os.path.join(str(project.GetPath()), str(project.GetName()) + ".aedt")


def same_path(left, right):
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def excitation_names(boundary):
    raw = list(boundary.GetExcitations())
    return raw[0::2]


def excitation_properties(design, name):
    node = design.GetChildObject("Excitations").GetChildObject(name)
    return {prop: normalized(node.GetPropValue(prop)) for prop in list(node.GetPropNames())}


def bar_materials(editor):
    return {
        name: normalized(editor.GetPropertyValue(
            "Geometry3DAttributeTab", name, "Material"
        ))
        for name in sorted(EXPECTED_BARS)
    }


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
    "checkpoint_path": CHECKPOINT_PATH,
    "working_path": WORKING_PATH,
    "design": DESIGN_NAME,
    "rmxprt_solve_attempted": False,
    "maxwell_solve_attempted": False,
}
try:
    require(os.path.isfile(CHECKPOINT_PATH), "Checkpoint file is missing")
    stale_working_artifacts = [
        WORKING_PATH,
        WORKING_PATH + ".lock",
        os.path.join(PROJECT_DIR, WORKING_NAME + ".aedtresults"),
    ]
    require(not any(os.path.exists(path) for path in stale_working_artifacts),
            "Working project artifacts already exist; refusing replay")
    with open(CHECKPOINT_PATH, "rb") as stream:
        checkpoint_text = stream.read()
    require(b"TorqueRotor" not in checkpoint_text,
            "Checkpoint already contains TorqueRotor; refusing replay")

    project = oDesktop.GetActiveProject()
    require(project is not None, "AEDT has no active project")
    require(project.GetName() == CHECKPOINT_NAME, "Unexpected active project: " + project.GetName())
    require(same_path(exact_project_path(project), CHECKPOINT_PATH), "Active checkpoint path mismatch")

    designs = [item.GetName() for item in list(project.GetDesigns())]
    require(set(designs) == {corrected.base.RMXPRT_DESIGN, DESIGN_NAME},
            "Unexpected project designs: " + str(designs))
    design = project.SetActiveDesign(DESIGN_NAME)
    require(str(design.GetSolutionType()) == "Transient", "Expected transient conversion seed")
    require(str(design.GetGeometryMode()) == "XY", "Expected XY geometry")
    editor = design.SetActiveEditor("3D Modeler")
    sheets = set(editor.GetObjectsInGroup("Sheets"))
    require(EXPECTED_BARS == {name for name in sheets if name.startswith("Bar")},
            "Unexpected temporary bar objects")
    require({"Stator", "Rotor", "Shaft", "Field_0", "FieldRe_0", "Band", "InnerRegion"}.issubset(sheets),
            "Converted design is missing required objects")

    boundary = design.GetModule("BoundarySetup")
    before_excitations = set(excitation_names(boundary))
    require({"PhaseA", "PhaseB", "PhaseC", "Field", "EndConnection1"}.issubset(before_excitations),
            "Converted design is missing required excitations")
    require(list(design.GetModule("AnalysisSetup").GetSetups()) == ["Setup1"],
            "Expected untouched transient Setup1")
    require(not QUALIFICATION_VARIABLES.intersection(set(design.GetVariables())),
            "Qualification variables already exist; refusing replay")
    require(not design.GetModule("OutputVariable").DoesOutputVariableExist("Torque_FEM"),
            "Torque_FEM already exists; refusing replay")
    seed_windings = {
        name: excitation_properties(design, name)
        for name in ("PhaseA", "PhaseB", "PhaseC", "Field")
    }
    require(all(seed_windings[name].get("Number of Parallel Branches") == "4"
                for name in ("PhaseA", "PhaseB", "PhaseC")),
            "A phase conversion seed does not have four branches")
    require(seed_windings["Field"].get("Number of Parallel Branches") == "1",
            "Field conversion seed does not have one branch")
    seed_materials = bar_materials(editor)
    require(all("cast_aluminum_75C" in str(value) for value in seed_materials.values()),
            "Temporary bar seed does not use cast aluminum")
    end_connection = excitation_properties(design, "EndConnection1")
    end_assignment = set(
        item.strip() for item in str(end_connection.get("Assignment", "")).split(",")
        if item.strip()
    )
    require(end_assignment == EXPECTED_BARS,
            "EndConnection1 is not assigned to exactly the temporary bars")
    require(conductor_turns(excitation_properties(design, "Field_0")) == "80",
            "Field_0 does not have 80 turns")
    require(conductor_turns(excitation_properties(design, "FieldRe_0")) == "80",
            "FieldRe_0 does not have 80 turns")
    payload["preflight"] = {
        "project": project.GetName(),
        "designs": designs,
        "solution_type": normalized(design.GetSolutionType()),
        "geometry_mode": normalized(design.GetGeometryMode()),
        "setups": normalized(design.GetModule("AnalysisSetup").GetSetups()),
        "temporary_bars": sorted(EXPECTED_BARS),
        "bar_materials": seed_materials,
        "windings": seed_windings,
        "end_connection": end_connection,
        "field_0": excitation_properties(design, "Field_0"),
        "field_re_0": excitation_properties(design, "FieldRe_0"),
    }

    project.SaveAs(WORKING_PATH, True)
    require(project.GetName() == WORKING_NAME, "SaveAs did not activate the working project")
    require(same_path(exact_project_path(project), WORKING_PATH), "Working project path mismatch after SaveAs")

    corrected.base.oDesktop = oDesktop
    corrected.base.PROJECT_NAME = WORKING_NAME
    contract = corrected.configure_corrected_maxwell(project)

    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    after_excitations = set(excitation_names(boundary))
    phase_properties = {
        name: excitation_properties(design, name)
        for name in ("PhaseA", "PhaseB", "PhaseC", "Field")
    }
    materials = bar_materials(editor)
    validation = normalized(design.ValidateDesign())
    errors = normalized(oDesktop.GetMessages(WORKING_NAME, DESIGN_NAME, 2))

    require(str(design.GetSolutionType()) == "Magnetostatic", "Final solution is not Magnetostatic")
    require(str(design.GetGeometryMode()) == "XY", "Final geometry is not XY")
    require(list(design.GetModule("AnalysisSetup").GetSetups()) == [corrected.base.SETUP_NAME],
            "Final setup list is not the frozen qualification setup")
    require("EndConnection1" not in after_excitations, "Temporary damper end connection remains")
    require(all("steel_1008" in str(value) for value in materials.values()),
            "Temporary bar sheets were not reassigned to rotor steel")
    require(all(phase_properties[name].get("Number of Parallel Branches") == "4"
                for name in ("PhaseA", "PhaseB", "PhaseC")),
            "A stator phase does not have four parallel branches")
    require(phase_properties["Field"].get("Number of Parallel Branches") == "1",
            "Field winding does not have one branch")
    require(QUALIFICATION_VARIABLES.issubset(set(design.GetVariables())),
            "Qualification variables are incomplete")
    require(design.GetModule("OutputVariable").DoesOutputVariableExist("Torque_FEM"),
            "Torque_FEM was not created")
    require(validation in (0, None, True), "Final design validation failed: " + str(validation))
    require(not errors, "Final design recorded AEDT errors: " + str(errors))

    project.Save()
    require(os.path.isfile(WORKING_PATH), "Working project was not saved")
    with open(WORKING_PATH, "rb") as stream:
        project_text = str(stream.read())
    require("ModelDepth='120mm'" in project_text, "Saved project does not record 120 mm depth")
    require(project_text.count("'Conductor number'='80'") >= 2,
            "Saved project does not preserve both 80-turn field coils")
    require("TorqueRotor" in project_text,
            "Saved project does not contain the virtual torque parameter")

    payload.update({
        "status": "configured",
        "working_sha256": sha256(WORKING_PATH),
        "qualification_contract": normalized(contract),
        "postflight": {
            "solution_type": normalized(design.GetSolutionType()),
            "geometry_mode": normalized(design.GetGeometryMode()),
            "setups": normalized(design.GetModule("AnalysisSetup").GetSetups()),
            "bar_materials": materials,
            "winding_properties": phase_properties,
            "validation": validation,
            "errors": errors,
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
    final_status_path = STATUS_PATH
    if os.path.isfile(STATUS_PATH) and payload.get("status") != "configured":
        try:
            with open(STATUS_PATH, "r") as stream:
                prior_status = json.load(stream)
            if prior_status.get("status") == "configured":
                final_status_path = REPLAY_STATUS_PATH
        except BaseException:
            pass
    with open(final_status_path, "w") as stream:
        json.dump(normalized(payload), stream, indent=2)
    try:
        AddWarningMessage("Corrected EESM r3 GUI configuration: " + final_status_path)
    except BaseException:
        print(final_status_path)
