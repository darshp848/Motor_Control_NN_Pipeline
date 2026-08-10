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
    for key in ("geometry.airgap_mm",
                "materials.steel_material",
                "extraction.d_axis_electrical_deg",
                "api.boundary_format_antiperiodic",
                "api.block_integral_torque"):
        assert key in unverified, "%s must be flagged unverified" % key


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
    assert machine.model_depth_m == 0.0770793


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


def test_problem_definition_uses_the_rmxprt_depth(built):
    handle, report = built
    assert handle.problem is not None
    assert handle.problem["depth"] == pytest.approx(0.0770793)
    assert handle.problem["frequency"] == 0.0  # magnetostatic
    assert report.model_depth_m == pytest.approx(0.0770793)


def test_four_circuits_are_created_series_connected(built):
    handle, report = built
    names = [entry["name"] for entry in handle.circuits]
    assert names == list(PHASE_CIRCUITS) + [FIELD_CIRCUIT]
    assert report.circuits == names
    for entry in handle.circuits:
        assert entry["type"] == DEFAULT_CONFIG.api.circuit_type_series
        assert entry["current"] == 0.0


def test_antiperiodic_condition_lands_on_two_distinct_edges(built):
    """The whole point of the sector model. Applying it twice to one edge
    would be a silent modelling failure, so distinctness is asserted."""
    handle, report = built
    antiperiodic = [seg for seg in handle.segments
                    if seg["boundary"] == BOUNDARY_ANTIPERIODIC_NAME]
    assert len(antiperiodic) == 2
    positions = [seg["position"] for seg in antiperiodic]
    assert all(pos is not None for pos in positions)
    assert positions[0] != positions[1]
    assert math.dist(positions[0], positions[1]) > 1.0
    assert len(report.antiperiodic_edges) == 2
    assert len(set(report.antiperiodic_edges)) == 2


def test_antiperiodic_boundary_uses_the_configured_format(built):
    handle, _ = built
    by_name = {entry["name"]: entry for entry in handle.boundary_props}
    assert by_name[BOUNDARY_ANTIPERIODIC_NAME]["format"] == \
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
    # The BH curve is NOT the real one. This must stay visible in the report.
    assert report.steel_is_placeholder is True


def test_expected_material_regions_are_present(built):
    _handle, report = built
    for name in ("stator_yoke", "airgap", "pole_shoe", "pole_body",
                 "interpolar_air", "shaft"):
        assert name in report.material_regions


def test_build_never_imports_femm():
    """The package must stay importable on Linux: no top-level femm import."""
    import eesm.femm.geometry as module
    source = open(module.__file__, "r", encoding="utf-8").read()
    assert "\nimport femm" not in source
    assert "\nfrom femm" not in source
