"""Build distinct no-solve r9_02 after confirming AEDT's operation type.

The model mechanism is identical to r9 attempt1.  The only correction is the
post-assignment introspection query: AEDT confirmed that
``GetOperationNames('Surface Approximation Based')`` returns
``SurfApprox_Main`` while ``GetOperationNames('All')`` returns an empty list.
Attempt1 and its audit evidence remain immutable.
"""

import os
import sys

try:
    import builtins
except ImportError:  # IronPython 2 compatibility in older AEDT runtimes.
    import __builtin__ as builtins


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

_had_builtin_desktop = hasattr(builtins, "oDesktop")
_prior_builtin_desktop = getattr(builtins, "oDesktop", None)
builtins.oDesktop = oDesktop
try:
    import build_direct_eesm_r9 as r9  # noqa: E402
finally:
    if _had_builtin_desktop:
        builtins.oDesktop = _prior_builtin_desktop
    else:
        del builtins.oDesktop


base = r9.base
base.PROJECT_NAME = "eesm_requal_direct_r9_02"
base.DESIGN_NAME = "EESM_2D_Direct_R9_Quarter"
base.GEOMETRY_REVISION = "academic-direct-r9-rmxprt-surface-attempt2"
base.SOLVER_REVISION = "magnetostatic-xy-quarter-antiperiodic-r9"
base.PROJECT_PATH = os.path.join(
    base.REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", base.PROJECT_NAME,
    base.PROJECT_NAME + ".aedt",
)
base.OUT_ROOT = os.path.join(
    base.REPO_ROOT, "out", "eesm", "task9_requalification_r9"
)
base.OUT_JSON = os.path.join(base.OUT_ROOT, "model_build_status_attempt2.json")

base.oDesktop = oDesktop
if "AddWarningMessage" in globals():
    base.AddWarningMessage = AddWarningMessage


AUDIT_PATH = (
    "out/eesm/task9_requalification_r9/"
    "mesh_operation_type_audit_attempt1.json"
)
AUDIT_SHA256 = (
    "b85683096f880155870bc395f98d6092e04e70dd95575520d155e20fbb9b88f3"
)
CONFIRMED_OPERATION_TYPE = "Surface Approximation Based"


def validate_inventory(design, editor, stator_objects, field_objects,
                       conductor_turns, terminal_map):
    """Repeat r9's assignment, correcting only its introspection query."""
    available = set(str(name) for name in list(editor.GetObjectsInGroup("Sheets")))
    missing = [name for name in r9.SURFACE_APPROX_OBJECTS
               if name not in available]
    if missing:
        raise RuntimeError(
            "SurfApprox_Main direct-equivalent objects are missing: "
            + ", ".join(missing)
        )
    r9.configure_surface_approximation(design)
    operations = [str(name) for name in list(
        design.GetModule("MeshSetup").GetOperationNames(
            CONFIRMED_OPERATION_TYPE
        )
    )]
    if operations != ["SurfApprox_Main"]:
        raise RuntimeError(
            "Expected only SurfApprox_Main surface-approximation operation, got: "
            + str(operations)
        )
    return r9._r8_validate_inventory(
        design, editor, stator_objects, field_objects,
        conductor_turns, terminal_map,
    )


base.validate_inventory = validate_inventory
_r9_build = r9.build


def build():
    payload = _r9_build()
    payload["attempt1_introspection_correction"] = {
        "changed_mechanism": "GetOperationNames query string only",
        "attempt1_query": "All",
        "attempt2_query": CONFIRMED_OPERATION_TYPE,
        "audit_path": AUDIT_PATH,
        "audit_sha256": AUDIT_SHA256,
        "mesh_assignment_changed": False,
        "physics_changed": False,
    }
    return payload


base.build = build


def main():
    return base.main()


if __name__ == "__main__":
    main()
