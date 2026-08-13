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


def shoe_half_angle_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Angular half-span of the pole shoe, FROM THE SPEC'S POLE-ARC RATIO.

    Spec section 3: "Pole-arc ratio 0.65", "Pole-shoe angular span 58.5
    mechanical degrees" -- and 0.65 x 90 deg pole pitch = 58.5, so the two
    lines agree. Section 7 then protects it: "not change air gap, POLE ARC,
    slot count, current domains, or material to meet the limit."

    Derived from the ratio rather than from a chord width. RMxprt's
    PoleShoeWidth = 45 mm gives 48.86 deg (ratio 0.543) and does not implement
    the spec; the spec's 0.65 needs a 53.2 mm chord.

    A distributed winding senses the FUNDAMENTAL, so the flux effect is
    B_1 = (4/pi) B_g sin(alpha pi / 2), i.e. sin(58.5)/sin(48.86) = 1.132 --
    not the 58.5/48.86 = 1.197 that linear-in-arc reasoning suggests.
    """
    return cfg.geometry.pole_arc_ratio * cfg.machine.sector_span_deg / 2.0


def shoe_half_chord_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Half-chord implied by the spec's pole arc, at the rotor OD."""
    r_od = cfg.geometry.rotor_outer_diameter_mm / 2.0
    return r_od * math.sin(math.radians(shoe_half_angle_deg(cfg)))


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
    """Spec 3: "Rotor hub outer radius 34.0" -- the pole body starts here."""
    return cfg.geometry.rotor_hub_outer_radius_mm


def pole_shoe_inner_radius_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Spec 3: pole body spans 34.0 to 49.0, shoe spans 49.0 to 54.4."""
    return cfg.geometry.pole_body_outer_radius_mm


def slot_opening_half_angle_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    bore = cfg.geometry.stator_inner_diameter_mm / 2.0
    return math.degrees(math.asin((cfg.geometry.slot_opening_width_mm / 2.0) / bore))


def slot_profile_mm(cfg: FemmConfig = DEFAULT_CONFIG
                    ) -> List[Tuple[float, float]]:
    """(radial, half_width) breakpoints of the slot, bore outward.

    Spec 3.1, a PARALLEL-SIDED OPEN SLOT: a 2.0 mm opening for the first
    1.5 mm of depth, then a step out to a constant 7.0 mm body running a
    further 18.5 mm, 20.0 mm total. Note the repeated radius -- the step at
    the tooth tip is a real horizontal edge, not a taper.

    RMxprt's slot is a different shape: tapered 3.0 -> 5.0 -> 7.0 over
    0.8 + 1.2 + 15.0 = 17.0 mm. It is shallower, wider-mouthed, and not
    parallel-sided.
    """
    geo = cfg.geometry
    bore = geo.stator_inner_diameter_mm / 2.0
    r_tip = bore + geo.slot_tooth_tip_depth_mm
    r_bottom = r_tip + geo.slot_body_depth_mm
    return [
        (bore, geo.slot_opening_width_mm / 2.0),
        (r_tip, geo.slot_opening_width_mm / 2.0),
        (r_tip, geo.slot_body_width_mm / 2.0),
        (r_bottom, geo.slot_body_width_mm / 2.0),
    ]


def slot_split_radial_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> Tuple[float, float]:
    """Mid-body radial position separating the two coil sheets, and its half-width."""
    profile = slot_profile_mm(cfg)
    (r_top, hw_top), (r_bottom, hw_bottom) = profile[2], profile[3]
    return (r_top + r_bottom) / 2.0, (hw_top + hw_bottom) / 2.0


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
    radii = [
        0.0,
        geo.shaft_diameter_mm / 2.0,
        pole_body_inner_radius_mm(cfg),
    ]
    if geo.use_sliding_band:
        radii.extend(sliding_band_radii_mm(cfg))
    radii.extend([
        geo.stator_inner_diameter_mm / 2.0,
        # The stator OD. Only an edge once the exterior region exists: with
        # outer_boundary_scale = 1.0 the outer arc WAS the stator OD, so this
        # was the same radius as the next entry. Spec 3 puts the solution
        # region at 135 mm, which separates them and adds a fifth band.
        geo.stator_outer_diameter_mm / 2.0,
        geo.stator_outer_diameter_mm / 2.0 * geo.outer_boundary_scale,
    ])
    return radii


def sector_edge_bands(cfg: FemmConfig = DEFAULT_CONFIG
                      ) -> List[Tuple[float, float]]:
    """Meshed (inner, outer) pairs of a sector edge.

    The unmeshed sliding-band span is omitted so it is not given an
    antiperiodic line property. Type-7 plus <No Mesh> owns that interval.
    """
    radii = sector_edge_split_radii_mm(cfg)
    band = sliding_band_radii_mm(cfg)
    return [
        pair for pair in zip(radii[:-1], radii[1:])
        if pair != band
    ]


def sliding_band_radii_mm(cfg: FemmConfig = DEFAULT_CONFIG
                          ) -> Tuple[float, float]:
    """Inner and outer radii of FEMM's unmeshed sliding band (2:3:2)."""
    rotor = cfg.geometry.rotor_outer_diameter_mm / 2.0
    bore = cfg.geometry.stator_inner_diameter_mm / 2.0
    physical_gap = bore - rotor
    band_thickness = (
        physical_gap * cfg.geometry.sliding_band_thickness_fraction
    )
    side_air = (physical_gap - band_thickness) / 2.0
    return rotor + side_air, bore - side_air


