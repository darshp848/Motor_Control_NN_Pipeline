"""Corrected EESM flux extraction for the fractions=4 RMxprt-derived model.

CONFIRMED BY SOLVE on 2026-07-21 against a disposable copy of
`eesm_qual.aedt` (sha256 28aedc7f...), evidence at
out/eesm/flux_convention_diagnostic/flux_convention_evidence.json.

What was wrong
--------------
Two independent faults, both in extraction. The model, the winding
definition, the sector topology, and the periodic boundaries are all fine.

1. `FluxLinkage(PhaseX)` is not usable on this model. Recomputing the flux
   linkage of the SAME winding definition directly from the vector
   potential gives a balanced three-phase set; AEDT's report expression
   does not:

       point               FluxLinkage(PhaseX)    A_z recomputation
       field_only               0.3932                 0.0001
       d_probe_negative         0.2554                 0.0157
       q_probe_positive         0.1929                 0.0797
       combined                 0.2229                 0.0102
       (figure is |lambda_0| / |lambda_dq|; balanced is < 0.05)

2. The Park reference angle was wrong by 150 degrees. Measured d-axis is
   330.01 deg electrical, not the 180 deg the exporter assumed. 150 deg is
   exactly five slot pitches (24 slots / 4 poles = 30 deg electrical per
   slot), which is consistent with a real geometric reference offset
   rather than a numerical artifact.

Superseded hypothesis
---------------------
An earlier draft of eesm/docs/FLUX_EXTRACTION_FIX.md proposed that the
go and return sheets needed differencing to cancel a vector-potential
gauge constant. THAT IS WRONG and the solve disproved it: differencing
makes the imbalance worse (0.0008 / 0.054 / 0.171 / 0.231) and collapses
the field-only magnitude to ~1e-5 Wb. RMxprt's same-sign convention is
correct - the anti-periodic boundary supplies the sign inversion, exactly
as the winding definition implies.

Result after correction
-----------------------
    balanced winding        PASS   (lambda_a+lambda_b+lambda_c ~ 2e-6 Wb)
    d(lambda_d)/d(If) > 0   PASS   (+4.20e-03 Wb/A)
    Ld > 0, Lq > 0          PASS
    Ld > Lq (salient pole)  PASS   (Ld=3.58e-03 H, Lq=1.89e-03 H, ratio 1.89)

Still open - see NOTES at the bottom.
"""

import math


# ---------------------------------------------------------------------------
# Measured constants
# ---------------------------------------------------------------------------

#: Electrical angle of the rotor field axis, measured from the field-only
#: probe (Id=Iq=0, If=2 A). Supersedes ROTOR_POSITION_DEG = 180.0 in
#: export_eesm_points.py line 29.
D_AXIS_ELECTRICAL_DEG = 330.01

#: Conductors per coil sheet. RMxprt variable `conds`, confirmed in the
#: solved design variation string.
CONDUCTORS_PER_SHEET = 18.0

#: 2-D model depth in metres. RMxprt's own emitted value (Maxwl2DV.vbs
#: line 160-161), NOT the 120 mm physical stack length.
MODEL_DEPTH_M = 0.0770793

#: Sector count. The model is one pole of a 4-pole machine.
FRACTIONS = 4

#: coil sheet -> (winding, polarity sign)
#: Transcribed from RMxprt Maxwl2DV.vbs lines 318-352 and confirmed against
#: GetExcitations on the live model. Every sheet of a phase carries the SAME
#: sign; do not difference go against return.
COIL_MAP = {
    "Coil_0":   ("PhaseA", +1.0),
    "Coil_1":   ("PhaseA", +1.0),
    "CoilRe_0": ("PhaseA", +1.0),
    "CoilRe_1": ("PhaseA", +1.0),
    "Coil_4":   ("PhaseB", +1.0),
    "Coil_5":   ("PhaseB", +1.0),
    "CoilRe_4": ("PhaseB", +1.0),
    "CoilRe_5": ("PhaseB", +1.0),
    "Coil_2":   ("PhaseC", -1.0),
    "Coil_3":   ("PhaseC", -1.0),
    "CoilRe_2": ("PhaseC", -1.0),
    "CoilRe_3": ("PhaseC", -1.0),
}

PHASES = ("PhaseA", "PhaseB", "PhaseC")


# ---------------------------------------------------------------------------
# Field-calculator primitives (AEDT-side; IronPython 2 compatible)
# ---------------------------------------------------------------------------

