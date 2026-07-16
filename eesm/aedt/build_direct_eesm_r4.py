"""Build a separate direct-geometry Maxwell 2-D EESM r4 project.

Run only inside AEDT Student 2025 R2.  The script owns a new project and
design, refuses to overwrite either, validates the complete geometry and
excitation inventory, saves build evidence, and never starts a solve.
"""

import json
import math
import os
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
PROJECT_NAME = "eesm_requal_direct_r4_04"
DESIGN_NAME = "EESM_2D_Direct_R4"
SETUP_NAME = "Setup_Qual"
GEOMETRY_REVISION = "academic-direct-r4-attempt4"
MATERIAL_REVISION = "steel-1008-direct-r4"
SOLVER_REVISION = "magnetostatic-xy-direct-r4"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r4")
OUT_JSON = os.path.join(OUT_ROOT, "model_build_status_attempt4.json")
STAINLESS_MATERIAL = "EESM_Nonmagnetic_Stainless_R4"


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


def warn(message):
    try:
        AddWarningMessage(message)
    except BaseException:
        print(message)


def write_status(payload):
    if not os.path.isdir(OUT_ROOT):
        os.makedirs(OUT_ROOT)
    path = OUT_JSON
    if os.path.exists(path):
        path = os.path.join(
            OUT_ROOT, "model_build_status_retry_%d.json" % int(time.time())
        )
    with open(path, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)
    warn("Direct EESM r4 build status: " + path)
    return path


def mm(value):
    return "%.12gmm" % float(value)


def attributes(name, material, color):
    return [
        "NAME:Attributes",
        "Name:=", name,
        "Flags:=", "",
        "Color:=", color,
        "Transparency:=", 0,
        "PartCoordinateSystem:=", "Global",
        "UDMId:=", "",
        "MaterialValue:=", '"' + material + '"',
        "SurfaceMaterialValue:=", '""',
        "SolveInside:=", True,
        "IsMaterialEditable:=", True,
        "UseMaterialAppearance:=", False,
        "IsLightweight:=", False,
    ]


def create_circle(editor, name, radius, material, color):
    editor.CreateCircle([
        "NAME:CircleParameters",
        "IsCovered:=", True,
        "XCenter:=", "0mm",
        "YCenter:=", "0mm",
        "ZCenter:=", "0mm",
        "Radius:=", mm(radius),
        "WhichAxis:=", "Z",
        "NumSegments:=", "0",
    ], attributes(name, material, color))
    return name


def xy(point, angle_deg):
    radius, tangent = point
    angle = math.radians(angle_deg)
    return (
        radius * math.cos(angle) - tangent * math.sin(angle),
        radius * math.sin(angle) + tangent * math.cos(angle),
    )


def create_polyline(editor, name, local_points, angle_deg, segment_specs,
                    material, color):
    points = ["NAME:PolylinePoints"]
    for point in local_points:
        x_value, y_value = xy(point, angle_deg)
        points.append([
            "NAME:PLPoint", "X:=", mm(x_value), "Y:=", mm(y_value),
            "Z:=", "0mm",
        ])
    segments = ["NAME:PolylineSegments"]
    for kind, start, count in segment_specs:
        segments.append([
            "NAME:PLSegment", "SegmentType:=", kind,
            "StartIndex:=", start, "NoOfPoints:=", count,
        ])
    editor.CreatePolyline([
        "NAME:PolylineParameters",
        "IsPolylineCovered:=", True,
        "IsPolylineClosed:=", True,
        points,
        segments,
        [
            "NAME:PolylineXSection", "XSectionType:=", "None",
            "XSectionOrient:=", "Auto", "XSectionWidth:=", "0mm",
            "XSectionTopWidth:=", "0mm", "XSectionHeight:=", "0mm",
            "XSectionNumSegments:=", "0", "XSectionBendType:=", "Corner",
        ],
    ], attributes(name, material, color))
    return name


def create_polygon(editor, name, local_points, angle_deg, material, color):
    segments = [("Line", index, 2) for index in range(len(local_points))]
    return create_polyline(
        editor, name, local_points, angle_deg, segments, material, color
    )


def subtract(editor, blank, tools, keep_originals):
    editor.Subtract([
        "NAME:Selections", "Blank Parts:=", blank,
        "Tool Parts:=", ",".join(tools),
    ], [
        "NAME:SubtractParameters", "CoordinateSystemID:=", -1,
        "KeepOriginals:=", keep_originals,
    ])


