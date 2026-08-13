"""Every geometric, winding, material and FEMM-API constant, in one place.

No other module in eesm/femm/ may contain a magic number. If a value is not
here, it does not exist.

Provenance discipline
---------------------
Every field of every config dataclass MUST have an entry in PROVENANCE,
keyed "section.field". The entry records where the number came from and
whether it is verified. test_femm_geometry.py enforces total coverage, so a
new constant without provenance is a test failure, not a silent assumption.

`unverified=True` means: this number is a placeholder or a transcription
whose ground truth has not been confirmed against the real machine. It is a
FINDING, not a blank that was filled in. Every unverified field is listed in
eesm/docs/FEMM_MIGRATION.md and must be confirmed before any production run.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, Dict, Tuple


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Provenance:
    """Where a constant came from, and whether it is trustworthy."""

    source: str
    unverified: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Machine and winding contract
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MachineConfig:
    """Pole/slot counts and the winding contract. All verified.

    These are the settled physics contract carried over from the qualified
    Maxwell model (eesm/docs/MAXWELL_EESM_QUALIFICATION.md, r2 winding
    contract). They are NOT re-derived here and must not be changed without
    re-qualifying the contract.
    """

    stator_slots: int = 24
    poles: int = 4
    pole_pairs: int = 2
    #: The model is one pole of a 4-pole machine: a 90 deg sector.
    sectors: int = 4
    sector_span_deg: float = 90.0
    coil_pitch_slots: int = 6
    slots_per_pole_per_phase: int = 2

    conductors_per_slot: int = 36
    #: Double-layer lap winding: two coil sheets per slot, 18 conductors each.
    conductors_per_sheet: int = 18
    stator_parallel_branches: int = 4
    series_turns_per_phase: int = 36

    field_turns_per_pole: int = 80
    field_parallel_branches: int = 1

    #: 2-D model depth in metres. THE CONTRACT VALUE, 120 mm.
    #:
    #: Changed 2026-08-12 from 0.0770793. That figure is RMxprt's emitted
    #: ModelDepth, and MAXWELL_EESM_QUALIFICATION.md lists it as a DEFECT --
    #: "Maxwell ModelDepth='77.0793mm', not the frozen 120 mm" -- corrected in
    #: the r4 rebuild. The frozen geometry spec gives an active stack length of
    #: 120 mm, and r9_03 carries 120 mm.
    #:
    #: It was held at 0.0770793 while the AEDT pilot anchors were the reference,
    #: so the comparison stayed like for like. Those anchors come from
    #: eesm_pilot_source_01, which carries the 77.0793 mm defect AND
    #: ConductorsPerPole=40 (20 field turns/pole, against the contract's 80), so
    #: they are not a validation target. Absolute checks against the frozen spec
    #: are, and those need the contract depth.
    #:
    #: Flux linkage and torque are exactly linear in depth, so every extensive
    #: quantity scales by 120 / 77.0793 = 1.55684 relative to earlier runs.
    model_depth_m: float = 0.120


@dataclass(frozen=True)
class GeometryConfig:
    """Sector geometry in millimetres, DERIVED FROM THE FROZEN SPEC.

    Source of every value below:
    docs/superpowers/specs/2026-07-12-canonical-academic-eesm-geometry-design.md
    sections 3, 3.1 and 3.2. Section references are given per field.

    Rebuilt 2026-08-12. These values were previously transcribed from RMxprt
    scalars in eesm/aedt/build_canonical_eesm.py, and the RMxprt implementation
    drifts from the spec it was meant to realise. Six deviations were found by
    measurement before anyone compared the two documents:

        model depth        77.0793 mm   vs spec 120 mm
        field turns/pole   20 (Cond/Pole 40)  vs spec 80
        pole-arc ratio     0.543        vs spec 0.65
        rotor hub radius   24.4 mm      vs spec 34.0
        pole body span     24.4->49.4   vs spec 34.0->49.0
        exterior region    90 mm        vs spec 135 mm

    plus the stator slot template and the field-coil window, corrected here.
    Where RMxprt and the spec disagree, THE SPEC IS THE CONTRACT: it is the
    design document, the RMxprt model is one (defective) implementation of it,
    and spec section 7 forbids changing "air gap, pole arc, slot count, current
    domains, or material" to suit the mesher.
    """

    # -- spec section 3, frozen radial geometry ------------------------------
    stator_outer_diameter_mm: float = 180.0
    stator_inner_diameter_mm: float = 110.0
    rotor_outer_diameter_mm: float = 108.8
    shaft_diameter_mm: float = 40.0

    #: Spec 3: "Radial airgap 0.6". Confirmed against eesm_pilot_source_01.aedt,
    #: whose bore and rotor OD read 110.0 and 108.8. The 0.3 mm alternative,
    #: from a stray DiaGap=109.4 in some VBS blocks, is settled: it is not this
    #: machine.
    airgap_mm: float = 0.6

    #: Spec 3: "Pole-arc ratio 0.65", "Pole-shoe angular span 58.5 mechanical
    #: degrees". The shoe span is DERIVED from this ratio, not from a chord
    #: width -- see section.shoe_half_angle_deg. RMxprt's PoleShoeWidth = 45 mm
    #: gives 48.86 deg and does not implement the spec.
    pole_arc_ratio: float = 0.65

    #: Spec 3: "Rotor hub outer radius 34.0". RMxprt's pole body height of
    #: 25 mm put this at 24.4, leaving a 4.4 mm hub against the spec's 14 mm --
    #: 3.2x less return-path area for the entire pole flux.
    rotor_hub_outer_radius_mm: float = 34.0

    #: Spec 3: "Pole body radial span radius 34.0 to 49.0", tangential width
    #: 20.0. "Pole-shoe radial span radius 49.0 to 54.4."
    pole_body_outer_radius_mm: float = 49.0
    pole_body_width_mm: float = 20.0

    # -- spec section 3.1, stator slot template ------------------------------
    #: "one parallel-sided open-slot template": opening 2.0 mm wide at the bore,
    #: tooth-tip/wedge depth 1.5 mm, then a PARALLEL body 7.0 mm wide and
    #: 18.5 mm deep, 20.0 mm total. RMxprt's tapered Hs0/Hs1/Hs2 = 0.8/1.2/15.0
    #: with Bs0/Bs1/Bs2 = 3.0/5.0/7.0 is a different slot: shallower (17.0 mm),
    #: wider-mouthed (3.0 mm) and tapered rather than parallel.
    slot_opening_width_mm: float = 2.0
    slot_tooth_tip_depth_mm: float = 1.5
    slot_body_width_mm: float = 7.0
    slot_body_depth_mm: float = 18.5

    # -- spec section 3.2, rotor pole and field-coil template ----------------
    #: "coil window radial span: radius 36.0 to 47.0 mm; coil window tangential
    #: width per side of pole body: 7.0 mm". This replaces the invented
    #: field_coil_width_mm = 8.0 and the 2 mm clearance guess: the spec gives
    #: the window outright. Clearance follows as 36.0 - 34.0 = 2.0 mm radially
    #: and (20/2) to the window's inner edge tangentially.
    field_coil_inner_radius_mm: float = 36.0
    field_coil_outer_radius_mm: float = 47.0
    field_coil_width_mm: float = 7.0

    #: Spec 3: "Exterior solution-region radius 135.0", as a multiple of the
    #: stator outer radius: 135 / 90 = 1.5. Was 1.0, which put the Dirichlet
    #: boundary directly on the stator OD with no exterior air at all.
    outer_boundary_scale: float = 1.5

    #: Fraction of the physical radial airgap occupied by FEMM's UNMESHED
    #: sliding band. FEMM's official Antunes.fem rotor-motion example uses a
    #: 0.3 mm band with 0.2 mm of meshed air on either side in a 0.7 mm gap,
    #: i.e. the exact 2:3:2 radial ratio retained here.
    sliding_band_thickness_fraction: float = 3.0 / 7.0

    #: Type-7 band is optional. Default off: a 90° band without a valid
    #: air-gap element refuses to solve. Enable only for an explicit diagnostic.
    use_sliding_band: bool = False

    #: Draw all four poles with no antiperiodic cuts. Used to test whether
    #: the locked-rotor T_even residual is a sector-boundary artifact.
    full_machine: bool = False


@dataclass(frozen=True)
class MaterialConfig:
    """Material assignment. The steel is the SPEC'S OWN BH TABLE.

    Spec section 5 pins a REVISION, not just a name: "AEDT built-in
    `steel_1008`, material revision `rmxprt-steel_1008-r1` ... Do not silently
    substitute another steel. Any substitute requires a new
    `material_revision` and an updated specification."

    Matching FEMM's library entry by name would not satisfy that -- a library
    grade called "1008 Steel" is not automatically the same point table as the
    pinned revision. So the table is not name-matched, it is EXTRACTED: .aedt
    files are plain text and readable without a licence, and
    eesm_pilot_source_01.aedt carries the material block verbatim. The 19
    points below are that block, loaded into FEMM with mi_addmaterial +
    mi_addbhpoint rather than mi_getmaterial.

    That makes the material checkable against the pinned revision instead of
    trusted by name, and it removes the last placeholder from this package.
    """

    #: Name given to the material we BUILD (not a library lookup).
    steel_material: str = "steel_1008"
    #: The pinned revision this table was extracted from.
    steel_material_revision: str = "rmxprt-steel_1008-r1"
    air_material: str = "Air"
    coil_material: str = "Copper"

    #: Bulk conductivity, MS/m. AEDT block: conductivity='2000000' S/m.
    steel_conductivity_ms_per_m: float = 2.0

    #: Lamination stacking factor and thickness are RMxprt defaults, not
    #: measured values.
    lamination_stacking_factor: float = 0.95
    lamination_thickness_mm: float = 0.5


# ---------------------------------------------------------------------------
# Winding map -- verbatim from RMxprt Maxwl2DV.vbs AssignCoil
# ---------------------------------------------------------------------------

#: The steel_1008 BH curve, revision rmxprt-steel_1008-r1, as (B tesla,
#: H A/m) pairs in FEMM's mi_addbhpoint argument order.
#:
#: EXTRACTED VERBATIM 2026-08-12 from the 'BHCoordinates' Points[38] array in
#: the $begin 'steel_1008' block of
#: aedt_mcp/tmp/aedt_projects/eesm_pilot_source_01/eesm_pilot_source_01.aedt
#: (AEDT stores them H-first; the order is swapped here to match FEMM).
#: ModTime=1499970477.
#:
#: This is the spec's own material, not a library grade with a similar name.
STEEL_1008_BH_POINTS: Tuple[Tuple[float, float], ...] = (
    (0.0, 0.0),
    (0.2402, 159.2),
    (0.8654, 318.3),
    (1.1106, 477.5),
    (1.2458, 636.6),
    (1.3310, 795.8),
    (1.5000, 1591.5),
    (1.6000, 3183.1),
    (1.6830, 4774.6),
    (1.7410, 6366.2),
    (1.7800, 7957.7),
    (1.9050, 15915.5),
    (2.0250, 31831.0),
    (2.0850, 47746.5),
    (2.1300, 63662.0),
    (2.1650, 79577.5),
    (2.2800, 159155.0),
    (2.4850, 318310.0),
    (2.5851, 397887.0),
)


#: (coil sheet name, circuit name, polarity sign).
#:
#: Transcribed verbatim from RMxprt Maxwl2DV.vbs AssignCoil and confirmed
#: against GetExcitations on the live AEDT model. Identical to
#: eesm/aedt/flux_extraction_v2.py COIL_MAP.
#:
#: EVERY sheet of a phase carries the SAME sign. This is correct for a
#: one-pole sector model and is not an oversight: a stator coil's return
#: conductors live in the ADJACENT sector, and the antiperiodic boundary
#: supplies the inversion. Go/return differencing was tried on the AEDT model
#: and disproved twice (it collapses every |lambda| to ~1e-5 Wb).
#: See eesm/aedt/flux_extraction_v2.py NOTE 4.
STATOR_COIL_MAP: Tuple[Tuple[str, str, float], ...] = (
    ("Coil_0", "PhaseA", +1.0),
    ("Coil_1", "PhaseA", +1.0),
    ("CoilRe_0", "PhaseA", +1.0),
    ("CoilRe_1", "PhaseA", +1.0),
    ("Coil_2", "PhaseC", -1.0),
    ("Coil_3", "PhaseC", -1.0),
    ("CoilRe_2", "PhaseC", -1.0),
    ("CoilRe_3", "PhaseC", -1.0),
    ("Coil_4", "PhaseB", +1.0),
    ("Coil_5", "PhaseB", +1.0),
    ("CoilRe_4", "PhaseB", +1.0),
    ("CoilRe_5", "PhaseB", +1.0),
)

PHASE_CIRCUITS: Tuple[str, str, str] = ("PhaseA", "PhaseB", "PhaseC")
FIELD_CIRCUIT: str = "Field"

#: (field coil region name, polarity sign).
#:
#: THIS IS NOT THE STATOR RULE. In a one-pole 90 deg sector the field coil's
#: go and return bundles are BOTH inside the model, one on each flank of the
#: pole body. They are a genuine go/return pair and MUST carry opposite turn
#: signs, or the pole MMF cancels instead of adding. The stator same-sign
#: rule does not transfer, because the stator's return conductors are outside
#: the sector and the antiperiodic boundary supplies their inversion.
#:
#: The discriminating check is the SIGN of d(lambda_d)/d(If) (must be > 0)
#: plus the magnitude of per-pole ampere-turns (= field_turns_per_pole * If).
#: The |lambda_q/lambda_d| ratio does NOT discriminate: it survives a sign
#: flip and will look healthy either way.
FIELD_COIL_MAP: Tuple[Tuple[str, float], ...] = (
    ("FieldCoil_Left", +1.0),
    ("FieldCoil_Right", -1.0),
)


# ---------------------------------------------------------------------------
# Extraction conventions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExtractionConfig:
    """dq conventions and the two sector multipliers.

    The two multipliers are DIFFERENT and both are load-bearing:

      flux  x1  -- with 4 parallel stator branches, one branch = one pole =
                   this sector = a 36-turn winding, so the circuit flux
                   linkage FEMM reports is already the terminal
                   (full-machine) phase flux linkage.
      torque x4 -- the block integral covers one sector only.

    A previous script (compare_flux_methods.py, fixed 2026-07-22)
    double-counted a x4 on the dq torque side. test_femm_extract.py has a
    regression test for exactly that bug.
    """

    #: Electrical angle of the rotor d-axis relative to the phase-A magnetic
    #: axis, at rotor_angle_deg = 0.
    #:
    #: UNVERIFIED, and deliberately NOT inherited from the AEDT model.
    #: eesm/aedt/flux_extraction_v2.py carries D_AXIS_ELECTRICAL_DEG = 330.01,
    #: but that number is a property of the RMxprt-CONVERTED model's own
    #: geometric reference frame (the 150 deg offset is exactly five slot
    #: pitches of that conversion). This package BUILDS the geometry, so the
    #: d-axis is fixed by our own construction, and 0.0 is what
    #: geometry.build_sector() intends. It must still be confirmed by a
    #: field-only FEMM probe (Id=Iq=0, If>0) before any production run --
    #: exactly the measurement that produced 330.01 on the AEDT side.
    #: DERIVED, then confirmed. 2026-08-12.
    #:
    #: For a pole at 45 deg the field vector potential is A_z = sin(2*theta -
    #: 90 deg), giving slot values -0.966, -0.707, -0.259, +0.259, +0.707,
    #: +0.966 at 7.5 .. 82.5 deg. With the winding map A(0,1)+, C(2,3)-,
    #: B(4,5)+ that is lambda_abc proportional to (-1, +1, 0) and
    #:
    #:     theta_d = 150 deg exactly
    #:
    #: FEMM measures 149.999 deg, and lambda_C -- which must be exactly zero
    #: because phase C straddles the pole axis -- comes out 2e-7 and shrinks
    #: under mesh refinement.
    #:
    #: The earlier value 139.1253 was measured on a model carrying a misplaced
    #: Dirichlet boundary (see geometry.build_sector). It was an artefact.
    d_axis_electrical_deg: float = 150.0

    #: Terminal flux linkage multiplier. See the class docstring.
    flux_multiplier: float = 1.0
    #: Sector -> full machine torque multiplier.
    torque_sector_multiplier: float = 4.0

    #: Amplitude-invariant Park. Torque identity, full machine, terminal
    #: quantities: T = 1.5 * p * (lambda_d * iq - lambda_q * id).
    torque_identity_constant: float = 1.5

    #: Relative |T_fem - T_identity| above which a point is flagged
    #: 'suspect'. Reporting threshold only -- NOT a promotion gate.
    torque_residual_report_threshold: float = 0.10


# ---------------------------------------------------------------------------
# Operating domain (mirrors eesm/configs/eesm_experiment_manifest.json)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainConfig:
    """Operating domain. Mirrors the manifest; the manifest is authority.

    machine.parameter_status is "synthetic_baseline": these electrical
    parameters are PLACEHOLDERS, not measured values. Do not present any
    result derived from them as validated.
    """

    id_a_min: float = -120.0
    id_a_max: float = 0.0
    iq_a_min: float = 0.0
    iq_a_max: float = 120.0
    if_a_min: float = 0.0
    if_a_max: float = 15.0

    rs_ohm: float = 0.05
    rf_ohm: float = 8.0
    vdc_v: float = 400.0
    i_s_max_peak_a: float = 120.0
    #: 10 kW at 3000 rpm. Tracks the manifest, corrected 2026-08-12 from the
    #: 80.0 synthetic_baseline placeholder.
    t_rated_nm: float = 31.83
    omega_mech_base_rpm: float = 3000.0
    omega_mech_max_rpm: float = 9000.0

    parameter_status: str = "synthetic_baseline"


# ---------------------------------------------------------------------------
# FEMM API constants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FemmApiConfig:
    """Magic integers and enum strings the FEMM 4.2 API expects.

    EVERY value in this class is flagged unverified. They are recalled from
    the FEMM 4.2 manual, not read back from a running FEMM, and this machine
    has no FEMM to check them against. They are the FIRST things to confirm
    on the Windows run -- see eesm/docs/FEMM_MIGRATION.md. The mock accepts
    whatever this class says, so a wrong value here CANNOT be caught offline.
    """

    #: mi_probdef(freq, units, type, precision, depth, minangle, acsolver)
    problem_frequency_hz: float = 0.0        # magnetostatic
    problem_units: str = "millimeters"
    problem_type: str = "planar"
    problem_precision: float = 1.0e-8
    problem_min_angle_deg: float = 30.0

    #: mi_addboundprop(..., BdryFormat, ...). FEMM 4.2 manual, "Boundary
    #: Property": 0=Prescribed A, 1=Small skin depth, 2=Mixed,
    #: 3=Strategic dual image, 4=Periodic, 5=Antiperiodic.
    boundary_format_antiperiodic: int = 5
    boundary_format_antiperiodic_airgap: int = 7
    boundary_format_prescribed_a: int = 0

    #: mi_modifyboundprop(name, propnum, value): 10 = inner angle. The inner
    #: side is the rotor for this inner-rotor machine.
    boundary_parameter_inner_angle: int = 10

    #: mi_addcircprop(name, current, circuittype): 0=parallel, 1=series.
    #: SERIES is correct here: the turns are in series within one branch.
    circuit_type_series: int = 1

    #: mo_blockintegral(type). FEMM 4.2 manual, "Block Integrals":
    #: 22 = steady-state weighted stress tensor torque.
    block_integral_torque: int = 22

    #: mo_gapintegral(boundary, type): 0 = DC torque.
    gap_integral_dc_torque: int = 0

    #: Mesh size hint for the airgap, as a fraction of the radial gap.
    airgap_mesh_fraction: float = 0.3333333333333333

    #: Group numbers used for selection. Arbitrary but must be consistent.
    group_stator_steel: int = 1
    group_rotor_steel: int = 2
    group_airgap: int = 3
    group_shaft: int = 4
    group_stator_coils: int = 5
    group_field_coils: int = 6

    #: Blocks summed for the torque integral (the rotating parts).
    torque_groups: Tuple[int, ...] = (2, 4, 6)


# ---------------------------------------------------------------------------
# Boundary names
# ---------------------------------------------------------------------------

BOUNDARY_ANTIPERIODIC_NAME: str = "SectorAntiperiodic"
BOUNDARY_OUTER_NAME: str = "OuterDirichlet"
BOUNDARY_SLIDING_BAND_NAME: str = "SlidingBand"

#: FEMM's reserved block name for an unmeshed sliding-band annulus.
#: Official sliding-band benchmark: the region between the two air-gap
#: faces is labeled "<No Mesh>", not left unlabeled.
NO_MESH_BLOCK: str = "<No Mesh>"

#: The two radial edges of the 90 deg sector. They are DISTINCT edges; the
#: antiperiodic boundary must be applied to both, and applying it twice to
#: the same edge is a silent modelling failure that the geometry test guards.
SECTOR_EDGE_LOW: str = "sector_edge_low"
SECTOR_EDGE_HIGH: str = "sector_edge_high"


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FemmConfig:
    """The whole contract, as one object passed everywhere."""

    machine: MachineConfig = MachineConfig()
    geometry: GeometryConfig = GeometryConfig()
    materials: MaterialConfig = MaterialConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    domain: DomainConfig = DomainConfig()
    api: FemmApiConfig = FemmApiConfig()


DEFAULT_CONFIG = FemmConfig()


# ---------------------------------------------------------------------------
# Provenance table -- one entry per config field, enforced by test
# ---------------------------------------------------------------------------

#: The frozen geometry spec. Where this and _RMXPRT disagree, THIS WINS: it is
#: the design document and the RMxprt model is one implementation of it, found
#: to drift from it in at least eight places.
_SPEC = ("docs/superpowers/specs/"
         "2026-07-12-canonical-academic-eesm-geometry-design.md")
_RMXPRT = "RMxprt via eesm/aedt/build_canonical_eesm.py"
_CONTRACT = "r2 winding contract, eesm/docs/MAXWELL_EESM_QUALIFICATION.md"
_MANIFEST = "eesm/configs/eesm_experiment_manifest.json"
_FEMM_MANUAL = "FEMM 4.2 manual (build 21Apr2019)"
_V2 = "eesm/aedt/flux_extraction_v2.py"

PROVENANCE: Dict[str, Provenance] = {
    # -- machine ------------------------------------------------------------
    "machine.stator_slots": Provenance(_RMXPRT),
    "machine.poles": Provenance(_RMXPRT),
    "machine.pole_pairs": Provenance(_MANIFEST),
    "machine.sectors": Provenance(_V2, note="FRACTIONS = 4"),
    "machine.sector_span_deg": Provenance(_V2, note="360 / sectors"),
    "machine.coil_pitch_slots": Provenance(_CONTRACT),
    "machine.slots_per_pole_per_phase": Provenance(_CONTRACT),
    "machine.conductors_per_slot": Provenance(_RMXPRT),
    "machine.conductors_per_sheet": Provenance(_V2, note="CONDUCTORS_PER_SHEET"),
    "machine.stator_parallel_branches": Provenance(_CONTRACT),
    "machine.series_turns_per_phase": Provenance(_CONTRACT),
    "machine.field_turns_per_pole": Provenance(_CONTRACT),
    "machine.field_parallel_branches": Provenance(_CONTRACT),
    "machine.model_depth_m": Provenance(
        _CONTRACT,
        note="120 mm active stack, frozen geometry spec section 3. RMxprt's "
             "emitted 77.0793 mm is a defect per MAXWELL_EESM_QUALIFICATION.md "
             "and was corrected in r4; r9_03 carries 120 mm.",
    ),
    # -- geometry -----------------------------------------------------------
    "geometry.stator_outer_diameter_mm": Provenance(_RMXPRT),
    "geometry.stator_inner_diameter_mm": Provenance(
        _SPEC, note="Section 3: stator bore diameter 110.0."),
    "geometry.slot_opening_width_mm": Provenance(
        _SPEC, note="Section 3.1: slot opening at the bore, 2.0 mm."),
    "geometry.slot_tooth_tip_depth_mm": Provenance(
        _SPEC, note="Section 3.1: tooth-tip / wedge radial depth 1.5 mm."),
    "geometry.slot_body_width_mm": Provenance(
        _SPEC, note="Section 3.1: slot body tangential width 7.0 mm, "
                    "parallel-sided."),
    "geometry.slot_body_depth_mm": Provenance(
        _SPEC, note="Section 3.1: 18.5 mm below the tooth tip, 20.0 total, "
                    "leaving the specified 15 mm minimum back iron."),
    "geometry.rotor_outer_diameter_mm": Provenance(
        _SPEC, note="Section 3: rotor outer diameter 108.8."),
    "geometry.shaft_diameter_mm": Provenance(
        _SPEC, note="Section 3: shaft diameter 40.0."),
    "geometry.pole_arc_ratio": Provenance(
        _SPEC, note="Section 3: pole-arc ratio 0.65, span 58.5 mech deg. "
                    "Section 7 forbids changing it to suit the mesher."),
    "geometry.rotor_hub_outer_radius_mm": Provenance(
        _SPEC, note="Section 3: rotor hub outer radius 34.0."),
    "geometry.pole_body_outer_radius_mm": Provenance(
        _SPEC, note="Section 3: pole body spans radius 34.0 to 49.0."),
    "geometry.pole_body_width_mm": Provenance(
        _SPEC, note="Section 3: pole body tangential width 20.0."),
    "geometry.field_coil_inner_radius_mm": Provenance(
        _SPEC, note="Section 3.2: coil window radial span 36.0 to 47.0."),
    "geometry.field_coil_outer_radius_mm": Provenance(_SPEC, note="Section 3.2."),
    "geometry.field_coil_width_mm": Provenance(
        _SPEC, note="Section 3.2: coil window tangential width per side of "
                    "the pole body, 7.0 mm."),
    "geometry.airgap_mm": Provenance(
        _SPEC,
        note="Section 3: air gap 0.6. Settled 2026-08-12 -- "
             "eesm_pilot_source_01.aedt reads bore 110.0 and rotor OD 108.8 "
             "directly, so the 0.3 mm alternative from a stray DiaGap=109.4 "
             "is not this machine.",
    ),
    "geometry.outer_boundary_scale": Provenance(
        "modelling choice",
        note="Stator OD is the model boundary; no external air region.",
    ),
    "geometry.sliding_band_thickness_fraction": Provenance(
        "https://www.femm.info/wiki/RotorMotion and official Antunes.fem",
        note="Official 0.7 mm-gap example uses 0.2 mm meshed air, 0.3 mm "
             "unmeshed band, 0.2 mm meshed air; preserve its 2:3:2 ratio.",
    ),
    "geometry.use_sliding_band": Provenance(
        "https://www.femm.info/wiki/SlidingBandBenchmark",
        note="Default off. Type-7 on this 90 deg sector refused twice "
             "without a working air-gap element.",
    ),
    "geometry.full_machine": Provenance(
        "modelling choice",
        note="360 deg, no antiperiodic cuts. Odd poles flip winding signs "
             "to realise the AP image. Torque x1, flux x1/4.",
    ),
    # -- materials ----------------------------------------------------------
    "materials.steel_material": Provenance(
        _SPEC,
        note="Section 5: steel_1008, revision rmxprt-steel_1008-r1. The BH "
             "table is EXTRACTED verbatim from the material block in "
             "eesm_pilot_source_01.aedt and loaded with mi_addbhpoint, not "
             "name-matched against a FEMM library grade -- section 5 pins a "
             "revision, and a library entry with a similar name is not the "
             "same point table. Was M-19 Steel, a substitution section 5 "
             "explicitly forbids.",
    ),
    "materials.steel_material_revision": Provenance(
        _SPEC, note="Section 5 pins this revision."),
    "materials.steel_conductivity_ms_per_m": Provenance(
        _SPEC, note="AEDT block: conductivity='2000000' S/m = 2 MS/m."),
    "materials.air_material": Provenance(_FEMM_MANUAL, unverified=True,
                                         note="Library name not read back."),
    "materials.coil_material": Provenance(_FEMM_MANUAL, unverified=True,
                                          note="Library name not read back."),
    "materials.lamination_stacking_factor": Provenance(
        "RMxprt default", unverified=True, note="Not measured."
    ),
    "materials.lamination_thickness_mm": Provenance(
        "RMxprt default", unverified=True, note="Not measured."
    ),
    # -- extraction ---------------------------------------------------------
    "extraction.d_axis_electrical_deg": Provenance(
        "derived from STATOR_COIL_MAP, confirmed by a field-only FEMM probe",
        note="150 deg exactly. A_z = sin(2*theta - 90) for a pole at 45 deg "
             "gives lambda_abc proportional to (-1, +1, 0), and phase C -- "
             "which straddles the pole axis -- contributes zero. FEMM "
             "measures 149.999 with lambda_C at 2e-7 and shrinking under "
             "refinement. Not the AEDT model's 330.01 deg, which belongs to "
             "a different winding frame.",
    ),
    "extraction.flux_multiplier": Provenance(_V2, note="NOTE 1: x1, terminal flux."),
    "extraction.torque_sector_multiplier": Provenance(_V2, note="NOTE 1: x4."),
    "extraction.torque_identity_constant": Provenance(
        "amplitude-invariant Park", note="T = 1.5 p (ld iq - lq id)."
    ),
    "extraction.torque_residual_report_threshold": Provenance(
        "reporting choice", note="NOT a gate. Labels rows 'suspect' only."
    ),
    # -- domain -------------------------------------------------------------
    "domain.id_a_min": Provenance(_MANIFEST),
    "domain.id_a_max": Provenance(_MANIFEST),
    "domain.iq_a_min": Provenance(_MANIFEST),
    "domain.iq_a_max": Provenance(_MANIFEST),
    "domain.if_a_min": Provenance(_MANIFEST),
    "domain.if_a_max": Provenance(_MANIFEST),
    "domain.rs_ohm": Provenance(_MANIFEST, unverified=True,
                                note="parameter_status = synthetic_baseline."),
    "domain.rf_ohm": Provenance(_MANIFEST, unverified=True,
                                note="parameter_status = synthetic_baseline."),
    "domain.vdc_v": Provenance(_MANIFEST, unverified=True,
                               note="parameter_status = synthetic_baseline."),
    "domain.i_s_max_peak_a": Provenance(_MANIFEST),
    "domain.t_rated_nm": Provenance(
        _MANIFEST,
        note="10 kW / 3000 rpm = 31.83 N.m, frozen geometry spec section 2. "
             "No longer a synthetic_baseline placeholder: the 80.0 it "
             "replaced implied 25.1 kW and contradicted the spec's rating. "
             "FEMM measures a 57.20 N.m peak over the current domain, so "
             "rated torque sits at 1.80x margin.",
    ),
    "domain.omega_mech_base_rpm": Provenance(_MANIFEST, unverified=True,
                                             note="synthetic_baseline."),
    "domain.omega_mech_max_rpm": Provenance(_MANIFEST, unverified=True,
                                            note="synthetic_baseline."),
    "domain.parameter_status": Provenance(_MANIFEST),
    # -- api ----------------------------------------------------------------
    "api.problem_frequency_hz": Provenance(_FEMM_MANUAL, unverified=True,
                                           note="0 Hz = magnetostatic."),
    "api.problem_units": Provenance(_FEMM_MANUAL, unverified=True),
    "api.problem_type": Provenance(_FEMM_MANUAL, unverified=True),
    "api.problem_precision": Provenance(_FEMM_MANUAL, unverified=True),
    "api.problem_min_angle_deg": Provenance(_FEMM_MANUAL, unverified=True),
    # The four silent-failure enums, all VERIFIED 2026-08-12 against the manual
    # FEMM ships with itself, C:\femm42\bin\manual.pdf. None was wrong.
    "api.boundary_format_antiperiodic": Provenance(
        _FEMM_MANUAL,
        note="BdryFormat 5. Manual, mi_addboundprop: \"For an 'Anti-Perodic' "
             "boundary condition, set BdryFormat to 5\" (sic)."
    ),
    "api.boundary_format_antiperiodic_airgap": Provenance(
        _FEMM_MANUAL,
        note="BdryFormat 7 = Anti-periodic Air Gap; verified against the "
             "installed FEMM 4.2 manual and official Antunes.fem example.",
    ),
    "api.boundary_format_prescribed_a": Provenance(
        _FEMM_MANUAL, note="BdryFormat 0 = Prescribed A."),
    "api.boundary_parameter_inner_angle": Provenance(
        _FEMM_MANUAL,
        note="mi_modifyboundprop propnum 10 sets the Inner Angle.",
    ),
    "api.circuit_type_series": Provenance(
        _FEMM_MANUAL,
        note="Manual, mi_addcircprop: \"0 for a parallel-connected circuit "
             "and 1 for a series-connected circuit\"."),
    "api.block_integral_torque": Provenance(
        _FEMM_MANUAL,
        note="Manual, mo_blockintegral type table: 22 = 'Steady-state "
             "weighted stress tensor torque'."
    ),
    "api.gap_integral_dc_torque": Provenance(
        _FEMM_MANUAL,
        note="Manual, mo_gapintegral type table: 0 = DC torque.",
    ),
    "api.airgap_mesh_fraction": Provenance(
        "eesm/aedt/flux_extraction_v2.py NOTE 4",
        note="max element ~ gap/3, the AEDT remediation recommendation.",
    ),
    "api.group_stator_steel": Provenance("modelling choice"),
    "api.group_rotor_steel": Provenance("modelling choice"),
    "api.group_airgap": Provenance("modelling choice"),
    "api.group_shaft": Provenance("modelling choice"),
    "api.group_stator_coils": Provenance("modelling choice"),
    "api.group_field_coils": Provenance("modelling choice"),
    "api.torque_groups": Provenance(
        "modelling choice",
        note="Rotor steel + shaft + field coils = the rotating assembly.",
    ),
}


def provenance_key(section: str, field_name: str) -> str:
    return "%s.%s" % (section, field_name)


def iter_config_fields(cfg: FemmConfig = DEFAULT_CONFIG):
    """Yield (key, value) for every leaf field of the aggregate config."""
    for section in fields(cfg):
        sub = getattr(cfg, section.name)
        for leaf in fields(sub):
            yield provenance_key(section.name, leaf.name), getattr(sub, leaf.name)


def unverified_fields(cfg: FemmConfig = DEFAULT_CONFIG) -> Dict[str, Provenance]:
    """Every constant that is a placeholder or an unconfirmed transcription."""
    out: Dict[str, Provenance] = {}
    for key, _value in iter_config_fields(cfg):
        entry = PROVENANCE.get(key)
        if entry is not None and entry.unverified:
            out[key] = entry
    return out


def missing_provenance(cfg: FemmConfig = DEFAULT_CONFIG) -> Tuple[str, ...]:
    """Config fields with no PROVENANCE entry. Must always be empty."""
    return tuple(key for key, _ in iter_config_fields(cfg) if key not in PROVENANCE)


# ---------------------------------------------------------------------------
# Derived quantities (still no magic numbers -- all from the fields above)
# ---------------------------------------------------------------------------


#: Metres per one unit of each length unit mi_probdef accepts.
PROBLEM_UNIT_METRES: Dict[str, float] = {
    "inches": 0.0254,
    "millimeters": 1e-3,
    "centimeters": 1e-2,
    "mils": 2.54e-5,
    "meters": 1.0,
    "micrometers": 1e-6,
}


def model_depth_in_problem_units(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Model depth expressed in `api.problem_units`, which is what FEMM wants.

    mi_probdef's depth argument is in the PROBLEM'S length units, not metres.
    The manual does not say so; FEMM's own Problem Definition dialog shows the
    depth field labelled with the selected units.

    Found 2026-08-11: define_problem passed model_depth_m (0.0770793) straight
    into mi_probdef while problem_units was "millimeters", making the model
    0.077 mm deep instead of 77.08 mm. Flux linkage in a 2-D problem is exactly
    linear in depth, so every lambda was 1000x too small. The first solves on
    the drawn section returned lambda_d = 2.96e-5 Wb.
    """
    scale = PROBLEM_UNIT_METRES.get(cfg.api.problem_units)
    if scale is None:
        raise ValueError(
            "Unknown problem_units %r; cannot convert model depth. Known: %s"
            % (cfg.api.problem_units, sorted(PROBLEM_UNIT_METRES))
        )
    return cfg.machine.model_depth_m / scale


