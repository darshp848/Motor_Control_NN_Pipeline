"""Draw the EESM cross-section: the curves, not just the labels.

Why this module exists
----------------------
`geometry.build_sector()` originally emitted five concentric arcs and the two
radial sector edges, then placed twenty block labels as though slots, teeth,
poles and winding cavities existed. They did not. FEMM rejected the first real
solve with "Material properties have not been defined for all regions", because
three rotor labels with disagreeing materials landed in one undivided annulus
and twelve coil labels landed in another.

The offline mock could not catch it: it records calls and returns closed-form
flux, so label bookkeeping was assertable and topology was not.

This module draws the section so that every block label sits in its own
enclosed region.

Region inventory (one label each, 18 total)
-------------------------------------------
  1  shaft            r < shaft_radius
  2  rotor_steel      hub annulus + pole body + pole shoe, all connected steel
  3  air              interpolar space + airgap + slot mouths + wedges, all
                      one connected air region
  4  stator_steel     bore .. outer, minus the slots
  5  12 coil sheets   two per slot, split at mid-body
  6  2 field coils    rectangles flanking the pole body

Shape decisions not pinned by config
------------------------------------
  - The pole shoe is treated as a CIRCULAR SEGMENT of the rotor OD circle,
    defined by pole_shoe_height_mm. Its implied half-chord is
    sqrt(r_od^2 - (r_od - h)^2) = 22.78 mm against the configured
    pole_shoe_width_mm / 2 = 22.5 mm -- consistent to 1.2%. Height is used as
    primary because deriving the chord from it puts the shoe corners exactly on
    the OD circle and avoids a sub-0.2 mm sliver that would wreck the mesh.
  - `field_coil_width_mm` is NEW and UNVERIFIED. Nothing in the RMxprt scalars
    fixes the field bundle footprint; only its 2 mm clearance from the pole
    body is given.
  - Slot mouths are left OPEN to the airgap, so slot-opening air, wedge air,
    interpolar air and the airgap are one region. They are all air, so a single
    label is correct and no artificial barrier is introduced across the mouth.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

from . import config as cfg_mod
from .config import DEFAULT_CONFIG, FemmConfig


# ---------------------------------------------------------------------------
# Derived shape geometry (pure, offline-testable)
# ---------------------------------------------------------------------------


def polar_to_xy(radius_mm: float, angle_deg: float) -> Tuple[float, float]:
    angle = math.radians(angle_deg)
    return radius_mm * math.cos(angle), radius_mm * math.sin(angle)


def offset_polar_to_xy(radial_mm: float, tangential_mm: float,
                       axis_deg: float) -> Tuple[float, float]:
    angle = math.radians(axis_deg)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    return (radial_mm * cos_a - tangential_mm * sin_a,
            radial_mm * sin_a + tangential_mm * cos_a)


def shoe_half_chord_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Half-chord of the pole shoe: pole_shoe_width_mm / 2, as configured."""
    return cfg.geometry.pole_shoe_width_mm / 2.0


def shoe_half_angle_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Angular half-span of the pole shoe at the rotor OD.

    CORRECTED 2026-08-11. The shoe was first built as a CIRCULAR SEGMENT of
    the rotor OD circle, cut at (r_od - pole_shoe_height). That gives a
    wedge-shaped shoe: 5 mm thick on the pole axis, tapering to nothing at the
    tips. Iron that thin carries no flux, so only the middle of the pole face
    was active -- FEMM measured average B_r under the pole of 0.0511 T against
    0.1313 T at the centre, a ratio of 0.39, and lambda_d came out 0.59x the
    AEDT anchor at equal ampere-turns even though the iron was unsaturated
    (mu_r 2400-3900) and 104% of the MMF was crossing the airgap.

    A salient-pole shoe has roughly CONSTANT radial thickness across its
    width: outer surface on the rotor OD arc, inner surface a concentric arc
    pole_shoe_height below it. The span comes from the configured width.
    """
    r_od = cfg.geometry.rotor_outer_diameter_mm / 2.0
    return math.degrees(math.asin(min(shoe_half_chord_mm(cfg) / r_od, 1.0)))


def pole_body_shoe_junction_half_angle_deg(cfg: FemmConfig = DEFAULT_CONFIG
                                           ) -> float:
    """Where the pole body's straight sides meet the shoe's inner arc."""
    r_inner = pole_shoe_inner_radius_mm(cfg)
    return math.degrees(math.asin(min(
        (cfg.geometry.pole_body_width_mm / 2.0) / r_inner, 1.0)))


def pole_body_shoe_junction_radial_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    r_inner = pole_shoe_inner_radius_mm(cfg)
    half_width = cfg.geometry.pole_body_width_mm / 2.0
    return math.sqrt(max(r_inner * r_inner - half_width * half_width, 0.0))


def pole_body_foot_radial_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Along-axis distance where a pole-body side meets the hub circle."""
    hub = pole_body_inner_radius_mm(cfg)
    half_width = cfg.geometry.pole_body_width_mm / 2.0
    return math.sqrt(max(hub * hub - half_width * half_width, 0.0))