def field_coil_extent_mm(cfg: FemmConfig = DEFAULT_CONFIG
                         ) -> Tuple[float, float, float, float]:
    """(radial_inner, radial_outer, tangential_inner, tangential_outer)."""
    geo = cfg.geometry
    # Spec 3.2 gives the window outright: "coil window radial span: radius
    # 36.0 to 47.0 mm; coil window tangential width per side of pole body:
    # 7.0 mm". The previous version invented an 8.0 mm width and derived the
    # radial extent from a clearance guess.
    inner_t = geo.pole_body_width_mm / 2.0
    return (geo.field_coil_inner_radius_mm, geo.field_coil_outer_radius_mm,
            inner_t, inner_t + geo.field_coil_width_mm)


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

    air_angle = (axis - shoe_half_angle_deg(cfg)) / 2.0
    rotor_od = geo.rotor_outer_diameter_mm / 2.0
    entries = [
        ("shaft", shaft_r / 2.0, axis,
         cfg.materials.steel_material, cfg.api.group_shaft),
        ("rotor_steel", (shaft_r + hub_r) / 2.0, axis,
         cfg.materials.steel_material, cfg.api.group_rotor_steel),
    ]
    if geo.use_sliding_band:
        band_inner, band_outer = sliding_band_radii_mm(cfg)
        entries.extend([
            ("rotor_air", (rotor_od + band_inner) / 2.0, air_angle,
             cfg.materials.air_material, cfg.api.group_airgap),
            ("stator_air", (band_outer + bore) / 2.0, air_angle,
             cfg.materials.air_material, cfg.api.group_airgap),
            ("sliding_band", 0.5 * (band_inner + band_outer), axis,
             cfg_mod.NO_MESH_BLOCK, 0),
        ])
    else:
        entries.append(
            ("air", (bore + rotor_od) / 2.0, air_angle,
             cfg.materials.air_material, cfg.api.group_airgap),
        )
    entries.append(
        ("stator_steel", (slot_bottom + outer) / 2.0, axis,
         cfg.materials.steel_material, cfg.api.group_stator_steel),
    )
    # Spec 3 puts the solution region at 135 mm, past the 90 mm stator OD, so
    # there is an exterior air annulus that needs its own label. With
    # outer_boundary_scale = 1.0 there is no such region and no label.
    exterior = outer * cfg.geometry.outer_boundary_scale
    if exterior - outer > 1e-9:
        entries.append(("exterior_air", (outer + exterior) / 2.0, axis,
                        cfg.materials.air_material, cfg.api.group_airgap))
    labels: List[Dict[str, Any]] = []
    for name, radius, angle, material, group in entries:
        x, y = polar_to_xy(radius, angle)
        label = {"name": name, "material": material,
                 "x": x, "y": y, "group": group}
        # Constrain the connected machine-air region. Do not apply the same
        # small elements to the 90--135 mm exterior annulus.
        if name in ("air", "rotor_air", "stator_air"):
            label["mesh_size_mm"] = geo.airgap_mm * cfg.api.airgap_mesh_fraction
        labels.append(label)
    return labels


# ---------------------------------------------------------------------------
# The drawing
# ---------------------------------------------------------------------------


def _arc(handle: Any, radius: float, angle_from: float, angle_to: float,
         max_seg_deg: float) -> None:
    x0, y0 = polar_to_xy(radius, angle_from)
    x1, y1 = polar_to_xy(radius, angle_to)
    handle.mi_drawarc(x0, y0, x1, y1, angle_to - angle_from, max_seg_deg)


