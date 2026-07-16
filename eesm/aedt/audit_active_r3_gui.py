"""Read-only AEDT audit for the interactively recovered corrected r3 project."""

import json
import os
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r3_gui_recovery_20260716_01"
)
OUT_PATH = os.path.join(OUT_DIR, "active_project_audit.json")
EXPECTED_PROJECT_PREFIX = "eesm_requal_r3_gui_"
EXPECTED_DESIGN = "EESM_2D_Qual"


def normalized(value):
    if value is None or isinstance(value, (bool, float, int, str)):
        return value
    try:
        return [normalized(item) for item in list(value)]
    except TypeError:
        return str(value)


def child_properties(parent, child_name):
    try:
        child = parent.GetChildObject(child_name)
        names = list(child.GetPropNames())
        return {
            "status": "available",
            "properties": {
                name: normalized(child.GetPropValue(name)) for name in names
            },
        }
    except BaseException as exc:
        return {"status": "unavailable", "error": str(exc)}


payload = {"status": "running", "read_only": True}
try:
    project = oDesktop.GetActiveProject()
    if project is None:
        raise RuntimeError("AEDT has no active project")
    project_name = project.GetName()
    if not project_name.startswith(EXPECTED_PROJECT_PREFIX):
        raise RuntimeError("Refusing unexpected active project: " + project_name)

    design_names = [design.GetName() for design in list(project.GetDesigns())]
    if EXPECTED_DESIGN not in design_names:
        raise RuntimeError(
            "Recovered project lacks " + EXPECTED_DESIGN + ": " + str(design_names)
        )
    design = project.SetActiveDesign(EXPECTED_DESIGN)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    analysis = design.GetModule("AnalysisSetup")
    mesh = design.GetModule("MeshSetup")
    output_variables = design.GetModule("OutputVariable")
    excitations_node = design.GetChildObject("Excitations")

    payload.update({
        "status": "audited",
        "project": project_name,
        "project_path": normalized(project.GetPath()),
        "designs": design_names,
        "active_design": EXPECTED_DESIGN,
        "solution_type": normalized(design.GetSolutionType()),
        "geometry_mode": normalized(design.GetGeometryMode()),
        "sheets": normalized(editor.GetObjectsInGroup("Sheets")),
        "solids": normalized(editor.GetObjectsInGroup("Solids")),
        "boundaries": normalized(boundary.GetBoundaries()),
        "excitations": normalized(boundary.GetExcitations()),
        "setups": normalized(analysis.GetSetups()),
        "mesh_operations": normalized(mesh.GetOperationNames("All")),
        "has_torque_fem": bool(
            output_variables.DoesOutputVariableExist("Torque_FEM")
        ),
        "variables": normalized(design.GetVariables()),
        "excitation_properties": {
            name: child_properties(excitations_node, name)
            for name in (
                "PhaseA", "PhaseB", "PhaseC", "Field", "Field_0", "FieldRe_0",
                "EndConnection1",
            )
        },
        "bar_materials": {
            name: normalized(editor.GetPropertyValue(
                "Geometry3DAttributeTab", name, "Material"
            ))
            for name in ("Bar", "Bar_Separate1", "Bar_Separate2")
        },
        "messages": normalized(oDesktop.GetMessages(project_name, EXPECTED_DESIGN, 0)),
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
        json.dump(payload, stream, indent=2)
    try:
        AddWarningMessage("Corrected EESM r3 GUI audit: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