def pole_body_foot_half_angle_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return math.degrees(math.atan2(cfg.geometry.pole_body_width_mm / 2.0,
                                   pole_body_foot_radial_mm(cfg)))


def pole_body_inner_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    r_od = cfg.geometry.rotor_outer_diameter_mm / 2.0
    return r_od - cfg.geometry.pole_shoe_height_mm - cfg.geometry.pole_body_height_mm


def pole_shoe_inner_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    return (cfg.geometry.rotor_outer_diameter_mm / 2.0
            - cfg.geometry.pole_shoe_height_mm)


def slot_opening_half_angle_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    bore = cfg.geometry.stator_inner_diameter_mm / 2.0
    return math.degrees(math.asin((cfg.geometry.slot_opening_width_mm / 2.0) / bore))


def slot_profile_mm(cfg: FemmConfig = DEFAULT_CONFIG
                    ) -> List[Tuple[float, float]]:
    """(radial, half_width) breakpoints of the slot, bore outward."""
    geo = cfg.geometry
    bore = geo.stator_inner_diameter_mm / 2.0
    r_open = bore + geo.slot_opening_height_mm
    r_wedge = r_open + geo.slot_wedge_height_mm
    r_bottom = r_wedge + geo.slot_body_height_mm
    return [
        (bore, geo.slot_opening_width_mm / 2.0),
        (r_open, geo.slot_opening_width_mm / 2.0),
        (r_wedge, geo.slot_wedge_width_mm / 2.0),
        (r_bottom, geo.slot_body_width_mm / 2.0),
    ]


def slot_split_radial_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> Tuple[float, float]:
    """Mid-body radial position separating the two coil sheets, and its half-width."""
    profile = slot_profile_mm(cfg)
    (r_wedge, hw_wedge), (r_bottom, hw_bottom) = profile[2], profile[3]
    r_mid = (r_wedge + r_bottom) / 2.0
    hw_mid = (hw_wedge + hw_bottom) / 2.0
    return r_mid, hw_mid


def sector_edge_split_radii_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> List[float]:
    """Radii at which a drawn arc lands on a radial sector edge, and so splits it.

    FEMM 4.2 manual, Periodic Boundary Conditions: "Often, a periodic boundary
    is made up of several different line or arc segments. A DIFFERENT periodic
    condition must be defined for each section of the boundary, since each
    periodic BC can only be applied to a line or arc and a corresponding
    [one]." Anything left unassigned falls back to homogeneous Neumann, which
    walls off the flux return path instead of continuing it.

    Only arcs that reach 0 deg and sector_span_deg split the edges: the shaft
    arc, the two hub arcs, the first and last bore segments, and the outer arc.
    The pole shoe arc spans 20.2-69.8 deg and does not touch either edge.
    """
    geo = cfg.geometry
    return [
        0.0,
        geo.shaft_diameter_mm / 2.0,
        pole_body_inner_radius_mm(cfg),
        geo.stator_inner_diameter_mm / 2.0,
        geo.stator_outer_diameter_mm / 2.0 * geo.outer_boundary_scale,
    ]


def sector_edge_bands(cfg: FemmConfig = DEFAULT_CONFIG
                      ) -> List[Tuple[float, float]]:
    """Consecutive (inner, outer) radius pairs of the split sector edge."""
    radii = sector_edge_split_radii_mm(cfg)
    return [(radii[index], radii[index + 1]) for index in range(len(radii) - 1)]


def field_coil_extent_mm(cfg: FemmConfig = DEFAULT_CONFIG
                         ) -> Tuple[float, float, float, float]:
    """(radial_inner, radial_outer, tangential_inner, tangential_outer)."""
    geo = cfg.geometry
    inner_t = geo.pole_body_width_mm / 2.0 + geo.field_winding_clearance_mm
    outer_t = inner_t + geo.field_coil_width_mm
    # The shoe's inner surface is now a concentric arc, so the bundle's outer
    # top corner is the binding constraint: keep it a clearance below.
    r_inner = pole_shoe_inner_radius_mm(cfg)
    radial_out = (math.sqrt(max(r_inner * r_inner - outer_t * outer_t, 0.0))
                  - geo.field_winding_clearance_mm)
    return (pole_body_inner_radius_mm(cfg), radial_out, inner_t, outer_t)


