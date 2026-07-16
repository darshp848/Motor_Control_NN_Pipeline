"""Build a separate r3 project corrected to the frozen academic EESM spec."""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(ROOT))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_canonical_eesm as base
try:
    base.oDesktop = oDesktop
except NameError:
    pass
PROJECT_NAME = "eesm_requal_r3"
PROJECT_PATH = os.path.join(
    REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", PROJECT_NAME,
    PROJECT_NAME + ".aedt",
)
OUT_ROOT = os.path.join(REPO_ROOT, "out", "eesm", "task9_requalification_r3")
OUT_JSON = os.path.join(OUT_ROOT, "model_build_status.json")
BACKUP_PROJECT = os.path.join(os.path.dirname(PROJECT_PATH), PROJECT_NAME + ".pre_template.aedt")

_configure_machine = base.configure_machine
_configure_maxwell = base.configure_maxwell_qualification


def configure_corrected_machine(design):
    configured = _configure_machine(design)
    machine = base.required("Get RMxprt machine tree", lambda: design.GetChildObject("Machine"))
    stator = base.required("Get Stator", lambda: machine.GetChildObject("Stator"))
    rotor = base.required("Get Rotor", lambda: machine.GetChildObject("Rotor"))
    corrections = [
        ("parallel_branches", stator, ["Parallel Branches"], 4),
        ("field_turns", rotor, ["Conductors per Pole"], 160),
        # SynM3 requires a temporary cage for its native conversion. Keep the
        # proven three-bar seed, then reintegrate the exported bar sheets
        # are reassigned to rotor steel and united back into Rotor below, so
        # the final Maxwell geometry has neither a cage nor air-filled holes.
        ("damper_slots", rotor, ["Damper Slots Per Pole"], 3),
        ("cast_rotor", rotor, ["Cast Rotor"], True),
    ]
    for key, root, labels, value in corrections:
        configured[key] = base.set_required(root, labels, value)
    return configured


def configure_corrected_maxwell(project):
    design = project.SetActiveDesign(base.DESIGN_NAME)
    design.SetDesignSettings(["NAME:Design Settings Data", "ModelDepth:=", "120mm"])
    editor = design.SetActiveEditor("3D Modeler")
    objects = []
    for group in ("Sheets", "Solids"):
        objects.extend(list(editor.GetObjectsInGroup(group)))
    bars = [name for name in objects if name.startswith("Bar")]
    if bars:
        boundary = design.GetModule("BoundarySetup")
        boundary.DeleteBoundaries(["EndConnection1"])
        editor.AssignMaterial(
            ["NAME:Selections", "Selections:=", ",".join(bars)],
            ["NAME:Attributes", "MaterialValue:=", '"steel_1008"',
             "SolveInside:=", True, "IsMaterialEditable:=", True],
        )
    contract = _configure_maxwell(project)
    boundary = design.GetModule("BoundarySetup")
    for phase, current in (
        ("PhaseA", "I_phase_a"), ("PhaseB", "I_phase_b"),
        ("PhaseC", "I_phase_c"),
    ):
        boundary.EditWindingGroup(phase, [
            "NAME:" + phase, "Type:=", "Current", "IsSolid:=", False,
            "Current:=", current, "Resistance:=", "0ohm",
            "Inductance:=", "0nH", "Voltage:=", "0V",
            "ParallelBranchesNum:=", 4, "Phase:=", "0deg",
        ])
    contract["model_depth"] = "120mm"
    contract["stator_parallel_branches"] = 4
    contract["field_turns_per_pole"] = 80
    contract["damper_cage"] = False
    contract["damper_objects_reintegrated_as_rotor_steel"] = bars
    contract["damper_fill_strategy"] = "separate_steel_rotor_fill"
    return contract


base.PROJECT_NAME = PROJECT_NAME
base.PROJECT_PATH = PROJECT_PATH
base.OUT_JSON = OUT_JSON
base.BACKUP_PROJECT = BACKUP_PROJECT
base.configure_machine = configure_corrected_machine
base.configure_maxwell_qualification = configure_corrected_maxwell

if not os.path.isdir(OUT_ROOT):
    os.makedirs(OUT_ROOT)

if __name__ == "__main__":
    base.main()