def add_variables(design):
    variables = [
        ("Id", "0A"),
        ("Iq", "0A"),
        ("If", "0A"),
        ("theta_e", "180deg"),
        ("I_phase_a", "Id*cos(theta_e)-Iq*sin(theta_e)"),
        ("I_phase_b", "Id*cos(theta_e-120deg)-Iq*sin(theta_e-120deg)"),
        ("I_phase_c", "Id*cos(theta_e+120deg)-Iq*sin(theta_e+120deg)"),
    ]
    props = ["NAME:NewProps"]
    for name, expression in variables:
        props.append([
            "NAME:" + name, "PropType:=", "VariableProp", "UserDef:=", True,
            "Value:=", expression,
        ])
    design.ChangeProperty([
        "NAME:AllTabs",
        [
            "NAME:LocalVariableTab", ["NAME:PropServers", "LocalVariables"],
            props,
        ],
    ])
    return dict(variables)


def add_stainless_material(project):
    manager = project.GetDefinitionManager()
    manager.AddMaterial([
        "NAME:" + STAINLESS_MATERIAL,
        "CoordinateSystemType:=", "Cartesian",
        "BulkOrSurfaceType:=", 1,
        ["NAME:PhysicsTypes", "set:=", ["Electromagnetic"]],
        "permeability:=", "1",
        "conductivity:=", "1.35e6",
    ])


def build_stator(editor):
    create_circle(editor, "Stator", 90.0, "steel_1008", "(132 132 193)")
    create_circle(editor, "BoreTool", 55.0, "vacuum", "(128 128 128)")
    slot_points = [
        (55.0, -1.0), (56.5, -1.0), (56.5, -3.5), (74.0, -3.5),
        (74.707106781187, -3.207106781187), (75.0, -2.5),
        (75.0, 2.5), (74.707106781187, 3.207106781187),
        (74.0, 3.5), (56.5, 3.5), (56.5, 1.0), (55.0, 1.0),
    ]
    slot_segments = [
        ("Line", 0, 2), ("Line", 1, 2), ("Line", 2, 2),
        ("Arc", 3, 3), ("Line", 5, 2), ("Arc", 6, 3),
        ("Line", 8, 2), ("Line", 9, 2), ("Line", 10, 2),
        ("Line", 11, 2),
    ]
    tools = ["BoreTool"]
    for slot in range(1, 25):
        name = "SlotTool_%02d" % slot
        create_polyline(
            editor, name, slot_points, 7.5 + 15.0 * (slot - 1),
            slot_segments, "vacuum", "(128 128 128)",
        )
        tools.append(name)
    subtract(editor, "Stator", tools, False)


def build_stator_conductors(editor):
    names = []
    top = [(56.5, -1.575), (65.75, -1.575),
           (65.75, 1.575), (56.5, 1.575)]
    bottom = [(65.75, -1.575), (75.0, -1.575),
              (75.0, 1.575), (65.75, 1.575)]
    for slot in range(1, 25):
        angle = 7.5 + 15.0 * (slot - 1)
        top_name = "StatorCoil_S%02d_T" % slot
        bottom_name = "StatorCoil_S%02d_B" % slot
        create_polygon(editor, top_name, top, angle, "copper", "(255 128 0)")
        create_polygon(
            editor, bottom_name, bottom, angle, "copper", "(255 128 0)"
        )
        names.extend([top_name, bottom_name])
    return names


def build_rotor(editor):
    create_circle(editor, "Rotor", 34.0, "steel_1008", "(132 132 193)")
    create_circle(
        editor, "Shaft", 20.0, STAINLESS_MATERIAL, "(0 255 255)"
    )
    subtract(editor, "Rotor", ["Shaft"], True)
    rotor_parts = ["Rotor"]
    for pole in range(1, 5):
        angle = 90.0 * (pole - 1)
        body = "PoleBody_%02d" % pole
        create_polygon(
            editor, body,
            [(34.0, -10.0), (49.0, -10.0),
             (49.0, 10.0), (34.0, 10.0)],
            angle, "steel_1008", "(132 132 193)",
        )
        shoe = "PoleShoe_%02d" % pole
        inner = shoe + "_Inner"
        wedge = shoe + "_Wedge"
        create_circle(editor, shoe, 54.4, "steel_1008", "(132 132 193)")
        create_circle(editor, inner, 49.0, "vacuum", "(128 128 128)")
        subtract(editor, shoe, [inner], False)
        create_polygon(
            editor, wedge,
            [(0.0, 0.0), (100.0, -100.0 * math.tan(math.radians(29.25))),
             (100.0, 100.0 * math.tan(math.radians(29.25)))],
            angle, "vacuum", "(128 128 128)",
        )
        editor.Intersect([
            "NAME:Selections", "Selections:=", shoe + "," + wedge,
        ], [
            "NAME:IntersectParameters", "KeepOriginals:=", False,
        ])
        rotor_parts.extend([body, shoe])
    editor.Unite([
        "NAME:Selections", "Selections:=", ",".join(rotor_parts),
    ], [
        "NAME:UniteParameters", "CoordinateSystemID:=", -1,
        "KeepOriginals:=", False,
    ])