# ---------------------------------------------------------------------------
# Region labels -- exactly one per enclosed region
# ---------------------------------------------------------------------------


def section_region_labels(cfg: FemmConfig = DEFAULT_CONFIG
                          ) -> List[Dict[str, Any]]:
    """The four non-winding regions the drawn section actually encloses."""
    geo = cfg.geometry
    axis = cfg.machine.sector_span_deg / 2.0
    shaft_r = geo.shaft_diameter_mm / 2.0
    hub_r = pole_body_inner_radius_mm(cfg)
    bore = geo.stator_inner_diameter_mm / 2.0
    slot_bottom = slot_profile_mm(cfg)[3][0]
    outer = geo.stator_outer_diameter_mm / 2.0

    # Air probe: an angle clear of the pole shoe, at airgap radius.
    air_angle = (axis - shoe_half_angle_deg(cfg)) / 2.0
    air_radius = (bore + geo.rotor_outer_diameter_mm / 2.0) / 2.0

    entries = [
        ("shaft", shaft_r / 2.0, axis,
         cfg.materials.steel_material, cfg.api.group_shaft),
        ("rotor_steel", (shaft_r + hub_r) / 2.0, axis,
         cfg.materials.steel_material, cfg.api.group_rotor_steel),
        ("air", air_radius, air_angle,
         cfg.materials.air_material, cfg.api.group_airgap),
        ("stator_steel", (slot_bottom + outer) / 2.0, axis,
         cfg.materials.steel_material, cfg.api.group_stator_steel),
    ]
    labels: List[Dict[str, Any]] = []
    for name, radius, angle, material, group in entries:
        x, y = polar_to_xy(radius, angle)
        labels.append({"name": name, "material": material,
                       "x": x, "y": y, "group": group})
    return labels


# ---------------------------------------------------------------------------
# The drawing
# ---------------------------------------------------------------------------


def _arc(handle: Any, radius: float, angle_from: float, angle_to: float,
         max_seg_deg: float) -> None:
    x0, y0 = polar_to_xy(radius, angle_from)
    x1, y1 = polar_to_xy(radius, angle_to)
    handle.mi_drawarc(x0, y0, x1, y1, angle_to - angle_from, max_seg_deg)


