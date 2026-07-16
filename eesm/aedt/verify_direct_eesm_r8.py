"""Independent read-only, no-solve verification of the saved r8 model."""

import hashlib
import json
import math
import os
import re
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_direct_r8_01"
DESIGN_NAME = "EESM_2D_Direct_R8_Quarter"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r8")
BUILD_STATUS_PATH = os.path.join(OUT_DIR, "model_build_status_attempt1.json")
OUT_PATH = os.path.join(OUT_DIR, "model_verification_attempt1.json")
R7_STATUS_PATH = os.path.join(
    REPO_ROOT, "out", "eesm", "task9_requalification_r7",
    "model_build_status_attempt1.json",
)
GENERATED_VBS = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "eesm_qual",
    "eesm_qual.aedtresults", "RMxprtDesign1.results",
    "DV106_SOL79_V0.MExportData", "Maxwl2DV.vbs",
)
GENERATED_VBS_SHA256 = "a07337b394a9bba6d78453f2478f0dba828829f19778bee65248129ded25719b"
OUTER_RADIUS_MM = 90.0


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


def edge_at(editor, x_value, y_value):
    return int(editor.GetEdgeByPosition([
        "NAME:Parameters", "BodyName:=", "OuterRegion",
        "XPosition:=", "%.12gmm" % x_value,
        "YPosition:=", "%.12gmm" % y_value, "ZPosition:=", "0mm",
    ]))


def vertices(editor, edge_id):
    return [
        [float(value) for value in editor.GetVertexPosition(int(vertex_id))]
        for vertex_id in list(editor.GetVertexIDsFromEdge(int(edge_id)))
    ]


def endpoint_set(points):
    return set((round(point[0], 8), round(point[1], 8)) for point in points)


def saved_boundary_section(project_text, boundary_name):
    pattern = (r"\$begin\s+'" + re.escape(boundary_name) + r"'(.*?)"
               + r"\$end\s+'" + re.escape(boundary_name) + r"'")
    section = re.search(pattern, project_text, re.DOTALL)
    require(section is not None, "Saved boundary is missing: " + boundary_name)
    return section.group(1)


