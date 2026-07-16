"""Read-only bounding-box/area audit for the preserved direct-r4 attempt 3."""

import json
import os
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
PROJECT_NAME = "eesm_requal_direct_r4_03"
DESIGN_NAME = "EESM_2D_Direct_R4"
PROJECT_PATH = os.path.abspath(os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
))
OUT_PATH = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r4",
    "attempt3_geometry_audit.json",
)
OBJECTS = ["Rotor", "Shaft", "Stator", "Region"] + [
    "Field_P%02d_%s" % (pole, side)
    for pole in range(1, 5) for side in ("NegT", "PosT")
]


def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def main():
    payload = {
        "status": "running", "project": PROJECT_NAME, "design": DESIGN_NAME,
        "project_path": PROJECT_PATH, "read_only": True,
        "maxwell_solve_attempted": False, "task_10_authorized": False,
    }
    try:
        project = oDesktop.GetActiveProject()
        if project is None or project.GetName() != PROJECT_NAME:
            raise RuntimeError("Active project must be " + PROJECT_NAME)
        active_path = os.path.abspath(os.path.join(
            str(project.GetPath()), project.GetName() + ".aedt"
        ))
        if os.path.normcase(active_path) != os.path.normcase(PROJECT_PATH):
            raise RuntimeError("Active project path drifted")
        design = project.SetActiveDesign(DESIGN_NAME)
        editor = design.SetActiveEditor("3D Modeler")
        sheets = set(editor.GetObjectsInGroup("Sheets"))
        records = {}
        for name in OBJECTS:
            if name not in sheets:
                raise RuntimeError("Missing audited sheet " + name)
            faces = list(editor.GetFaceIDs(name))
            records[name] = {
                "bounding_box": normalize(editor.GetObjectBoundingBox(name)),
                "face_ids": normalize(faces),
                "face_areas": [normalize(editor.GetFaceArea(face)) for face in faces],
                "edge_ids": normalize(editor.GetEdgeIDsFromObject(name)),
            }
        payload.update({"status": "audited", "objects": records})
    except BaseException as exc:
        payload.update({
            "status": "error", "error": str(exc),
            "traceback": traceback.format_exc().splitlines(),
        })
    if not os.path.isdir(os.path.dirname(OUT_PATH)):
        os.makedirs(os.path.dirname(OUT_PATH))
    with open(OUT_PATH, "w") as stream:
        json.dump(payload, stream, indent=2)
    try:
        AddWarningMessage("Direct r4 attempt3 geometry audit: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)


if __name__ == "__main__":
    main()