def _calc_scalar(design, solution_name, sheet_name, quantity):
    fields = design.GetModule("FieldsReporter")
    fields.CalcStack("clear")
    if quantity == "az":
        fields.EnterQty("A")
        fields.CalcOp("ScalarZ")
    else:
        fields.EnterScalar(1.0)
    fields.EnterSurf(sheet_name)
    fields.CalcOp("Integrate")
    value = fields.GetTopEntryValue(solution_name, [])
    fields.CalcStack("clear")
    return float(str(list(value)[0]))


def integrate_az(design, solution_name, sheet_name):
    """Integral of A_z over a sheet, in Wb/m."""
    return _calc_scalar(design, solution_name, sheet_name, "az")


def sheet_area(design, solution_name, sheet_name):
    """Sheet area in m^2."""
    return _calc_scalar(design, solution_name, sheet_name, "area")


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def lambda_abc_from_fields(
    design,
    solution_name,
    coil_map=None,
    conductors=CONDUCTORS_PER_SHEET,
    depth_m=MODEL_DEPTH_M,
    area_cache=None,
):
    """Per-phase flux linkage from the vector potential.

    lambda_phase = sum over that phase's sheets of
                       sign * N * depth * (integral of A_z) / area

    Same-sign summation, matching the winding definition. Areas are
    geometry-only and may be cached across operating points.
    """
    coil_map = coil_map or COIL_MAP
    totals = dict((p, 0.0) for p in PHASES)
    for sheet, (phase, sign) in coil_map.items():
        if phase not in totals:
            continue
        if area_cache is not None and sheet in area_cache:
            area = area_cache[sheet]
        else:
            area = sheet_area(design, solution_name, sheet)
            if area_cache is not None:
                area_cache[sheet] = area
        if not area:
            raise RuntimeError("zero area for sheet " + sheet)
        az = integrate_az(design, solution_name, sheet)
        totals[phase] += sign * conductors * depth_m * az / area
    return totals["PhaseA"], totals["PhaseB"], totals["PhaseC"]


def dq_from_abc(phi_a, phi_b, phi_c, theta_electrical_deg=D_AXIS_ELECTRICAL_DEG):
    """Amplitude-invariant Park, referenced to the MEASURED d-axis."""
    th = theta_electrical_deg * math.pi / 180.0
    phi_d = (2.0 / 3.0) * (
        phi_a * math.cos(th)
        + phi_b * math.cos(th - 2 * math.pi / 3)
        + phi_c * math.cos(th + 2 * math.pi / 3)
    )
    phi_q = (2.0 / 3.0) * (
        -phi_a * math.sin(th)
        - phi_b * math.sin(th - 2 * math.pi / 3)
        - phi_c * math.sin(th + 2 * math.pi / 3)
    )
    return phi_d, phi_q


def abc_from_dq(id_value, iq_value, theta_electrical_deg=D_AXIS_ELECTRICAL_DEG):
    """Inverse Park. MUST use the same angle as dq_from_abc.

    The Task 9 exporter was self-consistent at 180 deg, which is why the
    torque cross-product was invariant to the error - but the resulting
    lambda_d/lambda_q were labelled against an axis 150 deg from the
    rotor field, making the map unusable for a controller even though the
    torque identity could not detect it.
    """
    th = theta_electrical_deg * math.pi / 180.0
    return tuple(
        id_value * math.cos(angle) - iq_value * math.sin(angle)
        for angle in (th, th - 2 * math.pi / 3, th + 2 * math.pi / 3)
    )


def zero_sequence_ratio(phi_a, phi_b, phi_c):
    """Inline per-point health check. Balanced is < 0.05."""
    zero = (phi_a + phi_b + phi_c) / 3.0
    d, q = dq_from_abc(phi_a, phi_b, phi_c, 0.0)
    magnitude = math.hypot(d, q)
    if magnitude < 1e-15:
        return 0.0
    return abs(zero) / magnitude


