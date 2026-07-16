"""Build the no-solve r6 quarter-sector model with corrected edge orientation.

r6 is deliberately identical to r5 except that the dependent periodic edge
uses ``ReverseU=False``.  The preserved r5 audit showed that both Region
radial edges are parameterized from the origin toward the outer corner, so
reversing only the dependent parameter direction made the paired meshes
incompatible.
"""

import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_direct_eesm_r5 as base  # noqa: E402


base.PROJECT_NAME = "eesm_requal_direct_r6_01"
base.DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"
base.GEOMETRY_REVISION = "academic-direct-r6-quarter-attempt2"
base.SOLVER_REVISION = "magnetostatic-xy-quarter-antiperiodic-r6"
base.PROJECT_PATH = os.path.join(
    base.REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", base.PROJECT_NAME,
    base.PROJECT_NAME + ".aedt",
)
base.OUT_ROOT = os.path.join(
    base.REPO_ROOT, "out", "eesm", "task9_requalification_r6"
)
base.OUT_JSON = os.path.join(base.OUT_ROOT, "model_build_status_attempt2.json")

# AEDT injects these symbols into the executed wrapper module.  Imported
# modules do not automatically inherit them, so pass the handles explicitly
# before delegating to the shared builder.
base.oDesktop = oDesktop
if "AddWarningMessage" in globals():
    base.AddWarningMessage = AddWarningMessage


def _vertices(editor, edge_id):
    return [
        [float(value) for value in editor.GetVertexPosition(int(vertex_id))]
        for vertex_id in list(editor.GetVertexIDsFromEdge(int(edge_id)))
    ]


def _origin_to_outer(points, axis):
    if len(points) != 2:
        return False
    origin = points[0]
    outer = points[1]
    other_axis = 1 - axis
    return (
        abs(origin[0]) <= 1e-8 and abs(origin[1]) <= 1e-8
        and abs(outer[other_axis]) <= 1e-8 and outer[axis] > 0.0
    )


def configure_boundaries(editor, boundary):
    def edge_at(x_value, y_value):
        return int(editor.GetEdgeByPosition([
            "NAME:Parameters", "BodyName:=", "Region",
            "XPosition:=", "%.12gmm" % x_value,
            "YPosition:=", "%.12gmm" % y_value, "ZPosition:=", "0mm",
        ]))

    radial_x = edge_at(45.0, 0.0)
    radial_y = edge_at(0.0, 45.0)
    outer = [edge_at(135.0, 67.5), edge_at(67.5, 135.0)]
    if len(set([radial_x, radial_y] + outer)) != 4:
        raise RuntimeError("Quarter Region edge lookup did not return four unique edges")

    radial_x_vertices = _vertices(editor, radial_x)
    radial_y_vertices = _vertices(editor, radial_y)
    if not _origin_to_outer(radial_x_vertices, 0):
        raise RuntimeError("Independent x radial edge is not directed origin-to-outer")
    if not _origin_to_outer(radial_y_vertices, 1):
        raise RuntimeError("Dependent y radial edge is not directed origin-to-outer")

    boundary.AssignVectorPotential([
        "NAME:Outer_A0", "Edges:=", outer, "Value:=", "0",
        "CoordinateSystem:=", "",
    ])
    boundary.AssignMaster([
        "NAME:Quarter_Independent", "Edges:=", [radial_x],
        "ReverseV:=", False,
    ])
    boundary.AssignSlave([
        "NAME:Quarter_Dependent", "Edges:=", [radial_y],
        "ReverseU:=", False, "Master:=", "Quarter_Independent",
        "SameAsMaster:=", False,
    ])
    return {
        "independent_x_edge": radial_x,
        "dependent_y_edge": radial_y,
        "outer_a0_edges": outer,
        "edge_probe_positions_mm": {
            "independent_x": [45.0, 0.0],
            "dependent_y": [0.0, 45.0],
            "outer": [[135.0, 67.5], [67.5, 135.0]],
        },
        "radial_edge_vertices_mm": {
            "independent_x": radial_x_vertices,
            "dependent_y": radial_y_vertices,
        },
        "reverse_v": False,
        "reverse_u": False,
        "same_as_master": False,
        "periodicity": "anti-periodic_90deg",
        "orientation_basis": "both Region radial edges run origin-to-outer",
    }


base.configure_boundaries = configure_boundaries


def main():
    return base.main()


if __name__ == "__main__":
    main()
