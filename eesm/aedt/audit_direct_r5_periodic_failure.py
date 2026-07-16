"""Read-only radial-cut audit for the preserved failed r5 anchor session."""

import json
import os
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_r5_anchor_field_only"
DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"
OUT_PATH = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r5_attempt1_20260716",
    "failed_anchor_01_periodic_edge_audit.json",
)


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


def vertices(editor, edge_id):
    result = []
    for vertex_id in list(editor.GetVertexIDsFromEdge(edge_id)):
        result.append([float(value) for value in editor.GetVertexPosition(int(vertex_id))])
    return result


def radial_edges(editor, object_name):
    found = {"x_axis": [], "y_axis": []}
    for edge_id in [int(item) for item in list(editor.GetEdgeIDsFromObject(object_name))]:
        points = vertices(editor, edge_id)
        if points and all(abs(point[1]) <= 1e-8 for point in points):
            found["x_axis"].append({"edge_id": edge_id, "vertices": points})
        if points and all(abs(point[0]) <= 1e-8 for point in points):
            found["y_axis"].append({"edge_id": edge_id, "vertices": points})
    return found


payload = {
    "status": "running", "read_only": True, "solve_attempted": False,
    "project": PROJECT_NAME, "design": DESIGN_NAME,
    "failure_under_audit": "periodic_mesh_perimeter_neighborhood_mismatch",
    "task_10_authorized": False,
}
try:
    if os.path.exists(OUT_PATH):
        raise RuntimeError("Refusing periodic audit overwrite")
    project = oDesktop.GetActiveProject()
    if project is None or project.GetName() != PROJECT_NAME:
        raise RuntimeError("Unexpected active project")
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    sheets = list(editor.GetObjectsInGroup("Sheets"))
    cuts = {}
    for name in sheets:
        edges = radial_edges(editor, name)
        if edges["x_axis"] or edges["y_axis"]:
            cuts[name] = edges
    payload.update({
        "status": "audited",
        "region_edges": radial_edges(editor, "Region"),
        "radial_cut_edges_by_object": cuts,
        "boundaries": normalize(design.GetModule("BoundarySetup").GetBoundaries()),
        "validation": normalize(design.ValidateDesign()),
        "errors": normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2)),
    })
except BaseException as exc:
    payload.update({
        "status": "error", "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    })
finally:
    parent = os.path.dirname(OUT_PATH)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    with open(OUT_PATH, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)
    try:
        AddWarningMessage("Direct r5 periodic failure audit: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
