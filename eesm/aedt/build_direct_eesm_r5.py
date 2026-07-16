"""Build a no-solve quarter-sector Maxwell 2-D EESM r5 project.

The represented physical sector is centred on pole 1 (-45..+45 mechanical
degrees), then globally rotated +45 degrees into AEDT's first quadrant.  That
coordinate-only rotation gives robust x/y radial edges for the same
Independent/Dependent anti-periodic convention used by RMxprt exports.

This script creates a new project, validates its inventory, records the
explicit extensive-quantity scaling contract, saves, and never solves.
"""

import hashlib
import json
import math
import os
import sys
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from build_direct_eesm_r4 import (  # noqa: E402
    attributes, create_circle, create_polygon, create_polyline, normalize,
    subtract,
)


REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
PROJECT_NAME = "eesm_requal_direct_r5_01"
DESIGN_NAME = "EESM_2D_Direct_R5_Quarter"
SETUP_NAME = "Setup_Qual"
GEOMETRY_REVISION = "academic-direct-r5-quarter-attempt1"
MATERIAL_REVISION = "steel-1008-direct-r5"
SOLVER_REVISION = "magnetostatic-xy-quarter-antiperiodic-r5"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r5")
OUT_JSON = os.path.join(OUT_ROOT, "model_build_status_attempt1.json")
STAINLESS_MATERIAL = "EESM_Nonmagnetic_Stainless_R5"
SECTOR_MULTIPLIER = 4
SECTOR_SLOT_MAP = (
    (22, 7.5, "PhaseB", -1, 4),
    (23, 22.5, "PhaseB", -1, 5),
    (24, 37.5, "PhaseA", 1, 5),
    (1, 52.5, "PhaseA", 1, 4),
    (2, 67.5, "PhaseC", -1, 4),
    (3, 82.5, "PhaseC", -1, 5),
)


def warn(message):
    try:
        AddWarningMessage(message)
    except BaseException:
        print(message)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


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
    warn("Direct EESM r5 build status: " + path)
    return path


def add_variables(design):
    variables = [
        ("Id", "0A"), ("Iq", "0A"), ("If", "0A"),
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
        ["NAME:LocalVariableTab", ["NAME:PropServers", "LocalVariables"], props],
    ])
    return dict(variables)


def add_stainless_material(project):
    project.GetDefinitionManager().AddMaterial([
        "NAME:" + STAINLESS_MATERIAL,
        "CoordinateSystemType:=", "Cartesian", "BulkOrSurfaceType:=", 1,
        ["NAME:PhysicsTypes", "set:=", ["Electromagnetic"]],
        "permeability:=", "1", "conductivity:=", "1.35e6",
    ])


def clip_to_quadrant(editor, object_name):
    tool = object_name + "_QuadrantClip"
    create_polygon(
        editor, tool,
        [(0.0, 0.0), (160.0, 0.0), (160.0, 160.0), (0.0, 160.0)],
        0.0, "vacuum", "(128 128 128)",
    )
    editor.Intersect([
        "NAME:Selections", "Selections:=", object_name + "," + tool,
    ], ["NAME:IntersectParameters", "KeepOriginals:=", False])


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
    for physical_slot, angle, _phase, _sign, _turns in SECTOR_SLOT_MAP:
        name = "SlotTool_S%02d" % physical_slot
        create_polyline(
            editor, name, slot_points, angle, slot_segments,
            "vacuum", "(128 128 128)",
        )
        tools.append(name)
    subtract(editor, "Stator", tools, False)
    clip_to_quadrant(editor, "Stator")


def build_stator_conductors(editor):
    top = [(56.5, -1.575), (65.75, -1.575),
           (65.75, 1.575), (56.5, 1.575)]
    bottom = [(65.75, -1.575), (75.0, -1.575),
              (75.0, 1.575), (65.75, 1.575)]
    names = []
    for physical_slot, angle, _phase, _sign, _turns in SECTOR_SLOT_MAP:
        for layer, points in (("T", top), ("B", bottom)):
            name = "StatorCoil_S%02d_%s" % (physical_slot, layer)
            create_polygon(editor, name, points, angle, "copper", "(255 128 0)")
            names.append(name)
    return names