def draw_section(handle: Any, cfg: FemmConfig = DEFAULT_CONFIG,
                 origin_deg: float = 0.0) -> List[str]:
    """Emit every curve of one 90 deg sector starting at origin_deg."""
    geo = cfg.geometry
    span = cfg.machine.sector_span_deg
    axis = origin_deg + span / 2.0
    max_seg = cfg.api.problem_min_angle_deg
    drawn: List[str] = []

    shaft_r = geo.shaft_diameter_mm / 2.0
    hub_r = pole_body_inner_radius_mm(cfg)
    shoe_flat_r = pole_shoe_inner_radius_mm(cfg)
    rotor_od = geo.rotor_outer_diameter_mm / 2.0
    bore = geo.stator_inner_diameter_mm / 2.0
    outer = geo.stator_outer_diameter_mm / 2.0 * geo.outer_boundary_scale

    # -- shaft boundary ----------------------------------------------------
    _arc(handle, shaft_r, origin_deg, origin_deg + span, max_seg)
    drawn.append("shaft_arc")

    # -- rotor hub, drawn only between the pole feet ------------------------
    foot_half = pole_body_foot_half_angle_deg(cfg)
    _arc(handle, hub_r, origin_deg, axis - foot_half, max_seg)
    _arc(handle, hub_r, axis + foot_half, origin_deg + span, max_seg)
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

    if geo.use_sliding_band:
        band_inner, band_outer = sliding_band_radii_mm(cfg)
        _arc(handle, band_inner, origin_deg, origin_deg + span, max_seg)
        _arc(handle, band_outer, origin_deg, origin_deg + span, max_seg)
        drawn.append("sliding_band_arcs")

    # -- field coil windows -------------------------------------------------
    # Spec 3.2 says "coil window RADIAL SPAN: RADIUS 36.0 to 47.0 mm", so the
    # window is bounded by ARCS at those radii, not by straight lines at
    # constant along-axis distance. Read the other way it is a rectangle whose
    # outer corner sits at radius 49.98 and punches through the pole shoe's
    # inner surface at 49.0.
    #
    # The inner tangential boundary is the pole body side, already drawn.
    r_in, r_out, t_in, t_out = field_coil_extent_mm(cfg)
    for sign in (-1.0, +1.0):
        for radius in (r_in, r_out):
            a_in = math.degrees(math.asin(min(t_in / radius, 1.0)))
            a_out = math.degrees(math.asin(min(t_out / radius, 1.0)))
            lo, hi = sorted((axis + sign * a_in, axis + sign * a_out))
            _arc(handle, radius, lo, hi, max_seg)
        # Outer tangential side, spanning the two arcs.
        x0, y0 = offset_polar_to_xy(
            math.sqrt(max(r_in * r_in - t_out * t_out, 0.0)), sign * t_out, axis)
        x1, y1 = offset_polar_to_xy(
            math.sqrt(max(r_out * r_out - t_out * t_out, 0.0)), sign * t_out, axis)
        handle.mi_drawline(x0, y0, x1, y1)
    drawn.append("field_coil_cavities")

    # -- stator bore, in segments between slot mouths -----------------------
    slot_angles = [origin_deg + (index + 0.5) * cfg_mod.slot_pitch_deg(cfg)
                   for index in range(cfg_mod.slots_in_sector(cfg))]
    mouth_half = slot_opening_half_angle_deg(cfg)
    cursor = origin_deg
    for angle in slot_angles:
        _arc(handle, bore, cursor, angle - mouth_half, max_seg)
        cursor = angle + mouth_half
    _arc(handle, bore, cursor, origin_deg + span, max_seg)
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
        # Throat: closes the opening off from the coil body. It spans ONLY the
        # opening width -- the tooth-tip steps either side of it are already
        # drawn by the profile loop above, and a full-width line here would lie
        # on top of them.
        wx0, wy0 = offset_polar_to_xy(profile[1][0], -profile[1][1], angle)
        wx1, wy1 = offset_polar_to_xy(profile[1][0], +profile[1][1], angle)
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

    # -- stator OD, then the exterior boundary ------------------------------
    # The stator OD needs its own arc now that the solution region extends
    # past it (spec 3: exterior radius 135.0). Without it the stator iron and
    # the exterior air are ONE region and whichever label lands there decides
    # the material for both.
    stator_od = geo.stator_outer_diameter_mm / 2.0
    if abs(outer - stator_od) > 1e-9:
        _arc(handle, stator_od, origin_deg, origin_deg + span, max_seg)
        drawn.append("stator_od_arc")

    _arc(handle, outer, origin_deg, origin_deg + span, max_seg)
    drawn.append("outer_arc")

    return drawn
