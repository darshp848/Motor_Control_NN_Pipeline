"""Assert the config against the FROZEN SPEC, line by line, with citations.

    docs/superpowers/specs/2026-07-12-canonical-academic-eesm-geometry-design.md

Why this file exists
--------------------
`GeometryConfig` was originally transcribed from RMxprt scalars in
`eesm/aedt/build_canonical_eesm.py` rather than from the spec those scalars were
supposed to realise. The RMxprt model drifts from the spec, and each drift was
found the expensive way -- by measurement, one at a time, over days:

    model depth       77.0793 mm  vs 120 mm      (flux and torque, linear)
    field turns/pole  20          vs 80          (4x the field MMF)
    pole-arc ratio    0.543       vs 0.65        (1.13x on the fundamental)
    rotor hub radius  24.4 mm     vs 34.0        (3.2x the return-path area)
    slot template     tapered     vs parallel    (different slot entirely)
    field window      invented    vs given       (spec 3.2 defines it)
    exterior region   90 mm       vs 135 mm      (no exterior air at all)

None of these was detectable by a solve alone: the model converged happily and
returned confident wrong numbers. Every one of them was sitting in a document
nobody had diffed against the code.

So this file hardcodes the spec's frozen values with their section references.
The next drift of this kind fails here, immediately, instead of waiting for a
human to re-read two documents side by side.

Rule of precedence, from the spec itself (section 7): "not change air gap, pole
arc, slot count, current domains, or material to meet the limit." Where RMxprt
and the spec disagree, the spec is the contract.
"""
from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from eesm.femm import section                                   # noqa: E402
from eesm.femm.config import DEFAULT_CONFIG as CFG              # noqa: E402

SPEC = ("docs/superpowers/specs/"
        "2026-07-12-canonical-academic-eesm-geometry-design.md")


# --- section 2, rated operating point ------------------------------------

def test_spec_2_rated_point():
    """10 kW continuous at 3000 rpm base speed -> 31.83 N.m base torque."""
    machine = CFG.machine
    domain = CFG.domain
    assert machine.poles == 4
    assert machine.pole_pairs == 2
    assert domain.omega_mech_base_rpm == pytest.approx(3000.0)
    assert domain.i_s_max_peak_a == pytest.approx(120.0)
    assert domain.if_a_max == pytest.approx(15.0)
    assert domain.vdc_v == pytest.approx(400.0)
    # 10 kW / (3000 rpm * 2pi/60). The manifest carried 80.0 until 2026-08-12,
    # a synthetic_baseline placeholder implying 25.1 kW at the same speed.
    assert domain.t_rated_nm == pytest.approx(10_000.0 / (3000.0 * 2 * math.pi / 60), abs=0.01)
    assert domain.t_rated_nm == pytest.approx(31.83, abs=0.01)


# --- section 3, frozen radial geometry -----------------------------------

@pytest.mark.parametrize("field,spec_value,cite", [
    ("stator_outer_diameter_mm", 180.0, "stator outer diameter"),
    ("stator_inner_diameter_mm", 110.0, "stator bore diameter"),
    ("airgap_mm", 0.6, "air gap"),
    ("rotor_outer_diameter_mm", 108.8, "rotor outer diameter"),
    ("shaft_diameter_mm", 40.0, "shaft diameter"),
    ("pole_arc_ratio", 0.65, "pole-arc ratio"),
    ("rotor_hub_outer_radius_mm", 34.0, "rotor hub outer radius"),
    ("pole_body_outer_radius_mm", 49.0, "pole body radial span 34.0 to 49.0"),
    ("pole_body_width_mm", 20.0, "pole body tangential width"),
])
def test_spec_3_frozen_radial_geometry(field, spec_value, cite):
    actual = getattr(CFG.geometry, field)
    assert actual == pytest.approx(spec_value), (
        "%s section 3, '%s' = %s; config has %s" % (SPEC, cite, spec_value, actual))


def test_spec_3_active_stack_length():
    """"Active stack length | 120.0". RMxprt emitted 77.0793 mm; the
    qualification doc calls that a defect and r4 corrected it."""
    assert CFG.machine.model_depth_m == pytest.approx(0.120)


