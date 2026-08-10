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

    #: 2-D model depth in metres.
    model_depth_m: float = 0.0770793


@dataclass(frozen=True)
class GeometryConfig:
    """Sector geometry in millimetres (FEMM's native unit for this model).

    Every dimension is an RMxprt scalar transcribed from
    eesm/aedt/build_canonical_eesm.py. There is no DXF or native geometry to
    check the reconstructed SHAPES against -- see the geometry_reconstruction
    provenance note, which is the highest-risk assumption in this package.
    """

    stator_outer_diameter_mm: float = 180.0
    stator_inner_diameter_mm: float = 110.0

    #: Stator slot profile (RMxprt Hs0/Hs1/Hs2, Bs0/Bs1/Bs2).
    slot_opening_height_mm: float = 0.8      # Hs0
    slot_wedge_height_mm: float = 1.2        # Hs1
    slot_body_height_mm: float = 15.0        # Hs2
    slot_opening_width_mm: float = 3.0       # Bs0
    slot_wedge_width_mm: float = 5.0         # Bs1
    slot_body_width_mm: float = 7.0          # Bs2

    rotor_outer_diameter_mm: float = 108.8
    shaft_diameter_mm: float = 40.0

    pole_body_height_mm: float = 25.0
    pole_body_width_mm: float = 20.0
    pole_shoe_height_mm: float = 5.0
    pole_shoe_width_mm: float = 45.0
    field_winding_clearance_mm: float = 2.0

    #: Radial airgap = (stator_id - rotor_od) / 2 = (110 - 108.8) / 2.
    #: UNVERIFIED: RMxprt DiaGap also appeared as 109.4 mm in other VBS
    #: blocks, which would give 0.3 mm. Confirm against the real geometry
    #: before any production run.
    airgap_mm: float = 0.6

    #: Outer air boundary radius, as a multiple of the stator outer radius.
    outer_boundary_scale: float = 1.0


@dataclass(frozen=True)
class MaterialConfig:
    """Material assignment. The steel is a documented PLACEHOLDER.

    The real BH curve has not been supplied. Until it is, every nonlinear
    result from this package is qualitative. Points the manifest would label
    'saturation' are physically meaningless with a placeholder curve.
    """

    #: FEMM material-library name for the nonlinear laminated steel.
    #: PLACEHOLDER pending the real BH curve.
    steel_material: str = "M-19 Steel"
    air_material: str = "Air"
    coil_material: str = "Copper"

    #: Lamination stacking factor and thickness are RMxprt defaults, not
    #: measured values.
    lamination_stacking_factor: float = 0.95
    lamination_thickness_mm: float = 0.5


# ---------------------------------------------------------------------------
# Winding map -- verbatim from RMxprt Maxwl2DV.vbs AssignCoil
# ---------------------------------------------------------------------------

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
    d_axis_electrical_deg: float = 0.0

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
    t_rated_nm: float = 80.0
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
    boundary_format_prescribed_a: int = 0

    #: mi_addcircprop(name, current, circuittype): 0=parallel, 1=series.
    #: SERIES is correct here: the turns are in series within one branch.
    circuit_type_series: int = 1

    #: mo_blockintegral(type). FEMM 4.2 manual, "Block Integrals":
    #: 22 = steady-state weighted stress tensor torque.
    block_integral_torque: int = 22

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
        _V2,
        note="RMxprt's emitted MODEL_DEPTH_M, NOT the 120 mm physical stack.",
    ),
    # -- geometry -----------------------------------------------------------
    "geometry.stator_outer_diameter_mm": Provenance(_RMXPRT),
    "geometry.stator_inner_diameter_mm": Provenance(
        _RMXPRT,
        unverified=True,
        note="Ties to the airgap ambiguity: DiaGap appeared as 110, 108.8 "
             "and 109.4 mm across VBS blocks.",
    ),
    "geometry.slot_opening_height_mm": Provenance(_RMXPRT, note="Hs0"),
    "geometry.slot_wedge_height_mm": Provenance(_RMXPRT, note="Hs1"),
    "geometry.slot_body_height_mm": Provenance(_RMXPRT, note="Hs2"),
    "geometry.slot_opening_width_mm": Provenance(_RMXPRT, note="Bs0"),
    "geometry.slot_wedge_width_mm": Provenance(_RMXPRT, note="Bs1"),
    "geometry.slot_body_width_mm": Provenance(_RMXPRT, note="Bs2"),
    "geometry.rotor_outer_diameter_mm": Provenance(
        _RMXPRT, unverified=True, note="See stator_inner_diameter_mm."
    ),
    "geometry.shaft_diameter_mm": Provenance(_RMXPRT, note="Rotor inner diameter"),
    "geometry.pole_body_height_mm": Provenance(_RMXPRT),
    "geometry.pole_body_width_mm": Provenance(_RMXPRT),
    "geometry.pole_shoe_height_mm": Provenance(_RMXPRT),
    "geometry.pole_shoe_width_mm": Provenance(_RMXPRT),
    "geometry.field_winding_clearance_mm": Provenance(_RMXPRT),
    "geometry.airgap_mm": Provenance(
        _RMXPRT,
        unverified=True,
        note="(110 - 108.8)/2 = 0.6 mm. RMxprt DiaGap also appeared as "
             "109.4 mm elsewhere, which would give 0.3 mm -- a factor of 2 "
             "on the dominant reluctance. CONFIRM BEFORE ANY PRODUCTION RUN.",
    ),
    "geometry.outer_boundary_scale": Provenance(
        "modelling choice",
        note="Stator OD is the model boundary; no external air region.",
    ),
    # -- materials ----------------------------------------------------------
    "materials.steel_material": Provenance(
        "PLACEHOLDER",
        unverified=True,
        note="Real BH curve not supplied. M-19 is a documented stand-in. "
             "Saturation-region results are meaningless until replaced.",
    ),
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
        "construction of geometry.build_sector()",
        unverified=True,
        note="Deliberately NOT the AEDT model's 330.01 deg. Needs a "
             "field-only FEMM probe to confirm.",
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
    "domain.t_rated_nm": Provenance(_MANIFEST, unverified=True,
                                    note="parameter_status = synthetic_baseline."),
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
    "api.boundary_format_antiperiodic": Provenance(
        _FEMM_MANUAL, unverified=True,
        note="BdryFormat 5. Recalled, not read back. CONFIRM FIRST on Windows."
    ),
    "api.boundary_format_prescribed_a": Provenance(_FEMM_MANUAL, unverified=True),
    "api.circuit_type_series": Provenance(_FEMM_MANUAL, unverified=True),
    "api.block_integral_torque": Provenance(
        _FEMM_MANUAL, unverified=True,
        note="Type 22 = weighted stress tensor torque. CONFIRM FIRST."
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
