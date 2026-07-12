"""Build the canonical EESM qualification model inside AEDT.

Run manually from AEDT Student 2025 R2 with Automation -> Run Script.
This script rebuilds only EESM_2D_Qual, validates it, saves the project, and
never starts a solve.
"""

import json
import math
import os
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(ROOT, "eesm_model_build_status.json")
PROJECT_NAME = "eesm_qual"
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"
STEEL_NAME = "M270-35A"
MODEL_DEPTH = "120mm"


def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return dict((str(key), normalize(item)) for key, item in value.items())
    try:
        return [normalize(item) for item in list(value)]
    except BaseException:
        return str(value)


def call(fn):
    try:
        raw = fn()
        return {"ok": True, "value": normalize(raw), "_raw": raw}
    except BaseException as exc:
        return {
            "ok": False,
            "error": str(exc),
            "traceback_tail": traceback.format_exc().splitlines()[-8:],
        }


def required(fn, label):
    outcome = call(fn)
    if not outcome["ok"]:
        raise RuntimeError(label + ": " + outcome["error"])
    return outcome["_raw"]


def warn(message):
    try:
        AddWarningMessage(message)
    except BaseException:
        print(message)


def write_status(payload):
    with open(OUT_JSON, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def mm(value):
    return "%.9gmm" % float(value)


def rotate_xy(x_value, y_value, angle_deg):
    angle = math.radians(angle_deg)
    return (
        x_value * math.cos(angle) - y_value * math.sin(angle),
        x_value * math.sin(angle) + y_value * math.cos(angle),
    )


def attrs(name, material, color):
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
        "ShellElement:=", False,
        "ShellElementThickness:=", "0mm",
        "IsMaterialEditable:=", True,
        "UseMaterialAppearance:=", False,
        "IsLightweight:=", False,
    ]


def create_circle(editor, name, radius, material, color):
    return required(
        lambda: editor.CreateCircle(
            [
                "NAME:CircleParameters",
                "IsCovered:=", True,
                "XCenter:=", "0mm",
                "YCenter:=", "0mm",
                "ZCenter:=", "0mm",
                "Radius:=", mm(radius),
                "WhichAxis:=", "Z",
                "NumSegments:=", "0",
            ],
            attrs(name, material, color),
        ),
        "Create circle " + name,
    )


def create_polygon(editor, name, points, material, color):
    point_data = ["NAME:PolylinePoints"]
    for x_value, y_value in points:
        point_data.append([
            "NAME:PLPoint", "X:=", mm(x_value), "Y:=", mm(y_value), "Z:=", "0mm"
        ])
    segment_data = ["NAME:PolylineSegments"]
    for index in range(len(points)):
        segment_data.append([
            "NAME:PLSegment",
            "SegmentType:=", "Line",
            "StartIndex:=", index,
            "NoOfPoints:=", 2,
        ])
    parameters = [
        "NAME:PolylineParameters",
        "IsPolylineCovered:=", True,
        "IsPolylineClosed:=", True,
        point_data,
        segment_data,
        [
            "NAME:PolylineXSection",
            "XSectionType:=", "None",
            "XSectionOrient:=", "Auto",
            "XSectionWidth:=", "0mm",
            "XSectionTopWidth:=", "0mm",
            "XSectionHeight:=", "0mm",
            "XSectionNumSegments:=", "0",
            "XSectionBendType:=", "Corner",
        ],
    ]
    return required(
        lambda: editor.CreatePolyline(parameters, attrs(name, material, color)),
        "Create polygon " + name,
    )


def subtract(editor, blank_names, tool_names, keep_originals):
    return required(
        lambda: editor.Subtract(
            ["NAME:Selections", "Blank Parts:=", ",".join(blank_names),
             "Tool Parts:=", ",".join(tool_names)],
            ["NAME:SubtractParameters", "KeepOriginals:=", keep_originals],
        ),
        "Subtract " + ",".join(tool_names) + " from " + ",".join(blank_names),
    )


def unite(editor, names):
    return required(
        lambda: editor.Unite(
            ["NAME:Selections", "Selections:=", ",".join(names)],
            ["NAME:UniteParameters", "KeepOriginals:=", False],
        ),
        "Unite " + ",".join(names),
    )


