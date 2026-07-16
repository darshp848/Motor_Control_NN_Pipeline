"""Build the no-solve r7 quarter model with RMxprt sector topology.

r7 is deliberately identical to r6 in machine physics, Magnetostatic setup,
manual x4 scaling, and periodic-edge orientation.  Its only hypothesis change
is domain construction: one authoritative ``RMxprt/Band`` OuterRegion is
copied to an ``InfoCore=1`` Tool, and that single Tool clips every machine
sheet.  This mirrors the locally solved RMxprt-converted quarter model and
replaces r5/r6's per-object rectangles plus generic CreateRegion domain.
"""

import math
import os
import sys


ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import build_direct_eesm_r5 as base  # noqa: E402


base.PROJECT_NAME = "eesm_requal_direct_r7_01"
base.DESIGN_NAME = "EESM_2D_Direct_R7_Quarter"
base.GEOMETRY_REVISION = "academic-direct-r7-rmxprt-sector-attempt1"
base.SOLVER_REVISION = "magnetostatic-xy-quarter-antiperiodic-r7"
base.PROJECT_PATH = os.path.join(
    base.REPO_ROOT, "aedt_mcp", "tmp", "aedt_projects", base.PROJECT_NAME,
    base.PROJECT_NAME + ".aedt",
)
base.OUT_ROOT = os.path.join(
    base.REPO_ROOT, "out", "eesm", "task9_requalification_r7"
)
base.OUT_JSON = os.path.join(base.OUT_ROOT, "model_build_status_attempt1.json")

# AEDT injects these handles only into the executed wrapper module.
base.oDesktop = oDesktop
if "AddWarningMessage" in globals():
    base.AddWarningMessage = AddWarningMessage

OUTER_RADIUS_MM = 90.0
OUTER_DIAMETER_MM = 2.0 * OUTER_RADIUS_MM
SHARED_TOOL_NAME = "Tool"
SHARED_CLIP_TARGETS = []


def _defer_clip(_editor, _object_name):
    """Leave every machine sheet whole until the one shared Tool is ready."""


def _rmxprt_band(editor, name, info_core):
    editor.CreateUserDefinedPart([
        "NAME:UserDefinedPrimitiveParameters",
        "DllName:=", "RMxprt/Band", "Version:=", "12.1",
        "NoOfParameters:=", 7, "Library:=", "syslib",
        ["NAME:ParamVector",
         ["NAME:Pair", "Name:=", "DiaGap", "Value:=", "109.4mm"],
         ["NAME:Pair", "Name:=", "DiaYoke",
          "Value:=", "%.12gmm" % OUTER_DIAMETER_MM],
         ["NAME:Pair", "Name:=", "Length", "Value:=", "0mm"],
         ["NAME:Pair", "Name:=", "SegAngle", "Value:=", "0deg"],
         ["NAME:Pair", "Name:=", "Fractions", "Value:=", "4"],
         ["NAME:Pair", "Name:=", "HalfAxial", "Value:=", "0"],
         ["NAME:Pair", "Name:=", "InfoCore", "Value:=", str(info_core)]],
    ], [
        "NAME:Attributes", "Name:=", name, "Flags:=", "",
        "Color:=", "(0 255 255)", "Transparency:=", 0.75,
        "PartCoordinateSystem:=", "Global", "MaterialName:=", "vacuum",
        "SolveInside:=", True,
    ])


def build_region_and_shared_clip(editor):
    """Reproduce the saved RMxprt OuterRegion/copy/Tool clipping recipe."""
    targets = sorted(str(name) for name in list(editor.GetObjectsInGroup("Sheets")))
    if not targets or "OuterRegion" in targets or SHARED_TOOL_NAME in targets:
        raise RuntimeError("Unexpected pre-clip sheet inventory")
    SHARED_CLIP_TARGETS[:] = targets

    _rmxprt_band(editor, "OuterRegion", 100)
    editor.Copy(["NAME:Selections", "Selections:=", "OuterRegion"])
    editor.Paste()
    editor.SetPropertyValue(
        "Geometry3DCmdTab", "OuterRegion1:CreateUserDefinedPart:1",
        "InfoCore", "1",
    )
    editor.ChangeProperty([
        "NAME:AllTabs", [
            "NAME:Geometry3DAttributeTab",
            ["NAME:PropServers", "OuterRegion1"],
            ["NAME:ChangedProps", ["NAME:Name", "Value:=", SHARED_TOOL_NAME]],
        ],
    ])
    editor.Subtract([
        "NAME:Selections", "Blank Parts:=", ",".join(targets),
        "Tool Parts:=", SHARED_TOOL_NAME,
    ], [
        "NAME:SubtractParameters", "CoordinateSystemID:=", -1,
        "KeepOriginals:=", False,
    ])
    remaining = set(str(name) for name in list(editor.GetObjectsInGroup("Sheets")))
    if SHARED_TOOL_NAME in remaining:
        raise RuntimeError("Shared clipping Tool was not consumed")
    if "OuterRegion" not in remaining:
        raise RuntimeError("RMxprt OuterRegion is missing after shared clipping")
    return targets


