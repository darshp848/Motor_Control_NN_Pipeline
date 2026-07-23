"""Build the canonical EESM in the active AEDT process, IPM-style.

Run with AEDT Student 2025 R2: Automation -> Run Script. This file is kept
compatible with AEDT's embedded Python. It creates an RMxprt TPSM, analyzes
the analytical setup required for conversion, creates Maxwell 2-D with auto
setup, saves the project, and never starts a Maxwell solve.
"""

import json
import os
import shutil
import time
import traceback


ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", "eesm_qual", "eesm_qual.aedt"
)
OUT_JSON = os.path.join(ROOT, "eesm_model_build_status.json")
PROJECT_NAME = "eesm_qual"
TEMPLATE_PROJECT = os.path.join(
    os.environ.get("ProgramFiles", r"C:\Program Files"),
    "ANSYS Inc", "ANSYS Student", "v252", "AnsysEM", "Examples", "RMxprt",
    "manual", "SynM3_6p50Hz538kW.aedt"
)
BACKUP_PROJECT = os.path.join(
    os.path.dirname(PROJECT_PATH), "eesm_qual.pre_synm_template.aedt"
)
RMXPRT_DESIGN = "RMxprtDesign1"
DESIGN_NAME = "EESM_2D_Qual"
SETUP_NAME = "Setup_Qual"


