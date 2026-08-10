"""Build the one-pole 90 deg EESM sector in FEMM, parametrised from config.py.

What this module does
---------------------
Emits the FEMM calls that create: stator steel and its six slots, twelve
double-layer coil sheets, rotor pole body and shoe, the field winding pair,
the airgap, the shaft, the outer boundary, antiperiodic conditions on the two
radial sector edges, and the four circuits PhaseA/PhaseB/PhaseC/Field.

What this module CANNOT do
--------------------------
Verify itself. The sector SHAPES (slot profile, pole shoe curvature, field
coil footprint) are reconstructed from RMxprt scalar dimensions; there is no
DXF or native geometry to check them against. They set Lq and therefore the
saliency ratio. Offline tests can only assert the recorded call sequence --
that the antiperiodic condition landed on two DISTINCT edges, that the turns
signs match the verbatim RMxprt map, that the depth is the emitted value.
Whether the resulting magnetic circuit is the real machine is an open
question that only a Windows solve plus measured data can close.

Geometric frame
---------------
The sector spans 0 .. 90 deg mechanical. The rotor pole (d-axis) is placed at
the sector centre, 45 deg mechanical. Stator slots are placed on a half-pitch
offset so no slot straddles a sector edge. The electrical angle between the
phase-A magnetic axis and this d-axis is NOT asserted here: it follows from
STATOR_COIL_MAP and must be MEASURED with a field-only probe, which is why
ExtractionConfig.d_axis_electrical_deg is flagged unverified.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from . import config as cfg_mod
from .config import (
    BOUNDARY_ANTIPERIODIC_NAME,
    BOUNDARY_OUTER_NAME,
    FIELD_CIRCUIT,
    FIELD_COIL_MAP,
    FemmConfig,
    PHASE_CIRCUITS,
    SECTOR_EDGE_HIGH,
    SECTOR_EDGE_LOW,
    STATOR_COIL_MAP,
    DEFAULT_CONFIG,
)


# ---------------------------------------------------------------------------
# Pure geometry helpers (no FEMM involved -- fully testable offline)
# ---------------------------------------------------------------------------


def polar_to_xy(radius_mm: float, angle_deg: float) -> Tuple[float, float]:
    angle = math.radians(angle_deg)
    return radius_mm * math.cos(angle), radius_mm * math.sin(angle)


def offset_polar_to_xy(radial_mm: float, tangential_mm: float,
                       axis_deg: float) -> Tuple[float, float]:
    """A point `radial_mm` along `axis_deg`, displaced `tangential_mm` across it."""
    angle = math.radians(axis_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    x = radial_mm * cos_a - tangential_mm * sin_a
    y = radial_mm * sin_a + tangential_mm * cos_a
    return x, y


def stator_outer_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return cfg.geometry.stator_outer_diameter_mm / 2.0


def stator_bore_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return cfg.geometry.stator_inner_diameter_mm / 2.0


def rotor_outer_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return cfg.geometry.rotor_outer_diameter_mm / 2.0


def shaft_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return cfg.geometry.shaft_diameter_mm / 2.0


def slot_bottom_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Radius of the deepest point of the stator slot."""
    geo = cfg.geometry
    return (stator_bore_radius_mm(cfg) + geo.slot_opening_height_mm
            + geo.slot_wedge_height_mm + geo.slot_body_height_mm)


def airgap_mid_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return (stator_bore_radius_mm(cfg) + rotor_outer_radius_mm(cfg)) / 2.0


def pole_axis_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """The rotor d-axis, at the centre of the sector by construction."""
    return cfg.machine.sector_span_deg / 2.0


def pole_shoe_inner_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return rotor_outer_radius_mm(cfg) - cfg.geometry.pole_shoe_height_mm


def pole_body_inner_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return pole_shoe_inner_radius_mm(cfg) - cfg.geometry.pole_body_height_mm


def stator_slot_center_angles_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> List[float]:
    """Slot centre angles inside the sector, on a half-pitch offset.

    The half-pitch offset is a modelling choice with a physical reason: it
    keeps every slot wholly inside the sector, so no slot is bisected by an
    antiperiodic edge.
    """
    pitch = cfg_mod.slot_pitch_deg(cfg)
    count = cfg_mod.slots_in_sector(cfg)
    return [(index + 0.5) * pitch for index in range(count)]