def create_field_sheet(editor, name, tangent_min, tangent_max, angle):
    # The first tuple coordinate is a local Cartesian radial-axis coordinate,
    # not the point's true polar radius.  Clip the tangential strip with a
    # true 36--47 mm annulus so its outer corners cannot enter the r>=49 mm
    # pole-shoe steel.
    inner = name + "_Inner"
    strip = name + "_Strip"
    create_circle(editor, name, 47.0, "copper", "(255 128 0)")
    create_circle(editor, inner, 36.0, "vacuum", "(128 128 128)")
    subtract(editor, name, [inner], False)
    create_polygon(
        editor, strip,
        [(0.0, tangent_min), (60.0, tangent_min),
         (60.0, tangent_max), (0.0, tangent_max)],
        angle, "vacuum", "(128 128 128)",
    )
    editor.Intersect([
        "NAME:Selections", "Selections:=", name + "," + strip,
    ], [
        "NAME:IntersectParameters", "KeepOriginals:=", False,
    ])


def build_field_conductors(editor):
    names = []
    for pole in range(1, 5):
        angle = 90.0 * (pole - 1)
        left_name = "Field_P%02d_NegT" % pole
        right_name = "Field_P%02d_PosT" % pole
        create_field_sheet(editor, left_name, -15.075, -11.925, angle)
        create_field_sheet(editor, right_name, 11.925, 15.075, angle)
        names.extend([left_name, right_name])
    return names


def build_region(editor, machine_objects):
    # Use AEDT's special background Region primitive.  A single Boolean circle
    # minus all machine sheets is not robust because several tools share exact
    # boundaries (for example Shaft/Rotor).  Absolute 45 mm padding around the
    # 90 mm stator gives a +/-135 mm exterior without tool-tool Booleans.
    region_attributes = attributes("Region", "vacuum", "(0 255 255)")
    region_attributes[4] = "Wireframe#"
    editor.CreateRegion([
        "NAME:RegionParameters",
        "+XPaddingType:=", "Absolute Offset", "+XPadding:=", "45mm",
        "-XPaddingType:=", "Absolute Offset", "-XPadding:=", "45mm",
        "+YPaddingType:=", "Absolute Offset", "+YPadding:=", "45mm",
        "-YPaddingType:=", "Absolute Offset", "-YPadding:=", "45mm",
        "+ZPaddingType:=", "Absolute Offset", "+ZPadding:=", "0mm",
        "-ZPaddingType:=", "Absolute Offset", "-ZPadding:=", "0mm",
    ], region_attributes)


def assign_coil(boundary, terminal, object_name, turns, polarity, winding):
    boundary.AssignCoil([
        "NAME:" + terminal,
        "Objects:=", [object_name],
        "Conductor number:=", turns,
        "PolarityType:=", polarity,
        "Winding:=", winding,
    ])