def slots_in_sector(cfg: FemmConfig = DEFAULT_CONFIG) -> int:
    """Stator slots inside the one-pole sector: 24 / 4 = 6."""
    return cfg.machine.stator_slots // cfg.machine.sectors


def coil_sheets_in_sector(cfg: FemmConfig = DEFAULT_CONFIG) -> int:
    """Double layer: two sheets per slot."""
    return slots_in_sector(cfg) * (
        cfg.machine.conductors_per_slot // cfg.machine.conductors_per_sheet
    )


def slot_pitch_deg(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Mechanical degrees between adjacent slots."""
    return 360.0 / cfg.machine.stator_slots


def stator_branch_current(terminal_amps: float,
                          cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Terminal amps -> the current one modelled branch (this sector) carries.

    With 4 parallel branches, FEMM must drive each branch with I/4. The
    commanded (id, iq) are always TERMINAL amps.
    """
    return terminal_amps / float(cfg.machine.stator_parallel_branches)


def field_branch_current(field_amps: float,
                         cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """The field winding is NOT parallel-connected: commanded = actual."""
    return field_amps / float(cfg.machine.field_parallel_branches)


def sector_airgap_mm(cfg: FemmConfig = DEFAULT_CONFIG) -> float:
    """Radial airgap implied by the two diameters, for cross-checking."""
    return (cfg.geometry.stator_inner_diameter_mm
            - cfg.geometry.rotor_outer_diameter_mm) / 2.0


def as_provenance_payload(cfg: FemmConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """Serialisable provenance block for status JSON and row metadata."""
    return {
        "config_fields": dict(iter_config_fields(cfg)),
        "unverified": {
            key: {"source": entry.source, "note": entry.note}
            for key, entry in unverified_fields(cfg).items()
        },
    }