def layer_radii_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> Tuple[float, float]:
    """Label radii of the (lower, upper) coil sheet of a double-layer slot."""
    geo = cfg.geometry
    body_start = (stator_bore_radius_mm(cfg) + geo.slot_opening_height_mm
                  + geo.slot_wedge_height_mm)
    quarter = geo.slot_body_height_mm / 4.0
    return body_start + quarter, body_start + 3.0 * quarter


def stator_coil_labels(cfg: FemmConfig = DEFAULT_CONFIG
                       ) -> List[Dict[str, Any]]:
    """One entry per coil sheet: where it sits, its circuit, its signed turns.

    Sheet naming follows RMxprt: Coil_k is the lower layer of slot k and
    CoilRe_k the upper layer, for k in 0..5. Turns per sheet is
    conductors_per_sheet, signed by STATOR_COIL_MAP.

    All four sheets of a phase carry the SAME sign -- see the STATOR_COIL_MAP
    comment in config.py. The return conductors are in the adjacent sector and
    the antiperiodic boundary supplies their inversion.
    """
    angles = stator_slot_center_angles_deg(cfg)
    lower_radius, upper_radius = layer_radii_mm(cfg)
    turns = cfg.machine.conductors_per_sheet
    labels: List[Dict[str, Any]] = []
    for sheet_name, circuit, sign in STATOR_COIL_MAP:
        index = int(sheet_name.split("_")[-1])
        radius = upper_radius if sheet_name.startswith("CoilRe") else lower_radius
        x, y = polar_to_xy(radius, angles[index])
        labels.append({
            "name": sheet_name,
            "circuit": circuit,
            "turns": sign * turns,
            "x": x,
            "y": y,
            "slot_index": index,
            "layer": "upper" if sheet_name.startswith("CoilRe") else "lower",
            "group": cfg.api.group_stator_coils,
        })
    return labels


def field_coil_labels(cfg: FemmConfig = DEFAULT_CONFIG) -> List[Dict[str, Any]]:
    """The two field bundles flanking the pole body.

    OPPOSITE signs, unlike the stator. Both bundles are inside the model, so
    they are a genuine go/return pair; same-sign here would cancel the pole
    MMF instead of building it. See FIELD_COIL_MAP in config.py.
    """
    geo = cfg.geometry
    axis = pole_axis_deg(cfg)
    radial = (pole_body_inner_radius_mm(cfg) + pole_shoe_inner_radius_mm(cfg)) / 2.0
    offset = geo.pole_body_width_mm / 2.0 + geo.field_winding_clearance_mm
    turns = cfg.machine.field_turns_per_pole
    labels: List[Dict[str, Any]] = []
    for (name, sign) in FIELD_COIL_MAP:
        tangential = offset if sign > 0 else -offset
        x, y = offset_polar_to_xy(radial, tangential, axis)
        labels.append({
            "name": name,
            "circuit": FIELD_CIRCUIT,
            "turns": sign * turns,
            "x": x,
            "y": y,
            "group": cfg.api.group_field_coils,
        })
    return labels


def sector_edge_endpoints(cfg: FemmConfig = DEFAULT_CONFIG
                          ) -> Dict[str, Tuple[Tuple[float, float],
                                               Tuple[float, float]]]:
    """The two radial edges of the sector, as ((x0,y0),(x1,y1)) pairs.

    These are DISTINCT edges at 0 deg and sector_span_deg. Both carry the
    antiperiodic condition; applying it twice to one edge is a silent
    modelling failure, which is why the geometry test asserts two distinct
    midpoints.
    """
    inner = shaft_radius_mm(cfg)
    outer = stator_outer_radius_mm(cfg) * cfg.geometry.outer_boundary_scale
    return {
        SECTOR_EDGE_LOW: (polar_to_xy(inner, 0.0), polar_to_xy(outer, 0.0)),
        SECTOR_EDGE_HIGH: (
            polar_to_xy(inner, cfg.machine.sector_span_deg),
            polar_to_xy(outer, cfg.machine.sector_span_deg),
        ),
    }


