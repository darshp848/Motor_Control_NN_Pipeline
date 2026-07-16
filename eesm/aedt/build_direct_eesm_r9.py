"""Build the no-solve r9 model with generated curved-surface settings.

r9 preserves r8's RMxprt/Band quarter topology, boundary directions, machine
physics, setup, and manual x4 scaling.  Its one isolated mechanism change is
the ``SurfApprox_Main`` operation emitted by AEDT 2025 R2 for the locally
generated Maxwell 2D motor model.  This builder validates and saves a new
source project but never solves it or binds it to a campaign.
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
    import build_direct_eesm_r8 as r8  # noqa: E402
finally:
    if _had_builtin_desktop:
        builtins.oDesktop = _prior_builtin_desktop
    else:
        del builtins.oDesktop


base = r8.base
base.PROJECT_NAME = "eesm_requal_direct_r9_01"
base.DESIGN_NAME = "EESM_2D_Direct_R9_Quarter"
base.GEOMETRY_REVISION = "academic-direct-r9-rmxprt-surface-attempt1"
base.SOLVER_REVISION = "magnetostatic-xy-quarter-antiperiodic-r9"
base.PROJECT_PATH = os.path.join(
    base.REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", base.PROJECT_NAME,
    base.PROJECT_NAME + ".aedt",
)
base.OUT_ROOT = os.path.join(
    base.REPO_ROOT, "out", "eesm", "task9_requalification_r9"
)
base.OUT_JSON = os.path.join(base.OUT_ROOT, "model_build_status_attempt1.json")

base.oDesktop = oDesktop
if "AddWarningMessage" in globals():
    base.AddWarningMessage = AddWarningMessage


GENERATED_VBS = (
    "aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedtresults/"
    "RMxprtDesign1.results/DV106_SOL79_V0.MExportData/Maxwl2DV.vbs"
)
GENERATED_VBS_SHA256 = (
    "a07337b394a9bba6d78453f2478f0dba828829f19778bee65248129ded25719b"
)
SURFACE_APPROX_OBJECTS = [
    "Stator", "RotorYoke", "PoleAssembly_01", "OuterRegion", "Shaft",
]
SURFACE_APPROX_CONTRACT = {
    "name": "SurfApprox_Main",
    "objects": list(SURFACE_APPROX_OBJECTS),
    "surf_dev_choice": 2,
    "surf_dev": "0.09mm",
    "normal_dev_choice": 2,
    "normal_dev": "15deg",
    "aspect_ratio_choice": 1,
}


def configure_surface_approximation(design):
    """Apply the exact generated SurfApprox_Main manual settings."""
    design.GetModule("MeshSetup").AssignTrueSurfOp([
        "NAME:SurfApprox_Main",
        "Objects:=", list(SURFACE_APPROX_OBJECTS),
        "SurfDevChoice:=", 2,
        "SurfDev:=", "0.09mm",
        "NormalDevChoice:=", 2,
        "NormalDev:=", "15deg",
        "AspectRatioChoice:=", 1,
    ])


_r8_validate_inventory = base.validate_inventory


def validate_inventory(design, editor, stator_objects, field_objects,
                       conductor_turns, terminal_map):
    """Add the isolated mesh operation before running all r8 validation."""
    available = set(str(name) for name in list(editor.GetObjectsInGroup("Sheets")))
    missing = [name for name in SURFACE_APPROX_OBJECTS if name not in available]
    if missing:
        raise RuntimeError(
            "SurfApprox_Main direct-equivalent objects are missing: "
            + ", ".join(missing)
        )
    configure_surface_approximation(design)
    operations = [str(name) for name in list(
        design.GetModule("MeshSetup").GetOperationNames("All")
    )]
    if operations != ["SurfApprox_Main"]:
        raise RuntimeError(
            "Expected only SurfApprox_Main mesh operation, got: "
            + str(operations)
        )
    return _r8_validate_inventory(
        design, editor, stator_objects, field_objects,
        conductor_turns, terminal_map,
    )


base.validate_inventory = validate_inventory
_r8_build = r8.build


def build():
    payload = _r8_build()
    payload.pop("isolated_change_from_r7", None)
    payload["isolated_change_from_r8"] = "generated_surface_approximation_only"
    payload["surface_approximation_contract"] = dict(SURFACE_APPROX_CONTRACT)
    payload["surface_approximation_evidence"] = {
        "generated_vbs": GENERATED_VBS,
        "generated_vbs_sha256": GENERATED_VBS_SHA256,
        "generated_operation": "SurfApprox_Main",
    }
    payload["campaign_binding_authorized"] = False
    return payload


base.build = build


def main():
    return base.main()


if __name__ == "__main__":
    main()