def draw_section(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG) -> List[str]:
    """Emit every curve of the cross-section. Returns the feature names drawn."""
    geo = cfg.geometry
    span = cfg.machine.sector_span_deg
    axis = span / 2.0
    max_seg = cfg.api.problem_min_angle_deg
    drawn: List[str] = []

    shaft_r = geo.shaft_diameter_mm / 2.0
    hub_r = pole_body_inner_radius_mm(cfg)
    shoe_flat_r = pole_shoe_inner_radius_mm(cfg)
    rotor_od = geo.rotor_outer_diameter_mm / 2.0
    bore = geo.stator_inner_diameter_mm / 2.0
    outer = geo.stator_outer_diameter_mm / 2.0 * geo.outer_boundary_scale

    # -- shaft boundary ----------------------------------------------------
    _arc(handle, shaft_r, 0.0, span, max_seg)
    drawn.append("shaft_arc")

    # -- rotor hub, drawn only between the pole feet ------------------------
    foot_half = pole_body_foot_half_angle_deg(cfg)
    _arc(handle, hub_r, 0.0, axis - foot_half, max_seg)
    _arc(handle, hub_r, axis + foot_half, span, max_seg)
    drawn.append("hub_arc_low")
    drawn.append("hub_arc_high")

    # -- pole body sides, up to the shoe's inner arc ------------------------
    body_half_w = geo.pole_body_width_mm / 2.0
    foot_radial = pole_body_foot_radial_mm(cfg)
    junction_radial = pole_body_shoe_junction_radial_mm(cfg)
    for sign in (-1.0, +1.0):
        x0, y0 = offset_polar_to_xy(foot_radial, sign * body_half_w, axis)
        x1, y1 = offset_polar_to_xy(junction_radial, sign * body_half_w, axis)
        handle.mi_drawline(x0, y0, x1, y1)
    drawn.append("pole_body_sides")

    # -- pole shoe of CONSTANT radial thickness -----------------------------
    # Outer surface on the rotor OD arc, inner surface a concentric arc
    # pole_shoe_height below it, closed by two end faces. The inner arc is
    # drawn only either side of the body: between the junctions it is interior
    # steel where body meets shoe.
    shoe_half = shoe_half_angle_deg(cfg)
    junction_half = pole_body_shoe_junction_half_angle_deg(cfg)
    _arc(handle, shoe_flat_r, axis - shoe_half, axis - junction_half, max_seg)
    _arc(handle, shoe_flat_r, axis + junction_half, axis + shoe_half, max_seg)
    drawn.append("pole_shoe_inner_arcs")

    for sign in (-1.0, +1.0):
        angle = axis + sign * shoe_half
        x0, y0 = polar_to_xy(shoe_flat_r, angle)
        x1, y1 = polar_to_xy(rotor_od, angle)
        handle.mi_drawline(x0, y0, x1, y1)
    drawn.append("pole_shoe_end_faces")

    _arc(handle, rotor_od, axis - shoe_half, axis + shoe_half, max_seg)
    drawn.append("pole_shoe_arc")

    # -- field coil rectangles ---------------------------------------------
    r_in, r_out, t_in, t_out = field_coil_extent_mm(cfg)
    for sign in (-1.0, +1.0):
        corners = [
            (r_in, sign * t_in), (r_in, sign * t_out),     # bottom
            (r_in, sign * t_out), (r_out, sign * t_out),   # outer side
            (r_in, sign * t_in), (r_out, sign * t_in),     # inner side
            (r_out, sign * t_in), (r_out, sign * t_out),   # top
        ]
        for index in range(0, len(corners), 2):
            (ra, ta), (rb, tb) = corners[index], corners[index + 1]
            x0, y0 = offset_polar_to_xy(ra, ta, axis)
            x1, y1 = offset_polar_to_xy(rb, tb, axis)
            handle.mi_drawline(x0, y0, x1, y1)
    drawn.append("field_coil_cavities")

    # -- stator bore, in segments between slot mouths -----------------------
    slot_angles = [(index + 0.5) * cfg_mod.slot_pitch_deg(cfg)
                   for index in range(cfg_mod.slots_in_sector(cfg))]
    mouth_half = slot_opening_half_angle_deg(cfg)
    cursor = 0.0
    for angle in slot_angles:
        _arc(handle, bore, cursor, angle - mouth_half, max_seg)
        cursor = angle + mouth_half
    _arc(handle, bore, cursor, span, max_seg)
    drawn.append("bore_arc_segments")

    # -- slots --------------------------------------------------------------
    profile = slot_profile_mm(cfg)
    split_r, split_hw = slot_split_radial_mm(cfg)
    for angle in slot_angles:
        # Mouth points sit exactly on the bore circle so no sliver is created.
        for sign in (-1.0, +1.0):
            mx, my = polar_to_xy(bore, angle + sign * mouth_half)
            nx, ny = offset_polar_to_xy(profile[1][0], sign * profile[1][1], angle)
            handle.mi_drawline(mx, my, nx, ny)
            for index in range(1, len(profile) - 1):
                (ra, ha), (rb, hb) = profile[index], profile[index + 1]
                x0, y0 = offset_polar_to_xy(ra, sign * ha, angle)
                x1, y1 = offset_polar_to_xy(rb, sign * hb, angle)
                handle.mi_drawline(x0, y0, x1, y1)
        # Wedge top: separates wedge/mouth air from the lower coil sheet.
        wx0, wy0 = offset_polar_to_xy(profile[2][0], -profile[2][1], angle)
        wx1, wy1 = offset_polar_to_xy(profile[2][0], +profile[2][1], angle)
        handle.mi_drawline(wx0, wy0, wx1, wy1)
        # Mid-body split: lower sheet from upper sheet.
        sx0, sy0 = offset_polar_to_xy(split_r, -split_hw, angle)
        sx1, sy1 = offset_polar_to_xy(split_r, +split_hw, angle)
        handle.mi_drawline(sx0, sy0, sx1, sy1)
        # Slot bottom.
        bx0, by0 = offset_polar_to_xy(profile[3][0], -profile[3][1], angle)
        bx1, by1 = offset_polar_to_xy(profile[3][0], +profile[3][1], angle)
        handle.mi_drawline(bx0, by0, bx1, by1)
    drawn.append("stator_slots")

    # -- outer boundary -----------------------------------------------------
    _arc(handle, outer, 0.0, span, max_seg)
    drawn.append("outer_arc")

    return drawn