payload = {
    "status": "running", "read_only_verification": True,
    "project": PROJECT_NAME, "project_path": PROJECT_PATH,
    "design": DESIGN_NAME, "maxwell_solve_attempted": False,
    "task_10_authorized": False,
}
try:
    require(os.path.isfile(BUILD_STATUS_PATH), "Direct r8 build status is missing")
    require(os.path.isfile(R7_STATUS_PATH), "Immutable r7 build status is missing")
    with open(BUILD_STATUS_PATH, "r") as stream:
        build_status = json.load(stream)
    with open(R7_STATUS_PATH, "r") as stream:
        r7_status = json.load(stream)
    require(build_status.get("status") == "built", "Direct r8 build did not succeed")
    require(r7_status.get("status") == "built", "Reference r7 build did not succeed")
    require(build_status.get("maxwell_solve_attempted") is False,
            "Build status claims a solve")
    require(build_status.get("Task10Authorized") is False,
            "Build status improperly authorizes Task 10")
    require(build_status.get("isolated_change_from_r7") ==
            "dependent_boundary_direction_only",
            "r8 isolated-change declaration drifted")

    # Prove that topology and machine physics are unchanged from the immutable
    # r7 build record; the boundary direction is the only permitted delta.
    unchanged_fields = [
        "domain_topology_contract", "sector_slot_map", "terminal_map",
        "scaling_contract", "offset_motion_contract", "material_revision",
        "model_depth_mm", "field_turns_per_pole", "sector_multiplier",
        "sector_phase_series_turns", "replicated_full_phase_turns",
        "sector_phase_conductor_turns", "sector_slots", "terminal_count",
        "moving_objects", "variables", "setup", "solution", "inventory",
        "represented_physical_sector_deg", "sector_coordinate_frame_deg",
        "pole_center_coordinate_deg", "global_coordinate_rotation_deg",
        "aedt_magnetostatic_symmetry_multiplier_used",
    ]
    drifted = [name for name in unchanged_fields
               if build_status.get(name) != r7_status.get(name)]
    require(not drifted, "r8 drifted from r7 outside boundary direction: "
            + ", ".join(drifted))
    topology = build_status["domain_topology_contract"]
    require(topology.get("outer_region_primitive") == "RMxprt/Band",
            "RMxprt/Band OuterRegion contract drifted")
    require(topology.get("outer_radius_mm") == OUTER_RADIUS_MM,
            "OuterRegion radius drifted")
    require(topology.get("shared_tool_consumed") is True,
            "Shared Tool consumption contract drifted")
    require(len(topology.get("shared_tool_targets", [])) == 18,
            "Shared Tool must cover exactly 18 machine sheets")
    require(topology.get("per_object_quadrant_clips_used") is False and
            topology.get("generic_create_region_used") is False,
            "r7 shared-tool topology was not preserved")

    require(os.path.isfile(GENERATED_VBS), "Generated Maxwell 2D evidence is missing")
    require(sha256(GENERATED_VBS) == GENERATED_VBS_SHA256,
            "Generated Maxwell 2D evidence hash drifted")
    evidence = build_status.get("boundary_direction_evidence", {})
    require(evidence.get("generated_vbs_sha256") == GENERATED_VBS_SHA256,
            "Build did not bind the generated boundary-direction evidence")
    require(evidence.get("generated_contract") == {
        "reverse_v": False, "reverse_u": True, "same_as_master": False,
    }, "Generated boundary-direction contract drifted")

    require(os.path.isfile(PROJECT_PATH), "Direct r8 project is missing")
    project_hash = sha256(PROJECT_PATH)
    require(project_hash == build_status.get("project_sha256"),
            "Direct r8 project hash does not match build status")
    with open(PROJECT_PATH, "rb") as stream:
        project_text = stream.read().decode("latin-1")
    require(project_text.count("DllName='RMxprt/Band'") >= 2,
            "Saved OuterRegion/shared Tool history is missing")
    require("RegionParameters" not in project_text,
            "Generic CreateRegion history is prohibited in r8")
    require("_QuadrantClip" not in project_text,
            "Per-object quadrant clip history is prohibited in r8")

    project = oDesktop.GetActiveProject()
    require(project is not None and project.GetName() == PROJECT_NAME,
            "Unexpected active project")
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    sheets = set(str(name) for name in list(editor.GetObjectsInGroup("Sheets")))
    require(len(sheets) == 19, "Expected exactly 19 sheets")
    require("OuterRegion" in sheets and "Region" not in sheets,
            "RMxprt OuterRegion did not replace generic Region")
    require("Tool" not in sheets, "Shared clipping Tool was not consumed")
    require(set(topology["shared_tool_targets"]) == sheets - {"OuterRegion"},
            "Shared Tool target history does not cover every machine sheet")
    require(str(design.GetSolutionType()) == "Magnetostatic",
            "Solution is not Magnetostatic")
    require(str(design.GetGeometryMode()) == "XY", "Geometry is not XY")
    require(list(design.GetModule("AnalysisSetup").GetSetups()) == ["Setup_Qual"],
            "Unexpected setups")
    require(list(boundary.GetBoundaries()) == [
        "Outer_A0", "Vector Potential",
        "Quarter_Independent", "Independent",
        "Quarter_Dependent", "Dependent",
    ], "Boundary inventory/order drifted")

    radial_x = edge_at(editor, 45.0, 0.0)
    radial_y = edge_at(editor, 0.0, 45.0)
    diagonal = OUTER_RADIUS_MM / math.sqrt(2.0)
    outer = edge_at(editor, diagonal, diagonal)
    require(len(set([radial_x, radial_y, outer])) == 3,
            "OuterRegion did not expose three unique quarter edges")
    radial_vertices = {
        "independent_x": vertices(editor, radial_x),
        "dependent_y": vertices(editor, radial_y),
    }
    require(endpoint_set(radial_vertices["independent_x"]) == {
        (0.0, 0.0), (OUTER_RADIUS_MM, 0.0),
    }, "Independent edge is not exactly the 0..90 mm x radial edge")
    require(endpoint_set(radial_vertices["dependent_y"]) == {
        (0.0, 0.0), (0.0, OUTER_RADIUS_MM),
    }, "Dependent edge is not exactly the 0..90 mm y radial edge")

    independent = saved_boundary_section(project_text, "Quarter_Independent")
    dependent = saved_boundary_section(project_text, "Quarter_Dependent")
    outer_section = saved_boundary_section(project_text, "Outer_A0")
    require("Edges(%d)" % radial_x in independent and
            "ReverseV=false" in independent,
            "Independent boundary assignment/orientation drifted")
    require("Edges(%d)" % radial_y in dependent and
            "ReverseU=true" in dependent and
            "SameAsMaster=false" in dependent,
            "Dependent boundary assignment/orientation drifted")
    require("Edges(%d)" % outer in outer_section,
            "Outer_A0 is not assigned to the RMxprt outer arc")

    outputs = design.GetModule("OutputVariable")
    require(outputs.DoesOutputVariableExist("Torque_FEM_Sector"),
            "Raw sector torque output is missing")
    require(outputs.DoesOutputVariableExist("Torque_FEM"),
            "Manual x4 torque output is missing")
    require("4*TorqueRotor.Torque" in project_text,
            "Saved manual x4 torque expression is missing")
    require(build_status.get("aedt_magnetostatic_symmetry_multiplier_used") is False,
            "r8 must preserve r7 manual scaling without solver multiplier")
    validation = normalize(design.ValidateDesign())
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    require(validation in (0, None, True), "ValidateDesign failed: " + str(validation))
    require(not errors, "AEDT recorded design errors: " + str(errors))
    payload.update({
        "status": "verified", "project_sha256": project_hash,
        "sheet_count": len(sheets), "sheets": sorted(sheets),
        "r7_unchanged_fields": unchanged_fields,
        "domain_topology_contract": topology,
        "radial_edge_ids": {"independent_x": radial_x,
                            "dependent_y": radial_y, "outer": outer},
        "radial_edge_vertices_mm": radial_vertices,
        "saved_periodic_contract": {
            "reverse_v": False, "reverse_u": True,
            "same_as_master": False,
        },
        "manual_x4_scaling_preserved": True,
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
        AddWarningMessage("Direct EESM r8 verification: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
