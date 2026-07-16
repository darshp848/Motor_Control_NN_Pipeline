"""Independent read-only verification of the saved r6 quarter-sector model."""

import hashlib
import json
import os
import re
import traceback


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECT_NAME = "eesm_requal_direct_r6_01"
DESIGN_NAME = "EESM_2D_Direct_R6_Quarter"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_DIR = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r6")
BUILD_STATUS_PATH = os.path.join(OUT_DIR, "model_build_status_attempt2.json")
OUT_PATH = os.path.join(OUT_DIR, "model_verification_attempt2.json")
SECTOR_SLOT_MAP = (
    (22, "PhaseB", "Negative", 4),
    (23, "PhaseB", "Negative", 5),
    (24, "PhaseA", "Positive", 5),
    (1, "PhaseA", "Positive", 4),
    (2, "PhaseC", "Negative", 4),
    (3, "PhaseC", "Negative", 5),
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


def properties(design, name):
    node = design.GetChildObject("Excitations").GetChildObject(name)
    return dict((prop, normalize(node.GetPropValue(prop)))
                for prop in list(node.GetPropNames()))


def conductors(props):
    return int(str(props.get("Number of Conductors", props.get("Conductor number"))))


def saved_polarity(project_text, terminal):
    pattern = (r"\$begin\s+'" + re.escape(terminal)
               + r"'.*?PolarityType='(Positive|Negative)'.*?\$end\s+'"
               + re.escape(terminal) + r"'")
    match = re.search(pattern, project_text, re.DOTALL)
    return match.group(1) if match else ""


def saved_integer_property(project_text, object_name, key):
    pattern = (r"\$begin\s+'" + re.escape(object_name) + r"'(.*?)"
               + r"\$end\s+'" + re.escape(object_name) + r"'")
    section = re.search(pattern, project_text, re.DOTALL)
    require(section is not None, "Saved object is missing: " + object_name)
    match = re.search(r"(?:^|\s)" + re.escape(key) + r"=(-?\d+)",
                      section.group(1))
    require(match is not None,
            "Saved integer property is missing: %s.%s" % (object_name, key))
    return int(match.group(1))


def expected_terminal_map():
    result = {}
    for slot, phase, polarity, turns in SECTOR_SLOT_MAP:
        for layer in ("T", "B"):
            name = "%s_S%02d_%s" % (phase, slot, layer)
            result[name] = {
                "object": "StatorCoil_S%02d_%s" % (slot, layer),
                "turns": turns, "polarity": polarity, "winding": phase,
            }
    result.update({
        "Field_P01_NegT_Term": {
            "object": "Field_P01_NegT", "turns": 80,
            "polarity": "Negative", "winding": "Field",
        },
        "Field_P01_PosT_Term": {
            "object": "Field_P01_PosT", "turns": 80,
            "polarity": "Positive", "winding": "Field",
        },
    })
    return result


def edge_at(editor, x_value, y_value):
    return int(editor.GetEdgeByPosition([
        "NAME:Parameters", "BodyName:=", "Region",
        "XPosition:=", "%.12gmm" % x_value,
        "YPosition:=", "%.12gmm" % y_value, "ZPosition:=", "0mm",
    ]))


def vertices(editor, edge_id):
    return [
        [float(value) for value in editor.GetVertexPosition(int(vertex_id))]
        for vertex_id in list(editor.GetVertexIDsFromEdge(int(edge_id)))
    ]


def origin_to_outer(points, axis):
    if len(points) != 2:
        return False
    return (
        abs(points[0][0]) <= 1e-8 and abs(points[0][1]) <= 1e-8
        and abs(points[1][1 - axis]) <= 1e-8 and points[1][axis] > 0.0
    )


def saved_boundary_flag(project_text, boundary_name, key, expected):
    pattern = (r"\$begin\s+'" + re.escape(boundary_name) + r"'(.*?)"
               + r"\$end\s+'" + re.escape(boundary_name) + r"'")
    section = re.search(pattern, project_text, re.DOTALL)
    require(section is not None, "Saved boundary is missing: " + boundary_name)
    require((key + "=" + expected) in section.group(1),
            "%s does not save %s=%s" % (boundary_name, key, expected))


def radial_cut_signature(editor, sheet_names):
    signature = {"x_axis": {}, "y_axis": {}}
    for name in sheet_names:
        for edge_id in [int(item) for item in list(editor.GetEdgeIDsFromObject(name))]:
            points = vertices(editor, edge_id)
            if not points:
                continue
            if all(abs(point[1]) <= 1e-8 for point in points):
                radii = sorted(abs(point[0]) for point in points)
                signature["x_axis"].setdefault(name, []).append(radii)
            if all(abs(point[0]) <= 1e-8 for point in points):
                radii = sorted(abs(point[1]) for point in points)
                signature["y_axis"].setdefault(name, []).append(radii)
    for axis in signature:
        for name in signature[axis]:
            signature[axis][name].sort()
    return signature


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
    require(os.path.isfile(BUILD_STATUS_PATH), "Direct r6 build status is missing")
    with open(BUILD_STATUS_PATH, "r") as stream:
        build_status = json.load(stream)
    require(build_status.get("status") == "built", "Direct r6 build did not succeed")
    require(build_status.get("maxwell_solve_attempted") is False,
            "Build status claims a solve")
    require(build_status.get("Task10Authorized") is False,
            "Build status improperly authorizes Task 10")
    require(build_status.get("sector_multiplier") == 4,
            "Quarter-sector multiplier drifted")
    require(os.path.isfile(PROJECT_PATH), "Direct r6 project is missing")
    project_hash = sha256(PROJECT_PATH)
    require(project_hash == build_status.get("project_sha256"),
            "Direct r6 project hash does not match build status")
    with open(PROJECT_PATH, "rb") as stream:
        project_text = str(stream.read())

    project = oDesktop.GetActiveProject()
    require(project is not None and project.GetName() == PROJECT_NAME,
            "Unexpected active project")
    active_path = os.path.abspath(os.path.join(
        str(project.GetPath()), project.GetName() + ".aedt"
    ))
    require(os.path.normcase(active_path) == os.path.normcase(os.path.abspath(PROJECT_PATH)),
            "Active project path drifted")
    design_names = [item.GetName() for item in list(project.GetDesigns())]
    require(design_names == [DESIGN_NAME], "Unexpected direct r6 designs")
    design = project.SetActiveDesign(DESIGN_NAME)
    editor = design.SetActiveEditor("3D Modeler")
    boundary = design.GetModule("BoundarySetup")
    sheets = set(editor.GetObjectsInGroup("Sheets"))
    excitations = list(boundary.GetExcitations())[0::2]
    boundaries = list(boundary.GetBoundaries())

    require(str(design.GetSolutionType()) == "Magnetostatic", "Solution is not Magnetostatic")
    require(str(design.GetGeometryMode()) == "XY", "Geometry is not XY")
    require(list(design.GetModule("AnalysisSetup").GetSetups()) == ["Setup_Qual"],
            "Unexpected setups")
    require(len(sheets) == 19, "Expected exactly 19 sheets")
    expected_sheets = {
        "Stator", "RotorYoke", "Shaft", "PoleAssembly_01", "Region",
        "Field_P01_NegT", "Field_P01_PosT",
    } | {
        "StatorCoil_S%02d_%s" % (slot, layer)
        for slot, _phase, _polarity, _turns in SECTOR_SLOT_MAP
        for layer in ("T", "B")
    }
    require(sheets == expected_sheets,
            "Exact 19-sheet inventory drifted: " + str(sorted(sheets)))
    require(boundaries == [
        "Outer_A0", "Vector Potential",
        "Quarter_Independent", "Independent",
        "Quarter_Dependent", "Dependent",
    ], "Boundary inventory/order drifted: " + str(boundaries))

    expected_map = expected_terminal_map()
    winding_id_to_name = dict(
        (saved_integer_property(project_text, name, "ID"), name)
        for name in ("PhaseA", "PhaseB", "PhaseC", "Field")
    )
    require(len(winding_id_to_name) == 4, "Saved winding group IDs are not unique")
    terminal_names = [name for name in excitations
                      if name not in ("PhaseA", "PhaseB", "PhaseC", "Field")]
    require(set(terminal_names) == set(expected_map), "Terminal names drifted")
    observed_map = {}
    for name in terminal_names:
        props = properties(design, name)
        expected = expected_map[name]
        observed = {
            "object": str(props.get("Assignment")),
            "turns": conductors(props),
            "polarity": saved_polarity(project_text, name),
            "winding": winding_id_to_name.get(
                saved_integer_property(project_text, name, "Winding")
            ),
        }
        require(observed == expected,
                "Terminal mapping drifted for %s: %s" % (name, observed))
        observed_map[name] = observed
    require(observed_map == expected_map, "Exact terminal map drifted")

    radial_x = edge_at(editor, 45.0, 0.0)
    radial_y = edge_at(editor, 0.0, 45.0)
    radial_vertices = {
        "independent_x": vertices(editor, radial_x),
        "dependent_y": vertices(editor, radial_y),
    }
    require(origin_to_outer(radial_vertices["independent_x"], 0),
            "Independent x edge is not directed origin-to-outer")
    require(origin_to_outer(radial_vertices["dependent_y"], 1),
            "Dependent y edge is not directed origin-to-outer")
    cut_signature = radial_cut_signature(editor, sheets)
    expected_cut_signature = {
        "Region": [[0.0, 135.0]],
        "Shaft": [[0.0, 20.0]],
        "RotorYoke": [[20.0, 34.0]],
        "Stator": [[55.0, 90.0]],
    }
    require(cut_signature["x_axis"] == expected_cut_signature,
            "Unexpected x radial cut signature: " + str(cut_signature["x_axis"]))
    require(cut_signature["y_axis"] == expected_cut_signature,
            "Unexpected y radial cut signature: " + str(cut_signature["y_axis"]))
    require(sorted(set(value for intervals in expected_cut_signature.values()
                       for interval in intervals for value in interval)) ==
            [0.0, 20.0, 34.0, 55.0, 90.0, 135.0],
            "Radial cut breakpoints drifted")
    saved_boundary_flag(project_text, "Quarter_Independent", "ReverseV", "false")
    saved_boundary_flag(project_text, "Quarter_Dependent", "ReverseU", "false")
    saved_boundary_flag(project_text, "Quarter_Dependent", "SameAsMaster", "false")
    outer_edges = [edge_at(editor, 135.0, 67.5), edge_at(editor, 67.5, 135.0)]
    require("Edges(%d)" % radial_x in saved_boundary_section(
        project_text, "Quarter_Independent"),
        "Independent boundary is not assigned to the resolved x radial edge")
    require("Edges(%d)" % radial_y in saved_boundary_section(
        project_text, "Quarter_Dependent"),
        "Dependent boundary is not assigned to the resolved y radial edge")
    outer_section = saved_boundary_section(project_text, "Outer_A0")
    require(all(str(edge_id) in outer_section for edge_id in outer_edges),
            "Outer_A0 is not assigned to both resolved exterior edges")

    require(design.GetModule("OutputVariable").DoesOutputVariableExist(
        "Torque_FEM_Sector"), "Raw sector torque output is missing")
    require(design.GetModule("OutputVariable").DoesOutputVariableExist(
        "Torque_FEM"), "Scaled torque output is missing")
    require("4*TorqueRotor.Torque" in project_text,
            "Saved x4 torque scaling expression is missing")
    scaling = build_status.get("scaling_contract", {})
    require(scaling.get("qualification_runner_scaling_required") is True and
            scaling.get("independent_solve_validation_required") is True,
            "Scaling caveat was not preserved")
    contract = build_status.get("boundary_contract", {})
    require(contract.get("reverse_v") is False and
            contract.get("reverse_u") is False and
            contract.get("same_as_master") is False,
            "Build boundary orientation contract drifted")

    validation = normalize(design.ValidateDesign())
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    require(validation in (0, None, True), "ValidateDesign failed: " + str(validation))
    require(not errors, "AEDT recorded design errors: " + str(errors))
    payload.update({
        "status": "verified", "project_sha256": project_hash,
        "designs": design_names, "sheet_count": len(sheets),
        "excitation_count": len(excitations), "terminal_count": len(terminal_names),
        "terminal_map": observed_map, "boundaries": boundaries,
        "radial_edge_ids": {"independent_x": radial_x, "dependent_y": radial_y},
        "radial_edge_vertices_mm": radial_vertices,
        "radial_cut_signature": cut_signature,
        "radial_breakpoints_mm": [0.0, 20.0, 34.0, 55.0, 90.0, 135.0],
        "outer_a0_edge_ids": outer_edges,
        "saved_periodic_contract": {
            "reverse_v": False, "reverse_u": False, "same_as_master": False,
        },
        "sector_multiplier": 4, "scaling_contract": scaling,
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
        AddWarningMessage("Direct EESM r6 verification: " + OUT_PATH)
    except BaseException:
        print(OUT_PATH)