def configure_windings(design):
    boundary = design.GetModule("BoundarySetup")
    currents = (
        ("PhaseA", "I_phase_a"), ("PhaseB", "I_phase_b"),
        ("PhaseC", "I_phase_c"), ("Field", "If"),
    )
    for winding, current in currents:
        boundary.AssignWindingGroup([
            "NAME:" + winding, "Type:=", "Current", "IsSolid:=", False,
            "Current:=", current, "Resistance:=", "0ohm",
            "Inductance:=", "0nH", "Voltage:=", "0V",
            "ParallelBranchesNum:=", "1",
        ])

    belts = {
        1: ("PhaseA", 1), 2: ("PhaseC", -1), 3: ("PhaseC", -1),
        4: ("PhaseB", 1), 5: ("PhaseB", 1), 6: ("PhaseA", -1),
        7: ("PhaseA", -1), 8: ("PhaseC", 1), 9: ("PhaseC", 1),
        10: ("PhaseB", -1), 11: ("PhaseB", -1), 12: ("PhaseA", 1),
    }
    for slot in range(13, 25):
        belts[slot] = belts[slot - 12]
    turns_by_start = {
        1: 4, 13: 4, 6: 5, 18: 5, 7: 4, 19: 4, 12: 5, 24: 5,
        2: 4, 14: 4, 3: 5, 15: 5, 8: 4, 20: 4, 9: 5, 21: 5,
        4: 4, 16: 4, 5: 5, 17: 5, 10: 4, 22: 4, 11: 5, 23: 5,
    }
    phase_turns = {"PhaseA": 0, "PhaseB": 0, "PhaseC": 0}
    terminals = []
    for start_slot in range(1, 25):
        winding, sign = belts[start_slot]
        turns = turns_by_start[start_slot]
        return_slot = ((start_slot + 5) % 24) + 1
        top_terminal = "%s_C%02d_T" % (winding, start_slot)
        bottom_terminal = "%s_C%02d_B" % (winding, start_slot)
        assign_coil(
            boundary, top_terminal, "StatorCoil_S%02d_T" % start_slot,
            turns, "Positive" if sign > 0 else "Negative", winding,
        )
        assign_coil(
            boundary, bottom_terminal, "StatorCoil_S%02d_B" % return_slot,
            turns, "Negative" if sign > 0 else "Positive", winding,
        )
        phase_turns[winding] += turns
        terminals.extend([top_terminal, bottom_terminal])

    for pole in range(1, 5):
        positive_on_right = pole % 2 == 1
        assign_coil(
            boundary, "Field_P%02d_NegT_Term" % pole,
            "Field_P%02d_NegT" % pole, 80,
            "Negative" if positive_on_right else "Positive", "Field",
        )
        assign_coil(
            boundary, "Field_P%02d_PosT_Term" % pole,
            "Field_P%02d_PosT" % pole, 80,
            "Positive" if positive_on_right else "Negative", "Field",
        )
        terminals.extend([
            "Field_P%02d_NegT_Term" % pole,
            "Field_P%02d_PosT_Term" % pole,
        ])
    return boundary, phase_turns, terminals


def configure_boundary(editor, boundary):
    edge_ids = [int(item) for item in list(editor.GetEdgeIDsFromObject("Region"))]
    if len(edge_ids) != 4:
        raise RuntimeError("Expected four exterior Region edges, got " + str(edge_ids))
    boundary.AssignVectorPotential([
        "NAME:Outer_A0", "Edges:=", edge_ids, "Value:=", "0",
        "CoordinateSystem:=", "",
    ])
    return edge_ids


def configure_setup(design):
    setup = design.GetModule("AnalysisSetup")
    setup.InsertSetup("Magnetostatic", [
        "NAME:" + SETUP_NAME, "Enabled:=", True,
        ["NAME:MeshLink", "ImportMesh:=", False],
        "MaximumPasses:=", 3, "MinimumPasses:=", 1,
        "MinimumConvergedPasses:=", 1, "PercentRefinement:=", 10,
        "SolveFieldOnly:=", False, "PercentError:=", 1,
        "SolveMatrixAtLast:=", True, "UseNonLinearIterNum:=", True,
        "MinIterNum:=", 5, "MaxIterNum:=", 20,
        "NonLinearResidual:=", 0.001, "SmoothBHCurve:=", True,
    ])
    mesh = design.GetModule("MeshSetup")
    mesh.InitialMeshSettings([
        "NAME:MeshSettings",
        [
            "NAME:GlobalSurfApproximation",
            "CurvedSurfaceApproxChoice:=", "UseSlider",
            "SliderMeshSettings:=", 1,
        ],
        ["NAME:GlobalModelRes", "UseAutoLength:=", True],
    ])


def configure_torque(design, field_objects):
    torque_objects = ["Rotor", "Shaft"] + list(field_objects)
    parameters = design.GetModule("MaxwellParameterSetup")
    parameters.AssignTorque([
        "NAME:TorqueRotor", "Is Virtual:=", True,
        "Coordinate System:=", "Global", "Axis:=", "Z",
        "Is Positive:=", True, "Objects:=", torque_objects,
    ])
    outputs = design.GetModule("OutputVariable")
    outputs.CreateOutputVariable(
        "Torque_FEM", "TorqueRotor.Torque", SETUP_NAME + " : LastAdaptive",
        "Magnetostatic", []
    )
    return torque_objects


def collect_messages():
    messages = {}
    for level in range(4):
        try:
            messages[str(level)] = normalize(
                oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, level)
            )
        except BaseException as exc:
            messages[str(level)] = {"error": str(exc)}
    return messages