def test_spec_3_pole_shoe_angular_span():
    """"Pole-arc ratio 0.65" and "Pole-shoe angular span 58.5 mechanical
    degrees" -- and 0.65 x 90 deg pole pitch = 58.5, so the two lines agree."""
    assert 2 * section.shoe_half_angle_deg(CFG) == pytest.approx(58.5)
    assert CFG.geometry.pole_arc_ratio * CFG.machine.sector_span_deg == \
        pytest.approx(58.5)


def test_spec_3_pole_shoe_radial_span():
    """"Pole-shoe radial span | radius 49.0 to 54.4"."""
    assert section.pole_shoe_inner_radius_mm(CFG) == pytest.approx(49.0)
    assert CFG.geometry.rotor_outer_diameter_mm / 2.0 == pytest.approx(54.4)


def test_spec_3_exterior_solution_region():
    """"Exterior solution-region radius | 135.0"."""
    outer = (CFG.geometry.stator_outer_diameter_mm / 2.0
             * CFG.geometry.outer_boundary_scale)
    assert outer == pytest.approx(135.0)
    # ...and it must be OUTSIDE the stator OD, or there is no exterior air.
    assert outer > CFG.geometry.stator_outer_diameter_mm / 2.0


# --- section 3.1, stator slot template -----------------------------------

def test_spec_3_1_slot_template():
    """"one parallel-sided open-slot template": 2.0 mm opening, 1.5 mm
    tooth-tip depth, 7.0 mm parallel body, 18.5 mm deep, 20.0 mm total."""
    geo = CFG.geometry
    assert geo.slot_opening_width_mm == pytest.approx(2.0)
    assert geo.slot_tooth_tip_depth_mm == pytest.approx(1.5)
    assert geo.slot_body_width_mm == pytest.approx(7.0)
    assert geo.slot_body_depth_mm == pytest.approx(18.5)
    assert geo.slot_tooth_tip_depth_mm + geo.slot_body_depth_mm == \
        pytest.approx(20.0), "total slot radial depth"

    profile = section.slot_profile_mm(CFG)
    bore = geo.stator_inner_diameter_mm / 2.0
    assert profile[3][0] - bore == pytest.approx(20.0)
    # PARALLEL-SIDED: the body half-width does not change with depth. RMxprt's
    # slot tapers 3.0 -> 5.0 -> 7.0 and is a different slot.
    assert profile[2][1] == pytest.approx(profile[3][1])


def test_spec_3_1_minimum_back_iron():
    """"The resulting minimum stator back iron is 15 mm." A derived check:
    it falls out of the bore, the slot depth and the stator OD, so it catches
    an inconsistent trio that the individual assertions would each pass."""
    geo = CFG.geometry
    slot_bottom = section.slot_profile_mm(CFG)[3][0]
    assert geo.stator_outer_diameter_mm / 2.0 - slot_bottom == pytest.approx(15.0)


def test_spec_3_1_slot_count_and_offset():
    """24 slots, 15 deg pitch, "slot centerlines offset by 7.5 mechanical
    degrees from the +X axis"."""
    from eesm.femm import config as cfg_mod, geometry
    assert CFG.machine.stator_slots == 24
    assert cfg_mod.slot_pitch_deg(CFG) == pytest.approx(15.0)
    assert geometry.stator_slot_center_angles_deg(CFG)[0] == pytest.approx(7.5)


# --- section 3.2, rotor pole and field-coil template ---------------------

def test_spec_3_2_field_coil_window():
    """"coil window radial span: radius 36.0 to 47.0 mm; coil window
    tangential width per side of pole body: 7.0 mm; 80 series turns per pole".

    Note RADIUS: the window is bounded by arcs. Read as a rectangle in the
    pole-axis frame its outer corner lands at radius 49.98 and punches through
    the pole shoe's inner surface at 49.0.
    """
    r_in, r_out, t_in, t_out = section.field_coil_extent_mm(CFG)
    assert r_in == pytest.approx(36.0)
    assert r_out == pytest.approx(47.0)
    assert t_out - t_in == pytest.approx(7.0)
    assert t_in == pytest.approx(CFG.geometry.pole_body_width_mm / 2.0)
    assert CFG.machine.field_turns_per_pole == 80
    assert r_out < section.pole_shoe_inner_radius_mm(CFG)