def build_rotor(editor):
    create_circle(editor, "RotorYoke", 34.0, "steel_1008", "(132 132 193)")
    create_circle(editor, "Shaft", 20.0, STAINLESS_MATERIAL, "(0 255 255)")
    subtract(editor, "RotorYoke", ["Shaft"], True)
    clip_to_quadrant(editor, "RotorYoke")
    clip_to_quadrant(editor, "Shaft")

    angle = 45.0
    create_polygon(
        editor, "PoleBody_01",
        # Extend through the yoke and subtract it below.  This creates a
        # conformal r=34 mm arc interface instead of a one-point tangent.
        [(30.0, -10.0), (49.0, -10.0),
         (49.0, 10.0), (30.0, 10.0)],
        angle, "steel_1008", "(132 132 193)",
    )
    create_circle(editor, "PoleShoe_01", 54.4, "steel_1008", "(132 132 193)")
    create_circle(editor, "PoleShoe_01_Inner", 49.0, "vacuum", "(128 128 128)")
    subtract(editor, "PoleShoe_01", ["PoleShoe_01_Inner"], False)
    create_polygon(
        editor, "PoleShoe_01_Wedge",
        [(0.0, 0.0), (100.0, -100.0 * math.tan(math.radians(29.25))),
         (100.0, 100.0 * math.tan(math.radians(29.25)))],
        angle, "vacuum", "(128 128 128)",
    )
    editor.Intersect([
        "NAME:Selections", "Selections:=", "PoleShoe_01,PoleShoe_01_Wedge",
    ], ["NAME:IntersectParameters", "KeepOriginals:=", False])
    editor.Unite([
        "NAME:Selections", "Selections:=", "PoleBody_01,PoleShoe_01",
    ], [
        "NAME:UniteParameters", "CoordinateSystemID:=", -1,
        "KeepOriginals:=", False,
    ])
    editor.ChangeProperty([
        "NAME:AllTabs", [
            "NAME:Geometry3DAttributeTab",
            ["NAME:PropServers", "PoleBody_01"],
            ["NAME:ChangedProps", ["NAME:Name", "Value:=", "PoleAssembly_01"]],
        ],
    ])
    subtract(editor, "PoleAssembly_01", ["RotorYoke"], True)
    return ["RotorYoke", "Shaft", "PoleAssembly_01"]


def create_field_sheet(editor, name, tangent_min, tangent_max, angle):
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
    ], ["NAME:IntersectParameters", "KeepOriginals:=", False])


def build_field_conductors(editor):
    create_field_sheet(editor, "Field_P01_NegT", -15.075, -11.925, 45.0)
    create_field_sheet(editor, "Field_P01_PosT", 11.925, 15.075, 45.0)
    return ["Field_P01_NegT", "Field_P01_PosT"]


def build_region(editor):
    # The clipped machine has x>=0 and y>=0.  Zero negative padding preserves
    # the two radial symmetry edges; +45 mm produces x/y outer edges at 135 mm.
    region_attributes = attributes("Region", "vacuum", "(0 255 255)")
    region_attributes[4] = "Wireframe#"
    editor.CreateRegion([
        "NAME:RegionParameters",
        "+XPaddingType:=", "Absolute Offset", "+XPadding:=", "45mm",
        "-XPaddingType:=", "Absolute Offset", "-XPadding:=", "0mm",
        "+YPaddingType:=", "Absolute Offset", "+YPadding:=", "45mm",
        "-YPaddingType:=", "Absolute Offset", "-YPadding:=", "0mm",
        "+ZPaddingType:=", "Absolute Offset", "+ZPadding:=", "0mm",
        "-ZPaddingType:=", "Absolute Offset", "-ZPadding:=", "0mm",
    ], region_attributes)


def assign_coil(boundary, terminal, object_name, turns, polarity, winding):
    boundary.AssignCoil([
        "NAME:" + terminal, "Objects:=", [object_name],
        "Conductor number:=", turns, "PolarityType:=", polarity,
        "Winding:=", winding,
    ])