def set_variables(design):
    variables = [
        ("Id", "0A"),
        ("Iq", "0A"),
        ("If", "0A"),
        ("theta_e", "0deg"),
        ("Ia", "Id"),
        ("Ib", "-0.5*Id + 0.866025403784*Iq"),
        ("Ic", "-0.5*Id - 0.866025403784*Iq"),
    ]
    new_props = ["NAME:NewProps"]
    for name, expression in variables:
        new_props.append([
            "NAME:" + name,
            "PropType:=", "VariableProp",
            "UserDef:=", True,
            "Value:=", expression,
        ])
    required(
        lambda: design.ChangeProperty([
            "NAME:AllTabs",
            [
                "NAME:LocalVariableTab",
                ["NAME:PropServers", "LocalVariables"],
                new_props,
            ],
        ]),
        "Create local variables",
    )
    return dict(variables)


def slot_phase(slot_number):
    normalized = ((slot_number - 1) % 12) + 1
    if normalized in (1, 12):
        return "A", "Positive"
    if normalized in (2, 3):
        return "C", "Negative"
    if normalized in (4, 5):
        return "B", "Positive"
    if normalized in (6, 7):
        return "A", "Negative"
    if normalized in (8, 9):
        return "C", "Positive"
    return "B", "Negative"


def invert_polarity(polarity):
    return "Negative" if polarity == "Positive" else "Positive"


def create_geometry(editor):
    created = []
    create_circle(editor, "StatorCore", 90.0, STEEL_NAME, "(115 115 160)")
    create_circle(editor, "StatorBoreTool", 55.0, "vacuum", "(255 255 255)")
    subtract(editor, ["StatorCore"], ["StatorBoreTool"], False)
    created.append("StatorCore")

    coil_records = []
    for slot in range(1, 25):
        angle = 7.5 + 15.0 * (slot - 1)
        slot_local = [(55.0, -1.0), (55.0, 1.0), (56.5, 3.5),
                      (75.0, 3.5), (75.0, -3.5), (56.5, -3.5)]
        slot_points = [rotate_xy(x, y, angle) for x, y in slot_local]
        slot_name = "SlotTool_%02d" % slot
        create_polygon(editor, slot_name, slot_points, "vacuum", "(255 255 255)")
        subtract(editor, ["StatorCore"], [slot_name], False)

        top_local = [(58.0, -2.75), (58.0, 2.75), (65.0, 2.75), (65.0, -2.75)]
        bottom_local = [(66.0, -2.75), (66.0, 2.75), (73.0, 2.75), (73.0, -2.75)]
        top_name = "StatorCoil_%02d_Top" % slot
        bottom_name = "StatorCoil_%02d_Bottom" % slot
        create_polygon(editor, top_name,
                       [rotate_xy(x, y, angle) for x, y in top_local],
                       "copper", "(255 128 0)")
        create_polygon(editor, bottom_name,
                       [rotate_xy(x, y, angle) for x, y in bottom_local],
                       "copper", "(255 170 0)")
        top_phase, top_polarity = slot_phase(slot)
        source_slot = ((slot - 7) % 24) + 1
        bottom_phase, source_polarity = slot_phase(source_slot)
        coil_records.append({
            "object": top_name, "phase": top_phase, "polarity": top_polarity,
            "turns": 36,
        })
        coil_records.append({
            "object": bottom_name, "phase": bottom_phase,
            "polarity": invert_polarity(source_polarity), "turns": 36,
        })
        created.extend([top_name, bottom_name])

    create_circle(editor, "RotorHub", 34.0, STEEL_NAME, "(100 100 145)")
    rotor_parts = ["RotorHub"]
    field_records = []
    for pole in range(4):
        angle = 90.0 * pole
        body_name = "PoleBody_P%d" % (pole + 1)
        body_local = [(34.0, -10.0), (49.0, -10.0), (49.0, 10.0), (34.0, 10.0)]
        create_polygon(editor, body_name,
                       [rotate_xy(x, y, angle) for x, y in body_local],
                       STEEL_NAME, "(100 100 145)")
        shoe_points = []
        for step in range(9):
            theta = -29.25 + 58.5 * step / 8.0
            shoe_points.append(rotate_xy(54.4 * math.cos(math.radians(theta)),
                                         54.4 * math.sin(math.radians(theta)), angle))
        for step in range(8, -1, -1):
            theta = -29.25 + 58.5 * step / 8.0
            shoe_points.append(rotate_xy(49.0 * math.cos(math.radians(theta)),
                                         49.0 * math.sin(math.radians(theta)), angle))
        shoe_name = "PoleShoe_P%d" % (pole + 1)
        create_polygon(editor, shoe_name, shoe_points, STEEL_NAME, "(100 100 145)")
        rotor_parts.extend([body_name, shoe_name])

        for side, y0, y1 in (("Pos", 10.0, 17.0), ("Neg", -17.0, -10.0)):
            coil_name = "FieldCoil_P%d_%s" % (pole + 1, side)
            field_local = [(36.0, y0), (47.0, y0), (47.0, y1), (36.0, y1)]
            create_polygon(editor, coil_name,
                           [rotate_xy(x, y, angle) for x, y in field_local],
                           "copper", "(220 90 40)")
            pole_positive = (pole % 2 == 0)
            side_positive = (side == "Pos")
            polarity = "Positive" if pole_positive == side_positive else "Negative"
            field_records.append({
                "object": coil_name, "phase": "Field", "polarity": polarity,
                "turns": 80,
            })
            created.append(coil_name)

    unite(editor, rotor_parts)
    required(
        lambda: editor.ChangeProperty([
            "NAME:AllTabs",
            ["NAME:Geometry3DAttributeTab", ["NAME:PropServers", "RotorHub"],
             ["NAME:ChangedProps", ["NAME:Name", "Value:=", "RotorCore"]]],
        ]),
        "Rename rotor core",
    )
    create_circle(editor, "Shaft", 20.0, "stainless_steel", "(90 90 90)")
    subtract(editor, ["RotorCore"], ["Shaft"], True)
    created.extend(["RotorCore", "Shaft"])

    create_circle(editor, "Region", 135.0, "vacuum", "(230 230 255)")
    subtract(editor, ["Region"], created, True)
    created.append("Region")
    return created, coil_records, field_records