def region_labels(cfg: FemmConfig = DEFAULT_CONFIG) -> List[Dict[str, Any]]:
    """Non-winding material regions: steel, air, shaft."""
    axis = pole_axis_deg(cfg)
    half_span = cfg.machine.sector_span_deg / 2.0
    stator_yoke_radius = (slot_bottom_radius_mm(cfg)
                          + stator_outer_radius_mm(cfg)) / 2.0
    pole_radius = (pole_body_inner_radius_mm(cfg)
                   + pole_shoe_inner_radius_mm(cfg)) / 2.0
    shoe_radius = (pole_shoe_inner_radius_mm(cfg)
                   + rotor_outer_radius_mm(cfg)) / 2.0
    # Interpolar air: a quarter-span away from the pole axis, i.e. between
    # this pole and the sector edge.
    interpolar_angle = axis + half_span / 2.0

    entries = [
        ("stator_yoke", stator_yoke_radius, half_span,
         cfg.materials.steel_material, cfg.api.group_stator_steel),
        ("airgap", airgap_mid_radius_mm(cfg), half_span,
         cfg.materials.air_material, cfg.api.group_airgap),
        ("pole_shoe", shoe_radius, axis,
         cfg.materials.steel_material, cfg.api.group_rotor_steel),
        ("pole_body", pole_radius, axis,
         cfg.materials.steel_material, cfg.api.group_rotor_steel),
        ("interpolar_air", pole_radius, interpolar_angle,
         cfg.materials.air_material, cfg.api.group_airgap),
        ("shaft", shaft_radius_mm(cfg) / 2.0, half_span,
         cfg.materials.steel_material, cfg.api.group_shaft),
    ]
    labels: List[Dict[str, Any]] = []
    for name, radius, angle, material, group in entries:
        x, y = polar_to_xy(radius, angle)
        labels.append({
            "name": name,
            "material": material,
            "x": x,
            "y": y,
            "group": group,
        })
    return labels


# ---------------------------------------------------------------------------
# Build report
# ---------------------------------------------------------------------------


@dataclass
class BuildReport:
    """What the build actually emitted. Returned for assertion and provenance."""

    circuits: List[str] = field(default_factory=list)
    coil_sheets: List[str] = field(default_factory=list)
    field_coils: List[str] = field(default_factory=list)
    antiperiodic_edges: List[str] = field(default_factory=list)
    material_regions: List[str] = field(default_factory=list)
    model_depth_m: float = 0.0
    steel_material: str = ""
    steel_is_placeholder: bool = True

    def as_dict(self) -> Dict[str, Any]:
        return {
            "circuits": list(self.circuits),
            "coil_sheets": list(self.coil_sheets),
            "field_coils": list(self.field_coils),
            "antiperiodic_edges": list(self.antiperiodic_edges),
            "material_regions": list(self.material_regions),
            "model_depth_m": self.model_depth_m,
            "steel_material": self.steel_material,
            "steel_is_placeholder": self.steel_is_placeholder,
        }


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


def _mm_to_m(value_mm: float) -> float:
    return value_mm / 1000.0