def configure_boundaries(editor, boundary):
    def edge_at(x_value, y_value):
        return int(editor.GetEdgeByPosition([
            "NAME:Parameters", "BodyName:=", "OuterRegion",
            "XPosition:=", "%.12gmm" % x_value,
            "YPosition:=", "%.12gmm" % y_value, "ZPosition:=", "0mm",
        ]))

    radial_x = edge_at(45.0, 0.0)
    radial_y = edge_at(0.0, 45.0)
    diagonal = OUTER_RADIUS_MM / math.sqrt(2.0)
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
        "ReverseU:=", False, "Master:=", "Quarter_Independent",
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
        "reverse_v": False, "reverse_u": False,
        "same_as_master": False, "periodicity": "anti-periodic_90deg",
        "domain_topology": "RMxprt/Band OuterRegion plus one consumed shared Tool",
    }


def validate_inventory(design, editor, stator_objects, field_objects,
                       conductor_turns, terminal_map):
    sheets = list(editor.GetObjectsInGroup("Sheets"))
    expected_core = {
        "Stator", "RotorYoke", "Shaft", "PoleAssembly_01", "OuterRegion",
    }
    expected_terminals = {}
    for slot, _angle, phase, sign, turns in base.SECTOR_SLOT_MAP:
        for layer in ("T", "B"):
            terminal = "%s_S%02d_%s" % (phase, slot, layer)
            expected_terminals[terminal] = {
                "object": "StatorCoil_S%02d_%s" % (slot, layer),
                "turns": turns,
                "polarity": "Positive" if sign > 0 else "Negative",
                "winding": phase,
            }
    expected_terminals.update({
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
    ) or name in ("Band", "InnerRegion", "Region", SHARED_TOOL_NAME)
                  or name.endswith("_QuadrantClip")]
    checks = {
        "sheet_count_19": len(sheets) == 19,
        "stator_conductor_count_12": len(stator_objects) == 12,
        "field_conductor_count_2": len(field_objects) == 2,
        "required_core_objects": expected_core.issubset(set(sheets)),
        "rmxprt_outer_region_only": (
            "OuterRegion" in sheets and "Region" not in sheets
        ),
        "shared_tool_consumed": SHARED_TOOL_NAME not in sheets,
        "no_per_object_clip_sheets": not any(
            name.endswith("_QuadrantClip") for name in sheets
        ),
        "no_prohibited_objects": not prohibited,
        "sector_conductor_turns_18_each": conductor_turns == {
            "PhaseA": 18, "PhaseB": 18, "PhaseC": 18,
        },
        "replicated_full_phase_turns_36_each": dict(
            (phase, turns // 2 * base.SECTOR_MULTIPLIER)
            for phase, turns in conductor_turns.items()
        ) == {"PhaseA": 36, "PhaseB": 36, "PhaseC": 36},
        "terminal_map_exact": terminal_map == expected_terminals,
        "setup_exists": base.SETUP_NAME in list(
            design.GetModule("AnalysisSetup").GetSetups()
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Direct r7 inventory checks failed: " + ", ".join(failed))
    validation = base.normalize(design.ValidateDesign())
    if validation not in (0, None, True):
        raise RuntimeError("Direct r7 design validation failed: " + str(validation))
    errors = base.normalize(base.oDesktop.GetMessages(
        base.PROJECT_NAME, base.DESIGN_NAME, 2
    ))
    if errors:
        raise RuntimeError("Direct r7 design recorded AEDT errors: " + str(errors))
    return {
        "checks": checks, "validation": validation,
        "prohibited": prohibited, "sheet_count": len(sheets),
    }


base.clip_to_quadrant = _defer_clip
base.build_region = build_region_and_shared_clip
base.configure_boundaries = configure_boundaries
base.validate_inventory = validate_inventory


_base_build = base.build


def build():
    payload = _base_build()
    payload["domain_topology_contract"] = {
        "outer_region_primitive": "RMxprt/Band",
        "outer_region_info_core": 100,
        "outer_region_fractions": 4,
        "outer_radius_mm": OUTER_RADIUS_MM,
        "shared_tool_info_core": 1,
        "shared_tool_consumed": True,
        "shared_tool_targets": list(SHARED_CLIP_TARGETS),
        "per_object_quadrant_clips_used": False,
        "generic_create_region_used": False,
    }
    payload["isolated_change_from_r6"] = "domain_topology_only"
    return payload


base.build = build


def main():
    return base.main()


if __name__ == "__main__":
    main()