def configure_windings(design):
    boundary = design.GetModule("BoundarySetup")
    for winding, current in (
        ("PhaseA", "I_phase_a"), ("PhaseB", "I_phase_b"),
        ("PhaseC", "I_phase_c"), ("Field", "If"),
    ):
        boundary.AssignWindingGroup([
            "NAME:" + winding, "Type:=", "Current", "IsSolid:=", False,
            "Current:=", current, "Resistance:=", "0ohm",
            "Inductance:=", "0nH", "Voltage:=", "0V",
            "ParallelBranchesNum:=", "1",
        ])

    conductor_turns = {"PhaseA": 0, "PhaseB": 0, "PhaseC": 0}
    terminals = []
    terminal_map = {}
    for slot, _angle, phase, sign, turns in SECTOR_SLOT_MAP:
        for layer in ("T", "B"):
            terminal = "%s_S%02d_%s" % (phase, slot, layer)
            object_name = "StatorCoil_S%02d_%s" % (slot, layer)
            polarity = "Positive" if sign > 0 else "Negative"
            assign_coil(boundary, terminal, object_name, turns, polarity, phase)
            terminals.append(terminal)
            conductor_turns[phase] += turns
            terminal_map[terminal] = {
                "object": object_name, "turns": turns, "polarity": polarity,
                "winding": phase,
            }

    for side, polarity in (("NegT", "Negative"), ("PosT", "Positive")):
        terminal = "Field_P01_%s_Term" % side
        object_name = "Field_P01_%s" % side
        assign_coil(boundary, terminal, object_name, 80, polarity, "Field")
        terminals.append(terminal)
        terminal_map[terminal] = {
            "object": object_name, "turns": 80, "polarity": polarity,
            "winding": "Field",
        }
    return boundary, conductor_turns, terminals, terminal_map


def configure_boundaries(editor, boundary):
    # These positions follow the exact GetEdgeByPosition + Master/Slave API
    # emitted by the repository's authoritative RMxprt Maxwell export.  The
    # special Region spans 0..135 mm in x and y.
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
        "ReverseU:=", True, "Master:=", "Quarter_Independent",
        "SameAsMaster:=", False,
    ])
    return {
        "independent_x_edge": radial_x, "dependent_y_edge": radial_y,
        "outer_a0_edges": outer,
        "edge_probe_positions_mm": {
            "independent_x": [45.0, 0.0], "dependent_y": [0.0, 45.0],
            "outer": [[135.0, 67.5], [67.5, 135.0]],
        },
        "same_as_master": False, "periodicity": "anti-periodic_90deg",
    }


def configure_setup(design):
    design.GetModule("AnalysisSetup").InsertSetup("Magnetostatic", [
        "NAME:" + SETUP_NAME, "Enabled:=", True,
        ["NAME:MeshLink", "ImportMesh:=", False],
        "MaximumPasses:=", 3, "MinimumPasses:=", 1,
        "MinimumConvergedPasses:=", 1, "PercentRefinement:=", 10,
        "SolveFieldOnly:=", False, "PercentError:=", 1,
        "SolveMatrixAtLast:=", True, "UseNonLinearIterNum:=", True,
        "MinIterNum:=", 5, "MaxIterNum:=", 20,
        "NonLinearResidual:=", 0.001, "SmoothBHCurve:=", True,
    ])
    design.GetModule("MeshSetup").InitialMeshSettings([
        "NAME:MeshSettings",
        ["NAME:GlobalSurfApproximation",
         "CurvedSurfaceApproxChoice:=", "UseSlider", "SliderMeshSettings:=", 1],
        ["NAME:GlobalModelRes", "UseAutoLength:=", True],
    ])


def configure_torque(design, moving_objects):
    design.GetModule("MaxwellParameterSetup").AssignTorque([
        "NAME:TorqueRotor", "Is Virtual:=", True,
        "Coordinate System:=", "Global", "Axis:=", "Z",
        "Is Positive:=", True, "Objects:=", moving_objects,
    ])
    outputs = design.GetModule("OutputVariable")
    outputs.CreateOutputVariable(
        "Torque_FEM_Sector", "TorqueRotor.Torque",
        SETUP_NAME + " : LastAdaptive", "Magnetostatic", [],
    )
    outputs.CreateOutputVariable(
        "Torque_FEM", "4*TorqueRotor.Torque",
        SETUP_NAME + " : LastAdaptive", "Magnetostatic", [],
    )


