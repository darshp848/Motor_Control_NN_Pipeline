"""Build the no-solve r8 quarter model with the generated boundary direction.

r8 completes the missing interaction cell left by r5-r7.  It reuses r7's
RMxprt/Band 90 mm quarter domain, one consumed shared clipping Tool, machine
physics, Magnetostatic setup, and manual x4 output scaling verbatim.  The only
hypothesis change is ``ReverseU=True`` on the dependent y radial edge, matching
the Maxwell 2D script generated locally by AEDT 2025 R2 from the RMxprt motor.

This builder validates and saves a source project but never solves it.
"""

import math
import os
import sys

try:
    import builtins
except ImportError:  # IronPython 2 compatibility in older AEDT runtimes.
    import __builtin__ as builtins


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# r7 was originally an AEDT top-level script and therefore expects oDesktop
# during import.  Make the injected AEDT handle visible through Python's
# standard built-in fallback, then bind it explicitly to the shared base below.
_had_builtin_desktop = hasattr(builtins, "oDesktop")
_prior_builtin_desktop = getattr(builtins, "oDesktop", None)
builtins.oDesktop = oDesktop
try:
    import build_direct_eesm_r7 as r7  # noqa: E402
finally:
    if _had_builtin_desktop:
        builtins.oDesktop = _prior_builtin_desktop
    else:
        del builtins.oDesktop


base = r7.base
base.PROJECT_NAME = "eesm_requal_direct_r8_01"
base.DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"
base.GEOMETRY_REVISION = "academic-direct-r8-rmxprt-sector-attempt1"
base.SOLVER_REVISION = "magnetostatic-xy-quarter-antiperiodic-r8"
base.PROJECT_PATH = os.path.join(
    base.REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", base.PROJECT_NAME,
    base.PROJECT_NAME + ".aedt",
)
base.OUT_ROOT = os.path.join(
    base.REPO_ROOT, "out", "eesm", "task9_requalification_r8"
)
base.OUT_JSON = os.path.join(base.OUT_ROOT, "model_build_status_attempt1.json")

# AEDT injects these handles only into the executed wrapper module.
base.oDesktop = oDesktop
if "AddWarningMessage" in globals():
    base.AddWarningMessage = AddWarningMessage


def configure_boundaries(editor, boundary):
    """Keep r7 edge selection and change only dependent parameter direction."""
    def edge_at(x_value, y_value):
        return int(editor.GetEdgeByPosition([
            "NAME:Parameters", "BodyName:=", "OuterRegion",
            "XPosition:=", "%.12gmm" % x_value,
            "YPosition:=", "%.12gmm" % y_value, "ZPosition:=", "0mm",
        ]))

    radial_x = edge_at(45.0, 0.0)
    radial_y = edge_at(0.0, 45.0)
    diagonal = r7.OUTER_RADIUS_MM / math.sqrt(2.0)
    outer = edge_at(diagonal, diagonal)
    if len(set([radial_x, radial_y, outer])) != 3:
        raise RuntimeError("RMxprt OuterRegion did not expose three unique edges")
    boundary.AssignVectorPotential([
        "NAME:Outer_A0", "Edges:=", [outer], "Value:=", "0",
        "CoordinateSystem:=", "",
    ])
    boundary.AssignMaster([
        "NAME:Quarter_Independent", "Edges:=", [radial_x],
        "ReverseV:=", False,
    ])
    boundary.AssignSlave([
        "NAME:Quarter_Dependent", "Edges:=", [radial_y],
        "ReverseU:=", True, "Master:=", "Quarter_Independent",
        "SameAsMaster:=", False,
    ])
    return {
        "independent_x_edge": radial_x,
        "dependent_y_edge": radial_y,
        "outer_a0_edges": [outer],
        "edge_probe_positions_mm": {
            "independent_x": [45.0, 0.0],
            "dependent_y": [0.0, 45.0],
            "outer": [[diagonal, diagonal]],
        },
        "reverse_v": False, "reverse_u": True,
        "same_as_master": False, "periodicity": "anti-periodic_90deg",
        "domain_topology": "RMxprt/Band OuterRegion plus one consumed shared Tool",
        "orientation_basis": "AEDT-generated Maxwell 2D motor script",
    }


base.configure_boundaries = configure_boundaries
# Capture the named r7 wrapper explicitly.  It adds the full shared-tool
# topology contract after delegating to the original r5 physics builder.
_r7_build = r7.build


def build():
    payload = _r7_build()
    payload.pop("isolated_change_from_r6", None)
    payload["isolated_change_from_r7"] = "dependent_boundary_direction_only"
    payload["boundary_direction_evidence"] = {
        "generated_vbs": (
            "aedt_mcp/tmp/aedt_projects/eesm_qual/eesm_qual.aedtresults/"
            "RMxprtDesign1.results/DV106_SOL79_V0.MExportData/Maxwl2DV.vbs"
        ),
        "generated_vbs_sha256": (
            "a07337b394a9bba6d78453f2478f0dba828829f19778bee65248129ded25719b"
        ),
        "generated_contract": {
            "reverse_v": False, "reverse_u": True,
            "same_as_master": False,
        },
    }
    return payload


base.build = build


def main():
    return base.main()


if __name__ == "__main__":
    main()