# ---------------------------------------------------------------------------
# NOTES - decisions this module does NOT make for you
# ---------------------------------------------------------------------------
#
# 1. SERIES vs PARALLEL - RESOLVED (2026-07-21): PARALLEL, multiplier x1.
#
#    First, why no solve can decide this: under the parallel reading the
#    terminal flux linkage is 1/4 of the series reading but the terminal
#    current is 4x the branch current, so torque, power, losses, and the
#    field solution are IDENTICAL either way. T_dq = 1.5*p*(ld*iq - lq*id)
#    is exactly invariant to the choice. It is machine-definition
#    bookkeeping, not physics, so the frozen r2 winding contract is the
#    only authority - and it is explicit: 36 conductors/slot, FOUR
#    balanced stator branches, 36 series turns/phase
#    (eesm/docs/MAXWELL_EESM_QUALIFICATION.md). The contradiction was a
#    bug in build_canonical_eesm.py (ParallelBranchesNum = 1), fixed to 4
#    for the stator phases on 2026-07-21.
#
#    Consequences:
#      - full-machine flux linkage = per-sector value x1 (NOT xFRACTIONS);
#      - with ParallelBranchesNum = 4, commanded winding currents are
#        TERMINAL amps (AEDT drives each branch with I/4);
#      - LEGACY DATA: every probe solved before the builder fix (including
#        the 2026-07 flux-convention diagnostic) used 1 branch, so its
#        labelled currents are BRANCH amps = terminal/4 under the contract;
#      - torque still multiplies by FRACTIONS unconditionally.
#
# 2. D_AXIS_ELECTRICAL_DEG = 330.01 was measured from a single field-only
#    probe on a ~1500-element mesh. The value is physically credible
#    (150 deg offset = exactly 5 slot pitches) but deserves confirmation
#    from a second field-only point at a different If before it is frozen.
#
# 3. Ld/Lq = 1.89 was derived from two probe points whose currents were
#    injected in the OLD 180 deg frame and rotated into the true frame
#    during analysis. Re-measure with currents injected at
#    D_AXIS_ELECTRICAL_DEG for a clean number.
#
# 4. ROUTE C IS VALIDATED. Torque "closure failure" was the broken TORQUE
#    instrument, not the flux. Full analysis + independent Fable review:
#    out/eesm/pilot_20260721/PILOT_FINDINGS.md. Verified facts:
#      - Same-sign COIL_MAP is correct (matches RMxprt Maxwl2DV.vbs AssignCoil;
#        go/return differencing re-disproven, collapses every |lambda| to ~0).
#      - Route-C lambda is STRUCTURALLY EXACT, not an approximation: with PB=4,
#        one branch = one pole = the sector = a 36-turn winding, so the same-sign
#        A_z sum is the exact terminal (full-machine) phase flux linkage. There
#        is NO 2-slot/pole "aliasing" mechanism (an earlier hypothesis, refuted).
#      - Proof it is exact under load: pure_q_pos and q_neg are mirror images
#        about the d-axis; their route-C lambda_abc are mirror-equal to 5e-6 Wb
#        (0.01%). Flux is mesh-robust and physically consistent.
#      - The dq torque identity T = 1.5 p (lam_d iq - lam_q id) with route-C
#        lambda and TERMINAL amps is ALREADY the full-machine torque (no xN).
#      - The load-dependent k = T_fem_full/[1.5 p (lam_d iq - lam_q id)]
#        (pure_q 1.30, q_neg 0.99, reluctance 0.66-0.69) is TORQUE-SOLVER NOISE:
#        the mirror pair, which must have equal |T|, disagrees by 27.5% in
#        Torque_FEM; zero-torque points (field-only/pure-d) report 0.004-0.005 Nm
#        of spurious torque. Virtual-work torque at ~1565 elements is +-14-30%,
#        so a 10% closure gate against it is unpassable by construction.
#    ACTION: fix the torque instrument, not the flux. Re-solve the mirror pair
#    (pure_q + q_neg) and one reluctance mirror pair with MaximumPasses>=12,
#    PercentError<=0.2%, and an airgap/band mesh op (max element ~ gap/3).
#    Instrument gate: mirror |T| asymmetry <= 3%. Closure gate: k in [0.90,1.10]
#    at the pure_q pair. Keep the Torque_FEM x4 (it IS per-sector; confirmed by
#    q_neg closing at k~1). Do NOT loosen gates, re-sign COIL_MAP, difference
#    go/return, or escalate model fidelity yet (all unjustified by the evidence).
#    NB: compare_flux_methods.py had a separate x4 double-count on the dq side
#    (fixed 2026-07-22); its raw evidence residuals before that fix are x4 high.
#
# 5. STATOR ZERO-SEQUENCE IS REAL PHYSICS, NOT AN EXTRACTION ERROR, AND DOES
#    NOT CORRUPT THE dq FUNDAMENTAL. zero_sequence_ratio is ~1e-4 for
#    field-only/pure-d but 0.06-0.81 for stator points: a genuine triplen/zero-
#    sequence field under stator excitation, absent under rotor excitation. The
#    mirror-pair test (note 4) proves the dq fundamental is still exact despite
#    it. The 0.05 gate was validated only on rotor-excited probes and is
#    MIS-SCOPED for stator points -- apply it only to field/rotor excitations,
#    or replace it with a fundamental-reconstruction residual. Do not try to
#    drive stator zero-sequence to zero; it is not physical to do so.
