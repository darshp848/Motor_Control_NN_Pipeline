"""Structural tests for eesm/femm/geometry.py and the config contract.

What these tests CAN prove
--------------------------
That the build emits the calls the physics contract requires: antiperiodic
conditions on two DISTINCT radial edges, four circuits, twelve coil sheets
with the verbatim RMxprt turns signs, a field pair with OPPOSITE signs, the
RMxprt-emitted model depth, and steel on the steel regions.

What they CANNOT prove
----------------------
That the geometry is the real machine. The sector shapes are reconstructed
from RMxprt scalars with no DXF to check against, and the mock accepts
whatever FemmApiConfig says -- so a wrong FEMM boundary code or block-integral
type passes here and can only be caught on Windows. See
eesm/docs/FEMM_MIGRATION.md.

No FEMM licence, installation, or solve is used by any test in this file.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eesm.femm import config as cfg_mod  # noqa: E402
from eesm.femm import geometry  # noqa: E402
from eesm.femm.config import (  # noqa: E402
    BOUNDARY_ANTIPERIODIC_NAME,
    BOUNDARY_OUTER_NAME,
    DEFAULT_CONFIG,
    FIELD_CIRCUIT,
    FIELD_COIL_MAP,
    PHASE_CIRCUITS,
    STATOR_COIL_MAP,
)
from eesm.femm.mock_femm import MockFemm  # noqa: E402


@pytest.fixture()
def built():
    handle = MockFemm()
    report = geometry.build_sector(handle, DEFAULT_CONFIG)
    return handle, report


# ---------------------------------------------------------------------------
# Config contract
# ---------------------------------------------------------------------------


def test_every_config_field_has_provenance():
    """A constant with no documented source is a test failure, not a default."""
    assert cfg_mod.missing_provenance() == ()


def test_known_unknowns_are_flagged_unverified():
    """The values we could not confirm must be flagged, not quietly used."""
    unverified = cfg_mod.unverified_fields()
    for key in ("materials.air_material",      # library name, never read back
                "domain.rs_ohm",               # parameter_status synthetic
                "domain.rf_ohm"):
        assert key in unverified, "%s must be flagged unverified" % key

    # Settled since, and no longer flagged. Each is asserted here so that
    # re-flagging one is a deliberate act rather than a silent regression.
    for key, why in (
        ("geometry.airgap_mm",
         "0.6 mm, read from eesm_pilot_source_01.aedt and matching spec 3"),
        ("geometry.pole_arc_ratio",
         "0.65, frozen by spec 3 and protected by spec 7"),
        ("extraction.d_axis_electrical_deg",
         "150 deg, DERIVED from the winding map, FEMM measures 149.999"),
        ("api.boundary_format_antiperiodic",
         "BdryFormat 5, verified against the shipped FEMM 4.2 manual"),
        ("api.block_integral_torque",
         "type 22, verified against the shipped FEMM 4.2 manual"),
        ("materials.steel_material",
         "steel_1008 BH table extracted verbatim from the pinned revision"),
    ):
        assert key not in unverified, "%s is settled: %s" % (key, why)


def test_d_axis_angle_is_not_inherited_from_the_aedt_model():
    """330.01 deg belongs to the RMxprt-converted model's frame, not ours."""
    assert DEFAULT_CONFIG.extraction.d_axis_electrical_deg != pytest.approx(330.01)


def test_winding_contract_numbers():
    machine = DEFAULT_CONFIG.machine
    assert machine.stator_slots == 24
    assert machine.poles == 4
    assert machine.pole_pairs == 2
    assert machine.sectors == 4
    assert machine.coil_pitch_slots == 6
    assert machine.slots_per_pole_per_phase == 2
    assert machine.conductors_per_slot == 36
    assert machine.conductors_per_sheet == 18
    assert machine.stator_parallel_branches == 4
    assert machine.series_turns_per_phase == 36
    assert machine.field_turns_per_pole == 80
    assert machine.field_parallel_branches == 1
    assert machine.model_depth_m == 0.120