def normalize(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        if value.GetType().FullName == "System.Boolean":
            return bool(value)
    except BaseException:
        pass
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
    with open(OUT_JSON, "w") as stream:
        json.dump(normalize(payload), stream, indent=2)


def required(label, function):
    try:
        return function()
    except BaseException as exc:
        raise RuntimeError(label + ": " + str(exc))


def design_name(raw):
    return str(raw).split(";")[-1]


def project_design_names(project):
    return [design_name(item) for item in list(project.GetTopDesignList())]


def get_design_object(project, name):
    # RMxprt top-level identifiers can include the design flow prefix. AEDT
    # 2025 R2 may reject the short name but accept the exact returned token.
    for raw_name in list(project.GetTopDesignList()):
        if design_name(raw_name) == name:
            try:
                return project.SetActiveDesign(raw_name)
            except BaseException:
                pass
    try:
        design = project.GetDesign(name)
        if design is not None:
            return design
    except BaseException:
        pass
    for design in list(project.GetDesigns()):
        try:
            if design_name(design.GetName()) == name:
                return design
        except BaseException:
            pass
    return None


def matching_design_identifiers(project, name):
    return [
        normalize(item) for item in list(project.GetTopDesignList())
        if design_name(item) == name
    ]


def collect_aedt_messages():
    messages = {}
    for level in range(4):
        try:
            messages[str(level)] = normalize(
                oDesktop.GetMessages(PROJECT_NAME, "", level)
            )
        except BaseException as exc:
            messages[str(level)] = {"error": str(exc)}
    return messages


def get_project():
    if PROJECT_NAME in list(oDesktop.GetProjectList()):
        project = oDesktop.SetActiveProject(PROJECT_NAME)
        if RMXPRT_DESIGN in project_design_names(project):
            return project
        # The earlier hand-created project is not a valid IPM-style seed.
        # Close it before replacing it with the installed synchronous-machine
        # example, exactly as the IPM pipeline copied its installed template.
        oDesktop.CloseProject(PROJECT_NAME)
        time.sleep(0.5)
    if os.path.isfile(PROJECT_PATH):
        if not os.path.isfile(BACKUP_PROJECT):
            shutil.copy2(PROJECT_PATH, BACKUP_PROJECT)
    directory = os.path.dirname(PROJECT_PATH)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    if not os.path.isfile(TEMPLATE_PROJECT):
        raise RuntimeError("Installed synchronous-machine template missing: " + TEMPLATE_PROJECT)
    shutil.copy2(TEMPLATE_PROJECT, PROJECT_PATH)
    oDesktop.OpenProject(PROJECT_PATH)
    project = oDesktop.SetActiveProject(PROJECT_NAME)
    if RMXPRT_DESIGN not in project_design_names(project):
        raise RuntimeError("Template project does not contain " + RMXPRT_DESIGN)
    return project


def find_property(node, labels):
    names = list(node.GetPropNames())
    for label in labels:
        if label in names:
            return node, label
    for child_name in list(node.GetChildNames()):
        found = find_property(node.GetChildObject(child_name), labels)
        if found:
            return found
    return None


def set_required(root, labels, value):
    found = find_property(root, labels)
    if not found:
        raise RuntimeError("Required RMxprt property not found: " + " / ".join(labels))
    node, label = found
    outcome = node.SetPropValue(label, value)
    if outcome is False:
        raise RuntimeError("RMxprt property is read-only: " + label)
    return {"label": label, "value": normalize(node.GetPropValue(label))}


def configure_machine(design):
    machine = required("Get RMxprt machine tree", lambda: design.GetChildObject("Machine"))
    general = required("Get General", lambda: machine.GetChildObject("General"))
    stator = required("Get Stator", lambda: machine.GetChildObject("Stator"))
    rotor = required("Get Rotor", lambda: machine.GetChildObject("Rotor"))
    steel = ["Material:=", "steel_1008"]
    assignments = [
        ("poles", general, ["Number of Poles", "Number of poles"], 4),
        ("reference_speed", general, ["Reference Speed"], "3000rpm"),
        ("stator_od", stator, ["Outer Diameter"], "180mm"),
        ("stator_id", stator, ["Inner Diameter"], "110mm"),
        ("stator_length", stator, ["Length", "Stack Length"], "120mm"),
        ("slots", stator, ["Number of Slots"], 24),
        ("slot_hs0", stator, ["Hs0"], "0.8mm"),
        ("slot_hs1", stator, ["Hs1"], "1.2mm"),
        ("slot_hs2", stator, ["Hs2"], "15mm"),
        ("slot_bs0", stator, ["Bs0"], "3mm"),
        ("slot_bs1", stator, ["Bs1"], "5mm"),
        ("slot_bs2", stator, ["Bs2"], "7mm"),
        ("stator_conductors", stator, ["Conductors per Slot"], 36),
        ("parallel_branches", stator, ["Parallel Branches"], 1),
        ("coil_pitch", stator, ["Coil Pitch"], 6),
        ("stator_steel", stator, ["Steel Type"], steel),
        ("rotor_od", rotor, ["Outer Diameter"], "108.8mm"),
        ("rotor_id", rotor, ["Inner Diameter"], "40mm"),
        ("rotor_length", rotor, ["Length", "Stack Length"], "120mm"),
        ("rotor_steel", rotor, ["Rotor[Steel Type]"], steel),
        ("pole_steel", rotor, ["Pole[Steel Type]"], steel),
        ("pole_body_height", rotor, ["Pole Body Height"], "25mm"),
        ("pole_body_width", rotor, ["Pole Body Width"], "20mm"),
        ("pole_shoe_height", rotor, ["Pole Shoe Height"], "5mm"),
        ("pole_shoe_width", rotor, ["Pole Shoe Width"], "45mm"),
        ("pole_arc_offset", rotor, ["Pole Arc Offset"], "0mm"),
        ("winding_clearance", rotor, ["Winding Clearance"], "2mm"),
        ("field_turns", rotor, ["Conductors per Pole"], 40),
        ("field_cross_width", rotor, ["Limited Cross Width"], "4mm"),
        ("field_cross_height", rotor, ["Limited Cross Height"], "5mm"),
        ("field_winding_fillet", rotor, ["Winding Fillet"], "0.5mm"),
        ("field_wire_width", rotor,
         ["Wire Size/WireSizeWireWidth"], "0.5mm"),
        ("field_wire_thickness", rotor,
         ["Wire Size/WireSizeWireThickness"], "0.5mm"),
        ("damper_slots", rotor, ["Damper Slots Per Pole"], "3"),
        ("damper_bs0", rotor, ["Bs0"], "1mm"),
        ("damper_bs1", rotor, ["Bs1"], "1.5mm"),
        ("damper_bs2", rotor, ["Bs2"], "1.5mm"),
        ("damper_hs0", rotor, ["Hs0"], "0.5mm"),
        # Preserve the installed SynM template's cast damper topology.  A
        # multi-bar cage and positive end length provide a valid bar extension.
        # Keep the radial ring height minimally positive: RMxprt requires > 0,
        # while SalientPoleCore rejects larger rings in this compact pole shoe.
        ("damper_end_ring_height", rotor, ["End Ring Height"], "0.1mm"),
        ("damper_end_ring_width", rotor, ["End Ring Width"], "2.5mm"),
        ("damper_end_length", rotor, ["End Length"], "5mm"),
        ("cast_rotor", rotor, ["Cast Rotor"], True),
    ]
    configured = {}
    for key, root, labels, value in assignments:
        configured[key] = set_required(root, labels, value)
    return configured


def insert_setup(design):
    analysis = design.GetModule("AnalysisSetup")
    if SETUP_NAME in list(analysis.GetSetups()):
        analysis.DeleteSetups([SETUP_NAME])
    analysis.InsertSetup("SYNM", [
        "NAME:" + SETUP_NAME,
        "Enabled:=", True,
        "RatedOutputPower:=", "10kW",
        "RatedVoltage:=", "400V",
        "RatedSpeed:=", "3000rpm",
        "OperatingTemperature:=", "75cel",
        "OperationType:=", "Motor",
        "LoadType:=", "ConstantPower",
        "RatedPowerFactor:=", 0.8,
        "WindingConnection:=", False,
        "ExciterEfficiency:=", 90,
        "StartingFieldResistance:=", "0ohm",
        "InputExcitingCurrent:=", True,
        "ExcitingCurrent:=", "2A",
    ])
    setups = list(analysis.GetSetups())
    if SETUP_NAME not in setups:
        raise RuntimeError("RMxprt setup was not created")
    return analysis


def maxwell_design_has_content(project, name):
    design = project.SetActiveDesign(name)
    if "Maxwell" not in str(design.GetDesignType()):
        return False
    try:
        editor = design.SetActiveEditor("3D Modeler")
        for group in ("Solids", "Sheets", "Lines"):
            if len(list(editor.GetObjectsInGroup(group))) > 0:
                return True
    except BaseException:
        pass
    try:
        return len(list(design.GetModule("AnalysisSetup").GetSetups())) > 0
    except BaseException:
        return False


def convert_to_maxwell(project, analysis, before_names):
    # Use only the method proven by the IPM pipeline. Never continue with
    # fallback conversion calls after AEDT creates a partial Maxwell design;
    # repeated model-export calls can destabilize AEDT Student.
    analysis.CreateMaxwell2DDesignWithAutoSetup(SETUP_NAME, "")
    after_names = project_design_names(project)
    candidates = [name for name in after_names if name not in before_names]
    for candidate in candidates:
        if maxwell_design_has_content(project, candidate):
            if candidate != DESIGN_NAME:
                project.SetActiveDesign(candidate).RenameDesignInstance(
                    candidate, DESIGN_NAME
                )
            return "CreateMaxwell2DDesignWithAutoSetup", []
    raise RuntimeError(
        "CreateMaxwell2DDesignWithAutoSetup returned without a usable Maxwell design"
    )


def remove_partial_maxwell_designs(project):
    removed = []
    for name in project_design_names(project):
        if name == DESIGN_NAME or name.startswith("Maxwell2DDesign"):
            project.DeleteDesign(name)
            removed.append(name)
    return removed


def add_qualification_variables(design):
    variables = [
        ("Id", "0A"),
        ("Iq", "0A"),
        ("If", "0A"),
        # The RMxprt export places the rotor d axis at 180 electrical degrees
        # in its own generated Park expressions at the initial 105 deg
        # mechanical position.  Keep that reviewed alignment explicit.
        ("theta_e", "180deg"),
        ("I_phase_a", "Id*cos(theta_e)-Iq*sin(theta_e)"),
        ("I_phase_b", "Id*cos(theta_e-120deg)-Iq*sin(theta_e-120deg)"),
        ("I_phase_c", "Id*cos(theta_e+120deg)-Iq*sin(theta_e+120deg)"),
    ]
    new_props = ["NAME:NewProps"]
    for name, expression in variables:
        new_props.append([
            "NAME:" + name,
            "PropType:=", "VariableProp",
            "UserDef:=", True,
            "Value:=", expression,
        ])
    design.ChangeProperty([
        "NAME:AllTabs",
        [
            "NAME:LocalVariableTab",
            ["NAME:PropServers", "LocalVariables"],
            new_props,
        ],
    ])
    return dict(variables)


def configure_maxwell_qualification(project):
    design = project.SetActiveDesign(DESIGN_NAME)
    oDesktop.ClearMessages(PROJECT_NAME, DESIGN_NAME, 3)
    design.SetSolutionType("Magnetostatic", "XY")
    editor = design.SetActiveEditor("3D Modeler")
    all_sheets = list(editor.GetObjectsInGroup("Sheets"))
    conversion_only = [name for name in ("Band", "InnerRegion") if name in all_sheets]
    if conversion_only:
        editor.Delete(["NAME:Selections", "Selections:=", ",".join(conversion_only)])
    retained_fields = [name for name in ("Field_0", "FieldRe_0") if name in all_sheets]
    if "Stator" in all_sheets and retained_fields:
        editor.Subtract(
            ["NAME:Selections", "Blank Parts:=", "Stator",
             "Tool Parts:=", ",".join(retained_fields)],
            ["NAME:SubtractParameters", "KeepOriginals:=", True],
        )
    variables = add_qualification_variables(design)

    boundary = design.GetModule("BoundarySetup")
    # ParallelBranchesNum: the r2 winding contract is 36 conductors/slot with
    # FOUR balanced stator branches -> 36 series turns/phase (see
    # eesm/docs/MAXWELL_EESM_QUALIFICATION.md). With 4 branches, the commanded
    # winding current is the TERMINAL current and AEDT drives each branch with
    # I/4, so the exporter's (id, iq) domain reads in terminal amps and the
    # per-sector flux linkage is the terminal flux linkage (multiplier x1).
    #
    # The previous value of "1" (series, 144 turns/phase) contradicted the
    # contract. Note: the 2026-07 flux-convention diagnostic probes were solved
    # with the old value; their labelled currents are BRANCH amps, i.e.
    # terminal amps / 4 under the contract. See flux_extraction_v2.py NOTES.
    #
    # The field winding is a single series circuit and keeps 1 branch.
    winding_currents = {
        "PhaseA": ("I_phase_a", "4"),
        "PhaseB": ("I_phase_b", "4"),
        "PhaseC": ("I_phase_c", "4"),
        "Field": ("If", "1"),
    }
    for name, (current, branches) in winding_currents.items():
        boundary.EditWindingGroup(name, [
            "NAME:" + name,
            "Type:=", "Current",
            "IsSolid:=", False,
            "Current:=", current,
            "Resistance:=", "0ohm",
            "Inductance:=", "0nH",
            "Voltage:=", "0V",
            "ParallelBranchesNum:=", branches,
            "Phase:=", "0deg",
        ])

    analysis = design.GetModule("AnalysisSetup")
    existing_setups = list(analysis.GetSetups())
    if existing_setups:
        analysis.DeleteSetups(existing_setups)
    analysis.InsertSetup("Magnetostatic", [
        "NAME:" + SETUP_NAME,
        "Enabled:=", True,
        ["NAME:MeshLink", "ImportMesh:=", False],
        "MaximumPasses:=", 3,
        "MinimumPasses:=", 1,
        "MinimumConvergedPasses:=", 1,
        "PercentRefinement:=", 10,
        "SolveFieldOnly:=", False,
        "PercentError:=", 1,
        "SolveMatrixAtLast:=", True,
        "UseNonLinearIterNum:=", True,
        "MinIterNum:=", 5,
        "MaxIterNum:=", 20,
        "NonLinearResidual:=", 0.001,
        "SmoothBHCurve:=", True,
    ])

    mesh = design.GetModule("MeshSetup")
    existing_mesh_ops = list(mesh.GetOperationNames("All"))
    for mesh_op in ("SurfApprox_Mag", "SurfApprox_Main", "CylindricalGap1"):
        if mesh_op in existing_mesh_ops:
            mesh.DeleteOp([mesh_op])
    mesh.InitialMeshSettings([
        "NAME:MeshSettings",
        [
            "NAME:GlobalSurfApproximation",
            "CurvedSurfaceApproxChoice:=", "UseSlider",
            "SliderMeshSettings:=", 1,
        ],
        ["NAME:GlobalModelRes", "UseAutoLength:=", True],
        "MeshMethod:=", "AnsoftClassic",
    ])

    object_names = []
    for group in ("Sheets", "Solids"):
        object_names.extend(list(editor.GetObjectsInGroup(group)))
    torque_objects = [
        name for name in object_names
        if name == "Rotor" or name == "Shaft" or name.startswith("Field")
        or name.startswith("Bar")
    ]
    if not torque_objects:
        raise RuntimeError("No generated rotor objects found for virtual torque")
    parameters = design.GetModule("MaxwellParameterSetup")
    parameters.AssignTorque([
        "NAME:TorqueRotor",
        "Is Virtual:=", True,
        "Coordinate System:=", "Global",
        "Axis:=", "Z",
        "Is Positive:=", True,
        "Objects:=", torque_objects,
    ])
    output_variables = design.GetModule("OutputVariable")
    if output_variables.DoesOutputVariableExist("Torque_FEM"):
        output_variables.DeleteOutputVariable("Torque_FEM")
    output_variables.CreateOutputVariable(
        "Torque_FEM", "TorqueRotor.Torque",
        SETUP_NAME + " : LastAdaptive", "Magnetostatic", []
    )
    validation = normalize(design.ValidateDesign())
    if validation not in (0, None, True):
        raise RuntimeError("Qualification Maxwell design validation failed: " + str(validation))
    design_errors = normalize(oDesktop.GetMessages(PROJECT_NAME, DESIGN_NAME, 2))
    if design_errors:
        raise RuntimeError(
            "Qualification Maxwell design recorded AEDT errors: "
            + str(design_errors)
        )
    return {
        "solution_type": normalize(design.GetSolutionType()),
        "geometry_mode": normalize(design.GetGeometryMode()),
        "setup": SETUP_NAME,
        "solution": SETUP_NAME + " : LastAdaptive",
        "variables": variables,
        "winding_currents": winding_currents,
        "torque_parameter": "TorqueRotor",
        "torque_output_variable": "Torque_FEM",
        "torque_objects": torque_objects,
        "rotor_position_electrical_deg": 180.0,
        "pole_pairs": 2,
    }


def build():
    payload = {
        "status": "running",
        "project_path": PROJECT_PATH,
        "rmxprt_design": RMXPRT_DESIGN,
        "design": DESIGN_NAME,
        "setup": SETUP_NAME,
        "rmxprt_solve_attempted": False,
        "maxwell_solve_attempted": False,
    }
    project = get_project()
    design = get_design_object(project, RMXPRT_DESIGN)
    if design is None:
        raise RuntimeError(
            "Unable to activate template design " + RMXPRT_DESIGN
            + " from " + str(project_design_names(project))
        )
    project.SetActiveDesign(RMXPRT_DESIGN)
    payload["removed_partial_maxwell_designs"] = remove_partial_maxwell_designs(
        project
    )
    payload["properties"] = configure_machine(design)
    analysis = insert_setup(design)
    project.Save()

    payload["rmxprt_solve_attempted"] = True
    design.Analyze(SETUP_NAME)
    before_names = project_design_names(project)
    payload["conversion_method"], payload["conversion_warnings"] = convert_to_maxwell(
        project, analysis, before_names
    )
    payload["qualification_contract"] = configure_maxwell_qualification(project)
    project.Save()
    payload["status"] = "built"
    return payload


def main():
    try:
        status = build()
    except BaseException as exc:
        status = {
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc().splitlines(),
            "project_path": PROJECT_PATH,
            "design": DESIGN_NAME,
            "setup": SETUP_NAME,
            "maxwell_solve_attempted": False,
            "aedt_messages": collect_aedt_messages(),
        }
    write_status(status)
    warn("EESM model build status: " + OUT_JSON)
    return status


if __name__ == "__main__":
    main()