def validate_inventory(design, editor, stator_objects, field_objects,
                       phase_turns):
    sheets = list(editor.GetObjectsInGroup("Sheets"))
    prohibited = [
        name for name in sheets
        if name.startswith("Bar") or name.startswith("Damper")
        or name.startswith("Mag") or name in ("Band", "InnerRegion")
    ]
    checks = {
        "stator_conductor_count": len(stator_objects) == 48,
        "field_conductor_count": len(field_objects) == 8,
        "required_core_objects": all(
            name in sheets for name in ("Stator", "Rotor", "Shaft", "Region")
        ),
        "no_prohibited_objects": not prohibited,
        "phase_turns": phase_turns == {
            "PhaseA": 36, "PhaseB": 36, "PhaseC": 36,
        },
        "setup_exists": SETUP_NAME in list(
            design.GetModule("AnalysisSetup").GetSetups()
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Direct r4 inventory checks failed: " + ", ".join(failed))
    validation = normalize(design.ValidateDesign())
    if validation not in (0, None, True):
        raise RuntimeError("Direct r4 design validation failed: " + str(validation))
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    if errors:
        raise RuntimeError("Direct r4 design recorded AEDT errors: " + str(errors))
    return {"checks": checks, "validation": validation, "prohibited": prohibited}


def build():
    if PROJECT_NAME in list(oDesktop.GetProjectList()):
        raise RuntimeError("Refusing to overwrite open direct r4 project")
    if os.path.exists(PROJECT_PATH):
        raise RuntimeError("Refusing to overwrite direct r4 project: " + PROJECT_PATH)
    project_dir = os.path.dirname(PROJECT_PATH)
    if not os.path.isdir(project_dir):
        os.makedirs(project_dir)
    project = oDesktop.NewProject()
    project.SaveAs(PROJECT_PATH, True)
    project.InsertDesign("Maxwell 2D", DESIGN_NAME, "Magnetostatic", "")
    design = project.SetActiveDesign(DESIGN_NAME)
    design.SetSolutionType("Magnetostatic", "XY")
    design.SetDesignSettings([
        "NAME:Design Settings Data", "ModelDepth:=", "120mm",
    ])
    editor = design.SetActiveEditor("3D Modeler")
    add_stainless_material(project)
    variables = add_variables(design)
    build_stator(editor)
    stator_objects = build_stator_conductors(editor)
    build_rotor(editor)
    field_objects = build_field_conductors(editor)
    machine_objects = ["Stator", "Rotor", "Shaft"] + stator_objects + field_objects
    build_region(editor, machine_objects)
    boundary, phase_turns, terminals = configure_windings(design)
    outer_edge = configure_boundary(editor, boundary)
    configure_setup(design)
    torque_objects = configure_torque(design, field_objects)
    inventory = validate_inventory(
        design, editor, stator_objects, field_objects, phase_turns
    )
    project.Save()
    return {
        "status": "built",
        "project": PROJECT_NAME,
        "project_path": PROJECT_PATH,
        "design": DESIGN_NAME,
        "setup": SETUP_NAME,
        "solution": SETUP_NAME + " : LastAdaptive",
        "geometry_revision": GEOMETRY_REVISION,
        "material_revision": MATERIAL_REVISION,
        "solver_revision": SOLVER_REVISION,
        "maxwell_solve_attempted": False,
        "Task10Authorized": False,
        "model_depth_mm": 120.0,
        "full_model_symmetry_multiplier": 1,
        "slot_bottom_radius_mm": 1.0,
        "stator_fill_factor": 0.45,
        "field_fill_factor": 0.45,
        "phase_turns": phase_turns,
        "field_turns_per_pole": 80,
        "variables": variables,
        "terminal_count": len(terminals),
        "torque_objects": torque_objects,
        "outer_boundary_edge": normalize(outer_edge),
        "inventory": inventory,
        "messages": collect_messages(),
    }


def main():
    try:
        payload = build()
    except BaseException as exc:
        payload = {
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc().splitlines(),
            "project": PROJECT_NAME,
            "project_path": PROJECT_PATH,
            "design": DESIGN_NAME,
            "setup": SETUP_NAME,
            "geometry_revision": GEOMETRY_REVISION,
            "maxwell_solve_attempted": False,
            "Task10Authorized": False,
            "messages": collect_messages(),
        }
    payload["status_path"] = write_status(payload)
    return payload


if __name__ == "__main__":
    main()