def assign_winding(boundary, name, current_expression, records):
    required(
        lambda: boundary.AssignWindingGroup([
            "NAME:" + name,
            "Type:=", "Current",
            "IsSolid:=", False,
            "Current:=", current_expression,
            "Resistance:=", "0ohm",
            "Inductance:=", "0nH",
            "Voltage:=", "0V",
            "ParallelBranchesNum:=", "1",
            "Phase:=", "0deg",
        ]),
        "Assign winding " + name,
    )
    terminal_names = []
    for polarity in ("Positive", "Negative"):
        selected = [item for item in records if item["polarity"] == polarity]
        if not selected:
            continue
        names = [name + "_" + polarity + "_%02d" % (index + 1)
                 for index in range(len(selected))]
        objects = [item["object"] for item in selected]
        turns = str(selected[0]["turns"])
        required(
            lambda names=names, objects=objects, turns=turns, polarity=polarity:
                boundary.AssignCoilGroup(
                    names,
                    ["NAME:" + names[0], "Objects:=", objects,
                     "Conductor number:=", turns, "PolarityType:=", polarity],
                ),
            "Assign coil group " + name + " " + polarity,
        )
        terminal_names.extend(names)
    required(
        lambda: boundary.AddTerminalsToWinding([
            "NAME:AddTerminalsToWinding",
            ["NAME:BoundaryList"] + terminal_names,
            "Winding:=", name,
        ]),
        "Add coils to winding " + name,
    )
    return terminal_names