def collect_messages():
    result = {}
    for level in range(4):
        try:
            result[str(level)] = normalize(
                oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, level)
            )
        except BaseException as exc:
            result[str(level)] = {"error": str(exc)}
    return result


def validate_inventory(design, editor, stator_objects, field_objects,
                       conductor_turns, terminal_map):
    sheets = list(editor.GetObjectsInGroup("Sheets"))
    expected_core = {"Stator", "RotorYoke", "Shaft", "PoleAssembly_01", "Region"}
    expected_terminal_map = {}
    for slot, _angle, phase, sign, turns in SECTOR_SLOT_MAP:
        for layer in ("T", "B"):
            terminal = "%s_S%02d_%s" % (phase, slot, layer)
            expected_terminal_map[terminal] = {
                "object": "StatorCoil_S%02d_%s" % (slot, layer),
                "turns": turns,
                "polarity": "Positive" if sign > 0 else "Negative",
                "winding": phase,
            }
    expected_terminal_map.update({
        "Field_P01_NegT_Term": {
            "object": "Field_P01_NegT", "turns": 80,
            "polarity": "Negative", "winding": "Field",
        },
        "Field_P01_PosT_Term": {
            "object": "Field_P01_PosT", "turns": 80,
            "polarity": "Positive", "winding": "Field",
        },
    })
    prohibited = [name for name in sheets if name.startswith(
        ("Bar", "Damper", "Mag", "SlotTool", "BoreTool")
    ) or name in ("Band", "InnerRegion")]
    checks = {
        "sheet_count_19": len(sheets) == 19,
        "stator_conductor_count_12": len(stator_objects) == 12,
        "field_conductor_count_2": len(field_objects) == 2,
        "required_core_objects": expected_core.issubset(set(sheets)),
        "no_prohibited_objects": not prohibited,
        "sector_conductor_turns_18_each": conductor_turns == {
            "PhaseA": 18, "PhaseB": 18, "PhaseC": 18,
        },
        "sector_series_turns_9_each": dict(
            (phase, turns // 2) for phase, turns in conductor_turns.items()
        ) == {"PhaseA": 9, "PhaseB": 9, "PhaseC": 9},
        "replicated_full_phase_turns_36_each": dict(
            (phase, turns // 2 * SECTOR_MULTIPLIER)
            for phase, turns in conductor_turns.items()
        ) == {"PhaseA": 36, "PhaseB": 36, "PhaseC": 36},
        "terminal_map_exact": terminal_map == expected_terminal_map,
        "setup_exists": SETUP_NAME in list(
            design.GetModule("AnalysisSetup").GetSetups()
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Direct r5 inventory checks failed: " + ", ".join(failed))
    validation = normalize(design.ValidateDesign())
    if validation not in (0, None, True):
        raise RuntimeError("Direct r5 design validation failed: " + str(validation))
    errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    if errors:
        raise RuntimeError("Direct r5 design recorded AEDT errors: " + str(errors))
    return {
        "checks": checks, "validation": validation, "prohibited": prohibited,
        "sheet_count": len(sheets),
    }


def build():
    if PROJECT_NAME in list(oDesktop.GetProjectList()):
        raise RuntimeError("Refusing to overwrite open direct r5 project")
    if os.path.exists(PROJECT_PATH):
        raise RuntimeError("Refusing to overwrite direct r5 project: " + PROJECT_PATH)
    project_dir = os.path.dirname(PROJECT_PATH)
    if not os.path.isdir(project_dir):
        os.makedirs(project_dir)
    project = oDesktop.NewProject()
    project.SaveAs(PROJECT_PATH, True)
    project.InsertDesign("Maxwell 2D", DESIGN_NAME, "Magnetostatic", "")
    design = project.SetActiveDesign(DESIGN_NAME)
    design.SetSolutionType("Magnetostatic", "XY")
    design.SetDesignSettings(["NAME:Design Settings Data", "ModelDepth:=", "120mm"])
    editor = design.SetActiveEditor("3D Modeler")
    add_stainless_material(project)
    variables = add_variables(design)
    build_stator(editor)
    stator_objects = build_stator_conductors(editor)
    moving_core = build_rotor(editor)
    field_objects = build_field_conductors(editor)
    build_region(editor)
    boundary, conductor_turns, terminals, terminal_map = configure_windings(design)
    boundary_contract = configure_boundaries(editor, boundary)
    configure_setup(design)
    moving_objects = moving_core + field_objects
    configure_torque(design, moving_objects)
    inventory = validate_inventory(
        design, editor, stator_objects, field_objects, conductor_turns, terminal_map
    )
    project.Save()
    return {
        "status": "built", "project": PROJECT_NAME,
        "project_path": PROJECT_PATH, "project_sha256": sha256(PROJECT_PATH),
        "design": DESIGN_NAME, "setup": SETUP_NAME,
        "solution": SETUP_NAME + " : LastAdaptive",
        "geometry_revision": GEOMETRY_REVISION,
        "material_revision": MATERIAL_REVISION,
        "solver_revision": SOLVER_REVISION,
        "maxwell_solve_attempted": False, "Task10Authorized": False,
        "model_depth_mm": 120.0,
        "sector_coordinate_frame_deg": [0.0, 90.0],
        "represented_physical_sector_deg": [-45.0, 45.0],
        "global_coordinate_rotation_deg": 45.0,
        "pole_center_coordinate_deg": 45.0,
        "sector_multiplier": SECTOR_MULTIPLIER,
        "aedt_magnetostatic_symmetry_multiplier_used": False,
        "scaling_contract": {
            "raw_sector_torque_output": "Torque_FEM_Sector",
            "full_machine_torque_output": "Torque_FEM",
            "torque_expression": "4*TorqueRotor.Torque",
            "coenergy": "preserve_raw_sector_value_and_multiply_by_4",
            "abc_flux_linkage": "preserve_raw_sector_value_and_multiply_by_4",
            "qualification_runner_scaling_required": True,
            "independent_solve_validation_required": True,
        },
        "offset_motion_contract": {
            "rotate_without_reclip": ["PoleAssembly_01"] + field_objects,
            "keep_fixed_axisymmetric": ["RotorYoke", "Shaft"],
            "validated_offset_range_deg": [-2.0, 2.0],
            "note": (
                "Rotate only the pole assembly and field sheets; they remain "
                "inside the quadrant for +/-2 deg. Do not Boolean-reclip them, "
                "and do not rotate the clipped axisymmetric yoke or shaft."
            ),
        },
        "sector_slots": [item[0] for item in SECTOR_SLOT_MAP],
        "sector_slot_map": [list(item) for item in SECTOR_SLOT_MAP],
        "sector_phase_conductor_turns": conductor_turns,
        "sector_phase_series_turns": dict(
            (phase, turns // 2) for phase, turns in conductor_turns.items()
        ),
        "replicated_full_phase_turns": dict(
            (phase, turns // 2 * SECTOR_MULTIPLIER)
            for phase, turns in conductor_turns.items()
        ),
        "field_turns_per_pole": 80, "variables": variables,
        "terminal_count": len(terminals), "terminal_map": terminal_map,
        "moving_objects": moving_objects,
        "boundary_contract": boundary_contract,
        "inventory": inventory, "messages": collect_messages(),
    }


def main():
    try:
        payload = build()
    except BaseException as exc:
        payload = {
            "status": "error", "error": str(exc),
            "traceback": traceback.format_exc().splitlines(),
            "project": PROJECT_NAME, "project_path": PROJECT_PATH,
            "design": DESIGN_NAME, "setup": SETUP_NAME,
            "geometry_revision": GEOMETRY_REVISION,
            "maxwell_solve_attempted": False, "Task10Authorized": False,
            "messages": collect_messages(),
        }
    payload["status_path"] = write_status(payload)
    return payload


if __name__ == "__main__":
    main()