def test_sector_derivations():
    assert cfg_mod.slots_in_sector() == 6
    assert cfg_mod.coil_sheets_in_sector() == 12
    assert cfg_mod.slot_pitch_deg() == pytest.approx(15.0)
    # 4 sheets x 18 conductors = 72 conductors = 36 turns = one branch.
    sheets_per_phase = len(STATOR_COIL_MAP) // len(PHASE_CIRCUITS)
    conductors = sheets_per_phase * DEFAULT_CONFIG.machine.conductors_per_sheet
    assert conductors // 2 == DEFAULT_CONFIG.machine.series_turns_per_phase


def test_airgap_is_consistent_with_the_two_diameters():
    assert cfg_mod.sector_airgap_mm() == pytest.approx(
        DEFAULT_CONFIG.geometry.airgap_mm)


# ---------------------------------------------------------------------------
# Pure geometry
# ---------------------------------------------------------------------------


def test_radii_are_physically_ordered():
    cfg = DEFAULT_CONFIG
    assert (geometry.shaft_radius_mm(cfg)
            < geometry.pole_body_inner_radius_mm(cfg)
            < geometry.pole_shoe_inner_radius_mm(cfg)
            < geometry.rotor_outer_radius_mm(cfg)
            < geometry.stator_bore_radius_mm(cfg)
            < geometry.slot_bottom_radius_mm(cfg)
            < geometry.stator_outer_radius_mm(cfg))


def test_airgap_mid_radius_sits_between_rotor_and_bore():
    cfg = DEFAULT_CONFIG
    mid = geometry.airgap_mid_radius_mm(cfg)
    assert geometry.rotor_outer_radius_mm(cfg) < mid < geometry.stator_bore_radius_mm(cfg)


def test_pole_axis_is_at_the_sector_centre():
    assert geometry.pole_axis_deg() == pytest.approx(45.0)


def test_no_slot_straddles_a_sector_edge():
    """Half-pitch offset: every slot centre is strictly inside the sector."""
    span = DEFAULT_CONFIG.machine.sector_span_deg
    angles = geometry.stator_slot_center_angles_deg()
    assert len(angles) == 6
    assert all(0.0 < angle < span for angle in angles)
    half_pitch = cfg_mod.slot_pitch_deg() / 2.0
    assert angles[0] == pytest.approx(half_pitch)
    assert angles[-1] == pytest.approx(span - half_pitch)


def test_coil_labels_sit_inside_the_slot_body():
    lower, upper = geometry.layer_radii_mm()
    cfg = DEFAULT_CONFIG
    assert geometry.stator_bore_radius_mm(cfg) < lower < upper
    assert upper < geometry.slot_bottom_radius_mm(cfg)