def test_spec_3_2_no_damper_cage():
    """"No damper cage, permanent magnets, brushless exciter, skew, end turns,
    or axial leakage model is included." The RMxprt seed carried three damper
    bars; nothing in this package may reintroduce them."""
    from eesm.femm import geometry
    from eesm.femm.mock_femm import MockFemm
    handle = MockFemm(cfg=CFG)
    report = geometry.build_sector(handle, CFG)
    names = " ".join(report.section_features + report.material_regions).lower()
    for banned in ("damper", "bar", "magnet"):
        assert banned not in names


# --- section 4, stator winding -------------------------------------------

def test_spec_4_winding_contract():
    """"three-phase, double-layer distributed winding with 24 slots, 4 poles,
    q = 2 slots per pole per phase. Coil pitch is six slots... 36 series turns
    per phase"."""
    machine = CFG.machine
    assert machine.slots_per_pole_per_phase == 2
    assert machine.coil_pitch_slots == 6
    assert machine.series_turns_per_phase == 36
    assert machine.stator_slots // (machine.poles * 3) == 2


# --- section 5, materials -------------------------------------------------

def test_spec_5_lamination_material():
    """Section 5 pins a REVISION, not just a name: matching FEMM's library
    entry called '1008 Steel' would not be automatically the same BH point
    table as 'rmxprt-steel_1008-r1'. The .aedt files are plain text and
    readable without a licence, so the pinned table is EXTRACTED and loaded
    with mi_addmaterial / mi_addbhpoint rather than trusted by name."""
    from eesm.femm import config as cfg_mod
    assert CFG.materials.steel_material == "steel_1008"
    assert CFG.materials.steel_material_revision == "rmxprt-steel_1008-r1"
    assert CFG.materials.steel_material != "M-19 Steel"


def test_spec_5_bh_table_matches_the_pinned_revision():
    """The extracted curve must be the AEDT block's, point for point.

    Spot values are the first, last and knee entries of the Points[38] array
    in the $begin 'steel_1008' block of eesm_pilot_source_01.aedt. A curve
    that silently became a different steel fails here.
    """
    from eesm.femm import config as cfg_mod
    points = cfg_mod.STEEL_1008_BH_POINTS
    assert len(points) == 19, "Points[38] is 19 (H, B) pairs"

    assert points[0] == (0.0, 0.0)
    assert points[1] == pytest.approx((0.2402, 159.2))
    assert points[6] == pytest.approx((1.5, 1591.5))
    assert points[-1] == pytest.approx((2.5851, 397887.0))

    b_values = [b for b, _ in points]
    h_values = [h for _, h in points]
    assert b_values == sorted(b_values), "B must increase monotonically"
    assert h_values == sorted(h_values), "H must increase monotonically"
    # Saturates around 2 T, as a low-carbon steel should.
    assert 2.0 < b_values[-1] < 2.7
    assert CFG.materials.steel_conductivity_ms_per_m == pytest.approx(2.0)


def test_spec_5_steel_is_built_not_looked_up():
    """mi_getmaterial on the steel would reintroduce the substitution that
    section 5 forbids. It must be mi_addmaterial + mi_addbhpoint."""
    from eesm.femm import config as cfg_mod, geometry
    from eesm.femm.mock_femm import MockFemm
    handle = MockFemm(cfg=CFG)
    geometry.define_materials(handle, CFG)

    looked_up = [call.args[0] for call in handle.calls_named("mi_getmaterial")]
    assert CFG.materials.steel_material not in looked_up
    assert set(looked_up) == {CFG.materials.air_material,
                              CFG.materials.coil_material}

    built = [call.args[0] for call in handle.calls_named("mi_addmaterial")]
    assert built == [CFG.materials.steel_material]
    assert handle.bh_points[CFG.materials.steel_material] == \
        [tuple(p) for p in cfg_mod.STEEL_1008_BH_POINTS]