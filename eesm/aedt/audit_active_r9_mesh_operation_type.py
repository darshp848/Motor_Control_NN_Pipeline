"""Read-only audit of AEDT mesh-operation type names on open r9 attempt1.

Run this only against the still-open, unsaved r9 attempt1 design.  It calls
``GetOperationNames`` with the documented PyAEDT operation categories and an
``All`` control, records the exact responses, and makes no design mutation,
save, or solve call.
"""

import json
import os
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPECTED_PROJECT = "eesm_requal_direct_r9_01"
EXPECTED_DESIGN = "EESM_2D_Direct_R9_Quarter"
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r9")
OUT_PATH = os.path.join(OUT_DIR, "mesh_operation_type_audit_attempt1.json")

# ansys-aedt-core 0.20.2 Mesh.delete_mesh_operations names these two exact
# categories.  "All" is retained as the control that triggered this audit.
CANDIDATE_OPERATION_TYPES = [
    "Length Based",
    "Surface Approximation Based",
    "All",
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


payload = {
    "status": "running",
    "audit_mode": "read_only",
    "expected_project": EXPECTED_PROJECT,
    "expected_design": EXPECTED_DESIGN,
    "candidate_operation_types": CANDIDATE_OPERATION_TYPES,
    "maxwell_solve_attempted": False,
    "design_mutation_attempted": False,
    "project_save_attempted": False,
    "campaign_binding_authorized": False,
    "task_10_authorized": False,
}
try:
    project = oDesktop.GetActiveProject()
    if project is None or str(project.GetName()) != EXPECTED_PROJECT:
        raise RuntimeError(
            "Refusing unexpected active project: "
            + ("None" if project is None else str(project.GetName()))
        )
    design = project.GetActiveDesign()
    if design is None or str(design.GetName()) != EXPECTED_DESIGN:
        raise RuntimeError(
            "Refusing unexpected active design: "
            + ("None" if design is None else str(design.GetName()))
        )
    mesh = design.GetModule("MeshSetup")
    responses = {}
    for operation_type in CANDIDATE_OPERATION_TYPES:
        try:
            responses[operation_type] = {
                "status": "returned",
                "operation_names": normalize(mesh.GetOperationNames(operation_type)),
            }
        except BaseException as exc:
            responses[operation_type] = {
                "status": "error",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
    matching_types = [
        operation_type for operation_type in CANDIDATE_OPERATION_TYPES
        if "SurfApprox_Main" in
        (responses[operation_type].get("operation_names") or [])
    ]
    payload.update({
        "status": "audited",
        "active_project": str(project.GetName()),
        "active_design": str(design.GetName()),
        "responses": responses,
        "surfapprox_main_matching_types": matching_types,
        "exact_type_confirmed": (
            matching_types == ["Surface Approximation Based"]
        ),
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
        json.dump(normalize(payload), stream, indent=2)
    try:
        AddWarningMessage("Direct EESM r9 mesh-operation audit: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