def define_problem(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> None:
    """mi_probdef. Depth is the RMxprt emitted value, in metres."""
    api = cfg.api
    handle.mi_probdef(
        api.problem_frequency_hz,
        api.problem_units,
        api.problem_type,
        api.problem_precision,
        cfg.machine.model_depth_m,
        api.problem_min_angle_deg,
    )


def define_materials(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> List[str]:
    """Pull the library materials. The steel is a flagged PLACEHOLDER."""
    materials = [cfg.materials.air_material, cfg.materials.coil_material,
                 cfg.materials.steel_material]
    for name in materials:
        handle.mi_getmaterial(name)
    return materials


def define_circuits(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> List[str]:
    """PhaseA/PhaseB/PhaseC/Field, all series-connected, all starting at 0 A."""
    names = list(PHASE_CIRCUITS) + [FIELD_CIRCUIT]
    for name in names:
        handle.mi_addcircprop(name, 0.0, cfg.api.circuit_type_series)
    return names


def define_boundaries(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> None:
    """Antiperiodic on the sector edges, Dirichlet A=0 on the outer arc."""
    api = cfg.api
    zeros = [0.0] * 8
    handle.mi_addboundprop(BOUNDARY_ANTIPERIODIC_NAME, *zeros,
                           api.boundary_format_antiperiodic)
    handle.mi_addboundprop(BOUNDARY_OUTER_NAME, *zeros,
                           api.boundary_format_prescribed_a)


def apply_antiperiodic_edges(handle: Any,
                             cfg: FemmConfig = DEFAULT_CONFIG) -> List[str]:
    """Apply the antiperiodic condition to BOTH radial edges, separately."""
    applied: List[str] = []
    for name, ((x0, y0), (x1, y1)) in sector_edge_endpoints(cfg).items():
        handle.mi_drawline(x0, y0, x1, y1)
        handle.mi_clearselected()
        handle.mi_selectsegment((x0 + x1) / 2.0, (y0 + y1) / 2.0)
        handle.mi_setsegmentprop(BOUNDARY_ANTIPERIODIC_NAME, 0, 1, 0, 0)
        handle.mi_clearselected()
        applied.append(name)
    return applied


def _place_label(handle: Any, x: float, y: float, material: str,
                 circuit: str, turns: float, group: int) -> None:
    handle.mi_addblocklabel(x, y)
    handle.mi_clearselected()
    handle.mi_selectlabel(x, y)
    # mi_setblockprop(blockname, automesh, meshsize, incircuit, magdir, group, turns)
    handle.mi_setblockprop(material, 1, 0, circuit, 0, group, turns)
    handle.mi_clearselected()


def build_sector(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> BuildReport:
    """Emit the whole sector model. Returns what was emitted.

    `handle` is whatever runtime.resolve_femm() produced: a live pyfemm
    module on Windows, or a MockFemm offline. This function never imports
    femm itself.
    """
    report = BuildReport()

    define_problem(handle, cfg)
    report.model_depth_m = cfg.machine.model_depth_m

    define_materials(handle, cfg)
    report.steel_material = cfg.materials.steel_material
    report.steel_is_placeholder = cfg_mod.PROVENANCE[
        "materials.steel_material"].unverified

    report.circuits = define_circuits(handle, cfg)
    define_boundaries(handle, cfg)

    # Steel / air / shaft outlines. The arcs bound the sector radially.
    outer_radius = stator_outer_radius_mm(cfg) * cfg.geometry.outer_boundary_scale
    span = cfg.machine.sector_span_deg
    max_arc_seg_deg = cfg.api.problem_min_angle_deg
    for radius in (shaft_radius_mm(cfg), rotor_outer_radius_mm(cfg),
                   stator_bore_radius_mm(cfg), slot_bottom_radius_mm(cfg),
                   outer_radius):
        x0, y0 = polar_to_xy(radius, 0.0)
        x1, y1 = polar_to_xy(radius, span)
        handle.mi_drawarc(x0, y0, x1, y1, span, max_arc_seg_deg)

    report.antiperiodic_edges = apply_antiperiodic_edges(handle, cfg)

    # Outer arc gets the Dirichlet condition.
    ox0, oy0 = polar_to_xy(outer_radius, 0.0)
    ox1, oy1 = polar_to_xy(outer_radius, span)
    handle.mi_clearselected()
    handle.mi_selectsegment((ox0 + ox1) / 2.0, (oy0 + oy1) / 2.0)
    handle.mi_setsegmentprop(BOUNDARY_OUTER_NAME, 0, 1, 0, 0)
    handle.mi_clearselected()

    for entry in region_labels(cfg):
        _place_label(handle, entry["x"], entry["y"], entry["material"],
                     "<None>", 0, entry["group"])
        report.material_regions.append(entry["name"])

    for entry in stator_coil_labels(cfg):
        _place_label(handle, entry["x"], entry["y"], cfg.materials.coil_material,
                     entry["circuit"], entry["turns"], entry["group"])
        report.coil_sheets.append(entry["name"])

    for entry in field_coil_labels(cfg):
        _place_label(handle, entry["x"], entry["y"], cfg.materials.coil_material,
                     entry["circuit"], entry["turns"], entry["group"])
        report.field_coils.append(entry["name"])

    return report


def open_and_build(handle: Any, document_path: str,
                   cfg: FemmConfig = DEFAULT_CONFIG) -> BuildReport:
    """openfemm -> newdocument -> build -> save. Windows-only in practice."""
    handle.openfemm()
    handle.newdocument(0)  # 0 = magnetics problem
    report = build_sector(handle, cfg)
    handle.mi_saveas(document_path)
    return report