def test_sector_edges_are_two_distinct_edges():
    edges = geometry.sector_edge_endpoints()
    assert len(edges) == 2
    midpoints = []
    for (start, end) in edges.values():
        midpoints.append(((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0))
    assert math.dist(midpoints[0], midpoints[1]) > 1.0


# ---------------------------------------------------------------------------
# Emitted build
# ---------------------------------------------------------------------------


def test_problem_definition_uses_the_contract_depth(built):
    """120 mm active stack, per the frozen geometry spec.

    RMxprt's emitted 77.0793 mm is listed as a defect in
    MAXWELL_EESM_QUALIFICATION.md and was corrected in the r4 rebuild. The
    AEDT pilot anchors still carry it, which is one reason they are not a
    validation target.
    """
    handle, report = built
    assert handle.problem is not None
    assert handle.problem["frequency"] == 0.0  # magnetostatic
    # The report keeps metres, the canonical form used everywhere else.
    assert report.model_depth_m == pytest.approx(0.120)
    assert report.model_depth_m != pytest.approx(0.0770793)


def test_probdef_depth_is_in_problem_units_not_metres(built):
    """The bug of 2026-08-11, third solve.

    mi_probdef takes depth in the PROBLEM'S length units. This passed metres
    while problem_units was "millimeters", so the model was 0.077 mm deep, not
    77.08 mm. Flux linkage is exactly linear in depth in 2-D, so every lambda
    came back 1000x small -- lambda_d = 2.96e-5 Wb against an AEDT anchor of
    0.01281 Wb. The previous version of this test asserted the metres value
    reached FEMM, which pinned the defect in place.
    """
    from eesm.femm import config as cfg_mod
    handle, _report = built
    assert DEFAULT_CONFIG.api.problem_units == "millimeters"
    assert handle.problem["depth"] == pytest.approx(120.0)
    assert handle.problem["depth"] != pytest.approx(
        DEFAULT_CONFIG.machine.model_depth_m)
    # And the conversion must track the units, not hard-code a factor.
    assert cfg_mod.model_depth_in_problem_units(DEFAULT_CONFIG) == \
        pytest.approx(DEFAULT_CONFIG.machine.model_depth_m * 1000.0)


def test_four_circuits_are_created_series_connected(built):
    handle, report = built
    names = [entry["name"] for entry in handle.circuits]
    assert names == list(PHASE_CIRCUITS) + [FIELD_CIRCUIT]
    assert report.circuits == names
    for entry in handle.circuits:
        assert entry["type"] == DEFAULT_CONFIG.api.circuit_type_series
        assert entry["current"] == 0.0


def test_every_radius_band_of_both_edges_is_antiperiodic(built):
    """The bug of 2026-08-11, second solve.

    The drawn section lands arcs on each radial edge at the shaft, hub and
    bore radii, splitting it into four segments. FEMM applies an antiperiodic
    condition to exactly one segment and its partner (manual, Periodic
    Boundary Conditions: "A different periodic condition must be defined for
    each section of the boundary"). Selecting the edge midpoint covered ONE
    band; the other three defaulted to homogeneous Neumann and walled off the
    flux return path. lambda_d came back 432x under the AEDT anchor.

    Every band must carry its own property, on BOTH edges, at distinct points.
    """
    from eesm.femm import geometry, section
    handle, report = built
    # shaft / hub / bore / stator OD / exterior. The stator OD only became an
    # edge once spec 3's 135 mm solution region separated it from the outer
    # boundary; before that there were four.
    bands = section.sector_edge_bands(DEFAULT_CONFIG)
    assert len(bands) == 5

    for index in range(len(bands)):
        name = geometry.antiperiodic_band_name(index)
        segs = [seg for seg in handle.segments if seg["boundary"] == name]
        assert len(segs) == 2, "band %d covers %d segments, need exactly 2" % (
            index, len(segs))
        positions = [seg["position"] for seg in segs]
        assert all(pos is not None for pos in positions)
        assert math.dist(positions[0], positions[1]) > 1.0
        assert name in report.antiperiodic_edges

    # No band may reuse another band's property.
    assigned = [seg["boundary"] for seg in handle.segments
                if seg["boundary"] and seg["boundary"].startswith(
                    BOUNDARY_ANTIPERIODIC_NAME)]
    assert len(assigned) == 2 * len(bands)
    assert len(set(assigned)) == len(bands)


def test_antiperiodic_boundary_uses_the_configured_format(built):
    from eesm.femm import geometry, section
    handle, _ = built
    by_name = {entry["name"]: entry for entry in handle.boundary_props}
    for index in range(len(section.sector_edge_bands(DEFAULT_CONFIG))):
        assert by_name[geometry.antiperiodic_band_name(index)]["format"] == \
            DEFAULT_CONFIG.api.boundary_format_antiperiodic
    assert by_name[BOUNDARY_OUTER_NAME]["format"] == \
        DEFAULT_CONFIG.api.boundary_format_prescribed_a


def test_twelve_coil_sheets_with_verbatim_rmxprt_signs(built):
    handle, report = built
    assert len(report.coil_sheets) == 12
    assert sorted(report.coil_sheets) == sorted(
        name for name, _circuit, _sign in STATOR_COIL_MAP)

    coil_blocks = [b for b in handle.blocks
                   if b["group"] == DEFAULT_CONFIG.api.group_stator_coils]
    assert len(coil_blocks) == 12
    turns_per_sheet = DEFAULT_CONFIG.machine.conductors_per_sheet
    for block in coil_blocks:
        assert abs(block["turns"]) == turns_per_sheet

    expected_sign = {"PhaseA": +1.0, "PhaseB": +1.0, "PhaseC": -1.0}
    by_circuit = {}
    for block in coil_blocks:
        by_circuit.setdefault(block["circuit"], []).append(block["turns"])
    for circuit, turns in by_circuit.items():
        assert len(turns) == 4, "%s must have 4 sheets in the sector" % circuit
        # Same sign for every sheet of a phase: the return conductors are in
        # the adjacent sector and antiperiodicity supplies their inversion.
        assert len(set(math.copysign(1.0, t) for t in turns)) == 1
        assert math.copysign(1.0, turns[0]) == expected_sign[circuit]


def test_field_pair_carries_opposite_signs(built):
    """NOT the stator rule: both field bundles are inside the sector, so they
    are a genuine go/return pair. Same-sign here cancels the pole MMF."""
    handle, report = built
    assert len(report.field_coils) == 2
    field_blocks = [b for b in handle.blocks
                    if b["group"] == DEFAULT_CONFIG.api.group_field_coils]
    assert len(field_blocks) == 2
    turns = sorted(block["turns"] for block in field_blocks)
    expected = DEFAULT_CONFIG.machine.field_turns_per_pole
    assert turns == [-expected, expected]
    assert sum(turns) == 0
    assert all(block["circuit"] == FIELD_CIRCUIT for block in field_blocks)
    assert sorted(name for name, _sign in FIELD_COIL_MAP) == sorted(report.field_coils)


def test_field_bundles_flank_the_pole_body(built):
    """They must sit on opposite sides of the pole axis, not on top of it."""
    labels = geometry.field_coil_labels()
    axis = math.radians(geometry.pole_axis_deg())
    # Signed distance across the pole axis.
    across = [-entry["x"] * math.sin(axis) + entry["y"] * math.cos(axis)
              for entry in labels]
    assert across[0] > 0.0 > across[1]
    assert across[0] == pytest.approx(-across[1])


def test_steel_is_assigned_to_the_steel_regions_and_flagged_placeholder(built):
    handle, report = built
    steel = DEFAULT_CONFIG.materials.steel_material
    assert steel in handle.materials
    steel_groups = {block["group"] for block in handle.blocks
                    if block["material"] == steel}
    assert DEFAULT_CONFIG.api.group_stator_steel in steel_groups
    assert DEFAULT_CONFIG.api.group_rotor_steel in steel_groups
    # No longer a placeholder: the BH table is the spec's own pinned revision,
    # extracted from the AEDT material block. The report must say so, and this
    # assertion flips back the moment anyone reflags the material.
    assert report.steel_is_placeholder is False


def test_expected_material_regions_are_present(built):
    _handle, report = built
    for name in ("shaft", "rotor_steel", "air", "stator_steel"):
        assert name in report.material_regions


def test_the_section_is_actually_drawn(built):
    """The defect of 2026-08-11: labels placed into regions that never existed.

    The old build emitted five concentric arcs and two radial edges, then
    placed twenty labels as though slots, teeth, poles and winding cavities
    were there. FEMM refused the first real solve with "Material properties
    have not been defined for all regions". This asserts the curves exist.
    """
    _handle, report = built
    for feature in ("shaft_arc", "hub_arc_low", "hub_arc_high",
                    "pole_body_sides", "pole_shoe_inner_arcs",
                    "pole_shoe_end_faces", "pole_shoe_arc",
                    "field_coil_cavities", "bore_arc_segments",
                    "stator_slots", "outer_arc"):
        assert feature in report.section_features


def test_outer_dirichlet_lands_on_the_arc_not_a_slot_wall(built):
    """The bug of 2026-08-12.

    The outer boundary is an ARC. mi_selectsegment only ever selects LINES
    (manual: "Select the line segment closest to (x,y)"), and it was being
    called at the arc's CHORD midpoint (45, 45) -- r = 63.64 mm at 45 deg,
    not on the arc at all. The nearest line is a wall of stator slot 2,
    5.39 mm away, so a prescribed A = 0 boundary was pinned onto one slot wall
    beside phase C while the outer arc got nothing.

    That broke mirror symmetry about the pole axis and was invisible both to a
    geometry mirror check (a BC is not a drawn primitive) and to mesh
    refinement (lambda_C held to 4 digits over a 20x element sweep).
    """
    from eesm.femm import geometry
    handle, _report = built
    cfg = DEFAULT_CONFIG
    outer = (cfg.geometry.stator_outer_diameter_mm / 2.0
             * cfg.geometry.outer_boundary_scale)

    # The Dirichlet must be an ARC property, and no line may carry it.
    arc_bcs = [a for a in handle.arc_segments
               if a["boundary"] == BOUNDARY_OUTER_NAME]
    assert len(arc_bcs) == 1
    line_bcs = [s for s in handle.segments
                if s["boundary"] == BOUNDARY_OUTER_NAME]
    assert line_bcs == [], "outer Dirichlet leaked onto a line segment"

    # And the selection point must lie ON the arc, not on its chord.
    x, y = arc_bcs[0]["position"]
    assert math.hypot(x, y) == pytest.approx(outer)


def test_pole_shoe_has_constant_radial_thickness(built):
    """The shoe was first a circular segment of the rotor OD -- 5 mm thick on
    the pole axis, tapering to nothing at the tips. Iron that thin carries no
    flux, so only the middle of the pole face was active and lambda_d came out
    0.59x the AEDT anchor at equal ampere-turns with the iron unsaturated."""
    from eesm.femm import section
    cfg = DEFAULT_CONFIG
    r_od = cfg.geometry.rotor_outer_diameter_mm / 2.0
    r_in = section.pole_shoe_inner_radius_mm(cfg)
    # Spec 3: shoe spans radius 49.0 to 54.4, i.e. 5.4 mm thick everywhere.
    assert r_in == pytest.approx(49.0)
    assert r_od - r_in == pytest.approx(5.4)
    # Span comes from the spec's pole-arc RATIO, not from a chord width.
    assert section.shoe_half_angle_deg(cfg) == pytest.approx(58.5 / 2.0)
    # The field window is bounded by ARCS (spec 3.2: "radial span: radius 36.0
    # to 47.0"), so every point of it is at radius <= 47 and it cannot punch
    # through the shoe. Read as a rectangle instead, its outer corner lands at
    # radius 49.98 and does.
    _, r_out, _, t_out = section.field_coil_extent_mm(cfg)
    assert r_out < r_in
    assert math.hypot(r_out, t_out) > r_in, (
        "the rectangle reading really would collide -- this is why the arc "
        "reading is the right one")


def test_every_block_label_is_uniquely_placed(built):
    """No two labels may share a point -- the cheapest offline proxy for
    'no two labels share a region'. True enclosure can only be proven by a
    solve, which the mock cannot fake; see test_femm_smoke_windows.py."""
    handle, _report = built
    points = [(round(block["position"][0], 9), round(block["position"][1], 9))
              for block in handle.blocks]
    assert len(points) == len(set(points))
    # 5 non-winding regions + 12 coil sheets + 2 field bundles. The fifth is
    # exterior_air, which exists only because spec 3 puts the solution region
    # at 135 mm past the 90 mm stator OD.
    assert len(points) == 19


def test_slot_mouths_leave_the_bore_arc_open(built):
    """Slot openings must not be sealed by a continuous bore arc: the mouth
    air, wedge air, interpolar air and airgap are one region on purpose."""
    from eesm.femm import config as cfg_mod, section
    handle, _report = built
    bore = DEFAULT_CONFIG.geometry.stator_inner_diameter_mm / 2.0
    bore_arcs = [call for call in handle.calls_named("mi_drawarc")
                 if abs(math.hypot(call.args[0], call.args[1]) - bore) < 1e-6]
    # One arc before the first mouth, one between each adjacent pair, one after
    # the last: slots + 1 segments, never a single unbroken circle.
    assert len(bore_arcs) == cfg_mod.slots_in_sector(DEFAULT_CONFIG) + 1
    assert section.slot_opening_half_angle_deg(DEFAULT_CONFIG) > 0.0


def test_build_never_imports_femm():
    """The package must stay importable on Linux: no top-level femm import."""
    import eesm.femm.geometry as module
    source = open(module.__file__, "r", encoding="utf-8").read()
    assert "\nimport femm" not in source
    assert "\nfrom femm" not in source