def assign_physics(design, editor, coil_records, field_records):
    boundary = required(lambda: design.GetModule("BoundarySetup"), "Get BoundarySetup")
    winding_terminals = {}
    for phase, expression in (("A", "Ia"), ("B", "Ib"), ("C", "Ic")):
        records = [item for item in coil_records if item["phase"] == phase]
        winding_terminals["Phase" + phase] = assign_winding(
            boundary, "Phase" + phase, expression, records
        )
    winding_terminals["Field"] = assign_winding(boundary, "Field", "If", field_records)

    edge_ids = required(lambda: editor.GetEdgeIDsFromObject("Region"),
                        "Get exterior region edges")
    required(
        lambda: boundary.AssignVectorPotential([
            "NAME:Outer_A0", "Edges:=", edge_ids, "Value:=", "0",
        ]),
        "Assign outer vector potential",
    )

    parameters = required(lambda: design.GetModule("MaxwellParameterSetup"),
                          "Get MaxwellParameterSetup")
    torque_objects = ["RotorCore", "Shaft"] + [item["object"] for item in field_records]
    required(
        lambda: parameters.AssignTorque([
            "NAME:TorqueRotor",
            "Is Virtual:=", True,
            "Coordinate System:=", "Global",
            "Axis:=", "Z",
            "Is Positive:=", True,
            "Objects:=", torque_objects,
        ]),
        "Assign torque parameter",
    )

    analysis = required(lambda: design.GetModule("AnalysisSetup"), "Get AnalysisSetup")
    required(
        lambda: analysis.InsertSetup("Magnetostatic", [
            "NAME:" + SETUP_NAME,
            "Enabled:=", True,
            "MaximumPasses:=", 8,
            "MinimumPasses:=", 2,
            "MinimumConvergedPasses:=", 1,
            "PercentRefinement:=", 20,
            "SolveFieldOnly:=", False,
            "PercentError:=", 1,
            "SolveMatrixAtLast:=", True,
            "UseNonLinearIterNum:=", True,
            "MinIterNum:=", 5,
            "MaxIterNum:=", 20,
            "NonLinearResidual:=", 0.001,
            "SmoothBHCurve:=", True,
        ]),
        "Insert magnetostatic setup",
    )
    mesh = required(lambda: design.GetModule("MeshSetup"), "Get MeshSetup")
    required(
        lambda: mesh.AssignLengthOp([
            "NAME:AirgapAndPoleTips",
            "RefineInside:=", False,
            "Objects:=", ["StatorCore", "RotorCore"],
            "RestrictElem:=", False,
            "NumMaxElem:=", "1000",
            "RestrictLength:=", True,
            "MaxLength:=", "0.25mm",
            "ApplyToInitialMesh:=", True,
        ]),
        "Assign local mesh refinement",
    )
    return winding_terminals


def design_names(project):
    return [str(item).split(";")[-1] for item in list(project.GetTopDesignList())]


payload = {
    "status": "running",
    "solve_attempted": False,
    "project": PROJECT_NAME,
    "design": DESIGN_NAME,
    "setup": SETUP_NAME,
    "checks": {},
}

try:
    project = required(lambda: oDesktop.SetActiveProject(PROJECT_NAME),
                       "Activate project " + PROJECT_NAME)
    names_before = design_names(project)
    if DESIGN_NAME in names_before:
        required(lambda: project.DeleteDesign(DESIGN_NAME),
                 "Delete owned design " + DESIGN_NAME)
    required(lambda: project.InsertDesign("Maxwell 2D", DESIGN_NAME,
                                          "Magnetostatic", ""),
             "Insert Maxwell 2D design")
    design = required(lambda: project.SetActiveDesign(DESIGN_NAME),
                      "Activate design " + DESIGN_NAME)
    required(lambda: design.SetSolutionType("Magnetostatic", "XY"),
             "Set Magnetostatic XY solution")
    required(lambda: design.SetDesignSettings([
        "NAME:Design Settings Data", "ModelDepth:=", MODEL_DEPTH,
    ]), "Set model depth")
    payload["variables"] = set_variables(design)
    editor = required(lambda: design.SetActiveEditor("3D Modeler"), "Get 3D Modeler")
    objects, coils, field_coils = create_geometry(editor)
    payload["objects"] = objects
    payload["winding_terminals"] = assign_physics(design, editor, coils, field_coils)
    payload["checks"]["validation"] = call(design.ValidateDesign)
    payload["checks"]["design_type"] = call(design.GetDesignType)
    payload["checks"]["solution_type"] = call(design.GetSolutionType)
    payload["checks"]["geometry_mode"] = call(design.GetGeometryMode)
    payload["checks"]["setups"] = call(lambda: design.GetModule("AnalysisSetup").GetSetups())
    payload["checks"]["excitations"] = call(
        lambda: design.GetModule("BoundarySetup").GetExcitations()
    )
    payload["checks"]["messages"] = dict(
        (str(level), call(lambda level=level:
            oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, level)))
        for level in range(4)
    )
    validation = payload["checks"]["validation"]
    if not validation["ok"] or validation.get("value") not in (0, None):
        raise RuntimeError("ValidateDesign did not succeed")
    required(project.Save, "Save project")
    payload["status"] = "built"
except BaseException as exc:
    payload["status"] = "error"
    payload["failure"] = {
        "error": str(exc),
        "traceback": traceback.format_exc().splitlines(),
    }
finally:
    write_status(payload)
    warn("EESM model build status: " + OUT_JSON)
