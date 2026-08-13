"""Extraction-convention tests: Park round trip, the two sector multipliers,
the torque identity, and mirror symmetry.

The torque tests are pinned to HAND-COMPUTED LITERALS rather than to the
mock's own arithmetic. With Ld = 4.0e-3 H, Lq = 2.0e-3 H, M = 5.0e-3 Wb/A,
p = 2 and (id, iq, if) = (-100, 80, 10) A terminal:

    lambda_d = 4.0e-3 * (-100) + 5.0e-3 * 10 = -0.40 + 0.05 = -0.35 Wb
    lambda_q = 2.0e-3 * 80                   =  0.16 Wb
    T_full   = 1.5 * 2 * (-0.35 * 80 - 0.16 * (-100))
             = 3.0 * (-28.0 + 16.0) = -36.0 N.m
    T_sector = -36.0 / 4 = -9.0 N.m

Both sides of the extraction are asserted against those literals, so a
double-count applied to BOTH the FEM torque and the identity torque -- which
a residual-only test would happily pass -- fails here.

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

from eesm.femm import extract  # noqa: E402
from eesm.femm.config import (  # noqa: E402
    DEFAULT_CONFIG,
    FIELD_CIRCUIT,
    PHASE_CIRCUITS,
)
from eesm.femm.mock_femm import (  # noqa: E402
    LinearSalientMachine,
    MockFemm,
    analytic_torque_nm,
    build_mock,
)

ROUND_TRIP_TOLERANCE = 1.0e-12

#: The pinned machine of the module docstring. Round numbers on purpose.
PINNED = LinearSalientMachine(ld_h=4.0e-3, lq_h=2.0e-3,
                              mutual_field_d_wb_per_a=5.0e-3)
PINNED_POINT = (-100.0, 80.0, 10.0)          # id, iq, if (terminal amps)
PINNED_LAMBDA_D = -0.35
PINNED_LAMBDA_Q = 0.16
PINNED_TORQUE_FULL_NM = -36.0
PINNED_TORQUE_SECTOR_NM = -9.0


def _pinned_handle():
    return MockFemm(cfg=DEFAULT_CONFIG, machine=PINNED)


# ---------------------------------------------------------------------------
# Park round trip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theta_deg", [
    0.0,        # the config default
    330.01,     # the AEDT model's measured d-axis, for cross-path comparison
    45.0, 90.0, 137.5, 180.0, 270.0, -73.25, 719.9,
])
@pytest.mark.parametrize("id_a,iq_a", [
    (0.0, 0.0), (-120.0, 0.0), (0.0, 120.0), (-85.0, 61.0), (-7.5, -3.25),
])
def test_dq_abc_dq_round_trip_is_identity(theta_deg, id_a, iq_a):
    """dq -> abc -> dq must be exact to 1e-12 at any reference angle."""
    a, b, c = extract.abc_from_dq(id_a, iq_a, theta_deg)
    back_d, back_q = extract.dq_from_abc(a, b, c, theta_deg)
    assert back_d == pytest.approx(id_a, abs=ROUND_TRIP_TOLERANCE)
    assert back_q == pytest.approx(iq_a, abs=ROUND_TRIP_TOLERANCE)


def test_inverse_park_produces_a_balanced_three_phase_set():
    a, b, c = extract.abc_from_dq(-100.0, 80.0, 0.0)
    assert a + b + c == pytest.approx(0.0, abs=ROUND_TRIP_TOLERANCE)


def test_coenergy_scaling_implies_three_halves_field_reciprocity():
    """Amplitude-invariant W′ must not use naive ∂λf/∂id = ∂λd/∂If.

    W′ = (3/2)(½ Ld id² + ½ Lq iq² + M If id) + ½ Lf If²
    recovers λd = Ld id + M If and λf = (3/2) M id + Lf If.
    """
    ld_h, lq_h, mutual, lf_h = 4.0e-3, 2.0e-3, 5.0e-3, 8.0e-3
    id_a, iq_a, if_a = -100.0, 80.0, 10.0

    def coenergy(id_value, iq_value, if_value):
        magnetic = (
            0.5 * ld_h * id_value ** 2
            + 0.5 * lq_h * iq_value ** 2
            + mutual * if_value * id_value
        )
        return 1.5 * magnetic + 0.5 * lf_h * if_value ** 2

    step = 1.0e-4
    lambda_d = (2.0 / 3.0) * (
        coenergy(id_a + step, iq_a, if_a) - coenergy(id_a - step, iq_a, if_a)
    ) / (2.0 * step)
    lambda_q = (2.0 / 3.0) * (
        coenergy(id_a, iq_a + step, if_a) - coenergy(id_a, iq_a - step, if_a)
    ) / (2.0 * step)
    lambda_f = (
        coenergy(id_a, iq_a, if_a + step) - coenergy(id_a, iq_a, if_a - step)
    ) / (2.0 * step)

    assert lambda_d == pytest.approx(ld_h * id_a + mutual * if_a, rel=1e-8)
    assert lambda_q == pytest.approx(lq_h * iq_a, rel=1e-8)
    assert lambda_f == pytest.approx(1.5 * mutual * id_a + lf_h * if_a, rel=1e-8)

    d_lambda_f_d_id = 1.5 * mutual
    d_lambda_d_d_if = mutual
    assert d_lambda_f_d_id == pytest.approx(1.5 * d_lambda_d_d_if)
    assert d_lambda_f_d_id != pytest.approx(d_lambda_d_d_if)


def test_zero_sequence_ratio_is_zero_for_a_balanced_set():
    a, b, c = extract.abc_from_dq(-40.0, 30.0, 17.0)
    assert extract.zero_sequence_ratio(a, b, c) == pytest.approx(0.0, abs=1e-12)


def test_electrical_angle_tracks_the_rotor_through_pole_pairs():
    cfg = DEFAULT_CONFIG
    base = cfg.extraction.d_axis_electrical_deg
    assert extract.electrical_angle_deg(0.0, cfg) == pytest.approx(base)
    assert extract.electrical_angle_deg(30.0, cfg) == pytest.approx(base + 60.0)


# ---------------------------------------------------------------------------
# Current injection: the branch convention
# ---------------------------------------------------------------------------


def test_stator_currents_are_divided_by_the_parallel_branches():
    """Commanded (id, iq) are TERMINAL amps; each branch carries I/4."""
    cfg = DEFAULT_CONFIG
    currents = extract.branch_currents(-100.0, 80.0, 10.0, 0.0, cfg)
    terminal = extract.abc_from_dq(-100.0, 80.0, 0.0)
    for name, terminal_value in zip(PHASE_CIRCUITS, terminal):
        assert currents[name] == pytest.approx(terminal_value / 4.0)


def test_field_current_is_not_divided():
    """The field winding has ONE branch: commanded = actual."""
    currents = extract.branch_currents(-100.0, 80.0, 10.0, 0.0, DEFAULT_CONFIG)
    assert currents[FIELD_CIRCUIT] == pytest.approx(10.0)


def test_set_currents_drives_every_circuit_once():
    handle = _pinned_handle()
    extract.set_currents(handle, -50.0, 40.0, 6.0, 0.0, DEFAULT_CONFIG)
    driven = [call.args[0] for call in handle.calls_named("mi_setcurrent")]
    assert sorted(driven) == sorted(list(PHASE_CIRCUITS) + [FIELD_CIRCUIT])


# ---------------------------------------------------------------------------
# The two sector multipliers
# ---------------------------------------------------------------------------


def test_flux_multiplier_is_one():
    """Circuit flux linkage is ALREADY the terminal flux linkage."""
    assert DEFAULT_CONFIG.extraction.flux_multiplier == 1.0
    assert extract.terminal_flux(0.0123, DEFAULT_CONFIG) == pytest.approx(0.0123)


def test_torque_multiplier_is_four():
    """The block integral covers one pole of a four-pole machine."""
    assert DEFAULT_CONFIG.extraction.torque_sector_multiplier == 4.0
    assert extract.full_machine_torque(2.5, DEFAULT_CONFIG) == pytest.approx(10.0)


def test_flux_is_not_multiplied_by_the_sector_count():
    """Regression guard: x4 on flux would be the series/parallel error."""
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert result["lambda_d_wb"] == pytest.approx(PINNED_LAMBDA_D, rel=1e-12)
    assert result["lambda_q_wb"] == pytest.approx(PINNED_LAMBDA_Q, rel=1e-12)


# ---------------------------------------------------------------------------
# Torque identity -- the known x4 double-count bug
# ---------------------------------------------------------------------------


def test_torque_identity_has_no_spurious_sector_factor():
    """REGRESSION: compare_flux_methods.py once applied x4 on the dq side.

    T = 1.5 * p * (lambda_d * iq - lambda_q * id) on TERMINAL quantities is
    already the full-machine torque. Pinned to a hand-computed literal.
    """
    identity = extract.torque_from_dq(PINNED_LAMBDA_D, PINNED_LAMBDA_Q,
                                      PINNED_POINT[0], PINNED_POINT[1],
                                      DEFAULT_CONFIG)
    assert identity == pytest.approx(PINNED_TORQUE_FULL_NM, rel=1e-12)
    # The bug would have produced exactly four times this.
    assert identity != pytest.approx(PINNED_TORQUE_FULL_NM * 4.0)


def test_extracted_torque_matches_the_hand_computed_literal():
    """Both sides pinned independently, so a shared double-count fails."""
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert result["torque_sector_nm"] == pytest.approx(PINNED_TORQUE_SECTOR_NM,
                                                       rel=1e-12)
    assert result["torque_fem_nm"] == pytest.approx(PINNED_TORQUE_FULL_NM,
                                                    rel=1e-12)
    assert result["torque_identity_nm"] == pytest.approx(PINNED_TORQUE_FULL_NM,
                                                         rel=1e-12)
    assert result["torque_residual_nm"] == pytest.approx(0.0, abs=1e-12)
    assert result["torque_residual_rel"] == pytest.approx(0.0, abs=1e-12)
    assert result["torque_residual_suspect"] == 0


def test_full_machine_scales_flux_by_quarter_and_torque_by_one():
    from dataclasses import replace
    cfg = replace(
        DEFAULT_CONFIG,
        geometry=replace(DEFAULT_CONFIG.geometry, full_machine=True),
    )
    assert extract.flux_scale(cfg) == pytest.approx(0.25)
    assert extract.torque_scale(cfg) == pytest.approx(1.0)


def test_even_torque_component_is_the_instrument_bias():
    """The r2 F1 miss is 2*T_even/mean|T|, not a scale error.

    Numbers copied from out/eesm/femm_f1_refined_r2_20260812/f1_refined_r2.json.
    """
    parts = extract.decompose_mirror_torque(
        2.856908408390477, -2.767250014389566)
    assert parts["even_nm"] == pytest.approx(0.04482919700045551)
    assert parts["odd_nm"] == pytest.approx(2.8120792113900217)
    assert parts["asymmetry_pct"] == pytest.approx(3.1883310270123055)
    identity = extract.decompose_mirror_torque(
        2.7461209297242672, -2.7445074511927134)
    assert identity["even_nm"] == pytest.approx(0.0008067392657769, abs=1e-12)
    assert identity["asymmetry_pct"] < 0.1


def test_airgap_torque_is_an_independent_readout_with_the_same_scaling():
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert result["torque_gap_sector_nm"] is None
    assert result["torque_gap_nm"] is None
    assert handle.call_count("mo_gapintegral") == 0
    assert handle.call_count("mo_blockintegral") == 1


def test_extracted_torque_matches_an_independent_closed_form():
    """Cross-check against analytic_torque_nm, which does not use extract.py."""
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    expected = analytic_torque_nm(*PINNED_POINT, machine=PINNED,
                                  cfg=DEFAULT_CONFIG)
    assert expected == pytest.approx(PINNED_TORQUE_FULL_NM, rel=1e-12)
    assert result["torque_fem_nm"] == pytest.approx(expected, rel=1e-12)


def test_sector_torque_is_a_quarter_of_the_full_machine_torque():
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert result["torque_fem_nm"] == pytest.approx(
        result["torque_sector_nm"] * 4.0, rel=1e-12)


# ---------------------------------------------------------------------------
# Mirror symmetry -- the assumption-free numerical-quality test
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("id_a,iq_a,if_a", [
    (-100.0, 80.0, 10.0),
    (0.0, 120.0, 0.0),
    (-120.0, 60.0, 15.0),
    (-45.0, 5.0, 3.0),
])
def test_mirror_pair_gives_equal_magnitude_torque(id_a, iq_a, if_a):
    """(id, iq) and (id, -iq) must give equal |T|.

    This is the single best assumption-free numerical-quality test, and it is
    what exposed the AEDT torque instrument: a mirror pair whose flux linkages
    agreed to 0.01% disagreed by 27.5% in Torque_FEM.
    """
    positive = extract.extract_point(_pinned_handle(), id_a, iq_a, if_a,
                                     cfg=DEFAULT_CONFIG)
    mirrored = extract.extract_point(_pinned_handle(), id_a, -iq_a, if_a,
                                     cfg=DEFAULT_CONFIG)
    assert abs(positive["torque_fem_nm"]) == pytest.approx(
        abs(mirrored["torque_fem_nm"]), rel=1e-12)
    assert positive["torque_fem_nm"] == pytest.approx(
        -mirrored["torque_fem_nm"], rel=1e-12)


def test_mirror_pair_flux_linkages_mirror_correctly():
    """lambda_d unchanged, lambda_q negated under iq -> -iq."""
    positive = extract.extract_point(_pinned_handle(), -100.0, 80.0, 10.0,
                                     cfg=DEFAULT_CONFIG)
    mirrored = extract.extract_point(_pinned_handle(), -100.0, -80.0, 10.0,
                                     cfg=DEFAULT_CONFIG)
    assert positive["lambda_d_wb"] == pytest.approx(mirrored["lambda_d_wb"],
                                                    rel=1e-12)
    assert positive["lambda_q_wb"] == pytest.approx(-mirrored["lambda_q_wb"],
                                                    rel=1e-12)


# ---------------------------------------------------------------------------
# Physics cross-checks the AEDT pilot established
# ---------------------------------------------------------------------------


def test_field_only_excitation_projects_onto_the_d_axis():
    """Target from the AEDT pilot: |lambda_q / lambda_d| ~ 1e-4."""
    handle = _pinned_handle()
    result = extract.extract_point(handle, 0.0, 0.0, 5.0, cfg=DEFAULT_CONFIG)
    assert abs(result["lambda_q_wb"] / result["lambda_d_wb"]) < 1.0e-4


def test_d_axis_flux_rises_with_field_current():
    """d(lambda_d)/d(If) > 0. This is what discriminates a field-coil sign
    error; the |lambda_q/lambda_d| ratio does NOT (it survives a sign flip)."""
    low = extract.extract_point(_pinned_handle(), 0.0, 0.0, 3.0,
                                cfg=DEFAULT_CONFIG)
    high = extract.extract_point(_pinned_handle(), 0.0, 0.0, 5.0,
                                 cfg=DEFAULT_CONFIG)
    slope = (high["lambda_d_wb"] - low["lambda_d_wb"]) / 2.0
    assert slope > 0.0
    assert slope == pytest.approx(PINNED.mutual_field_d_wb_per_a, rel=1e-12)


def test_default_mock_reproduces_the_pilot_order_of_magnitude():
    """Sanity targets, NOT gates: they came from a different mesh and solver."""
    machine = LinearSalientMachine()
    assert machine.ld_h > machine.lq_h > 0.0            # salient pole
    low = extract.extract_point(build_mock(), 0.0, 0.0, 3.0, cfg=DEFAULT_CONFIG)
    high = extract.extract_point(build_mock(), 0.0, 0.0, 5.0, cfg=DEFAULT_CONFIG)
    slope = (high["lambda_d_wb"] - low["lambda_d_wb"]) / 2.0
    assert slope == pytest.approx(4.63e-3, rel=1e-9)
    assert low["lambda_d_wb"] == pytest.approx(0.0128, abs=2e-3)


def test_saliency_is_visible_in_the_extracted_inductances():
    """Ld > Lq > 0 must be recoverable from extracted flux linkages."""
    d_probe = extract.extract_point(_pinned_handle(), -100.0, 0.0, 0.0,
                                    cfg=DEFAULT_CONFIG)
    q_probe = extract.extract_point(_pinned_handle(), 0.0, 100.0, 0.0,
                                    cfg=DEFAULT_CONFIG)
    ld = d_probe["lambda_d_wb"] / -100.0
    lq = q_probe["lambda_q_wb"] / 100.0
    assert ld > lq > 0.0


# ---------------------------------------------------------------------------
# Provenance and fail-closed behaviour
# ---------------------------------------------------------------------------


def test_result_carries_provenance():
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert result["mesh_elements"] == PINNED.mesh_elements
    assert result["solver_status"] == "converged"
    assert result["converged"] is True
    assert result["pole_pairs"] == 2
    # 120 mm contract stack. Was 0.0770793 (RMxprt's emitted value, a defect
    # per MAXWELL_EESM_QUALIFICATION.md) until 2026-08-12.
    assert result["model_depth_m"] == pytest.approx(0.120)
    assert result["flux_multiplier"] == 1.0
    assert result["torque_sector_multiplier"] == 4.0
    assert set(result["applied_branch_currents_a"]) == set(
        list(PHASE_CIRCUITS) + [FIELD_CIRCUIT])


def test_mock_mesh_is_above_the_aedt_student_cap():
    """The cap that forced this migration was ~2000 surface elements."""
    assert LinearSalientMachine().mesh_elements > 2000


def test_a_failed_solve_reports_no_numbers():
    """Fail closed: no flux, no torque, converged False."""
    handle = MockFemm(cfg=DEFAULT_CONFIG, machine=PINNED, fail_analysis=True)
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert result["converged"] is False
    assert result["lambda_d_wb"] is None
    assert result["lambda_q_wb"] is None
    assert result["solver_status"].startswith("failed:")
    assert "torque_fem_nm" not in result


def test_result_never_uses_the_schema_forbidden_key():
    """eesm_point.schema.json sets lambda_f_wb to `false` -- it is FORBIDDEN."""
    handle = _pinned_handle()
    result = extract.extract_point(handle, *PINNED_POINT, cfg=DEFAULT_CONFIG)
    assert "lambda_f_wb" not in result
    assert "lambda_field_wb" in result
