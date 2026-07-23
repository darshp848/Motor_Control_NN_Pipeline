"""Tests for the EESM flux-map physical validity gates."""

from __future__ import annotations

import math

import pytest

from validation.flux_invariants import (
    FluxInvariantViolation,
    evaluate_flux_invariants,
    gate_dq_torque_consistency,
    gate_field_couples_d_axis,
    gate_salient_pole_saliency,
    gate_zero_sequence,
    require_flux_invariants,
)


POLE_PAIRS = 2


def synthetic_records(
    n: int = 24,
    ld_h: float = 3.0e-4,
    lq_h: float = 1.0e-4,
    lambda_f_per_amp: float = 4.0e-3,
    zero_sequence: float = 0.0,
    swap_dq: bool = False,
):
    """A physically consistent salient-pole EESM map, optionally corrupted.

    lambda_d = Ld*id + k*if,  lambda_q = Lq*iq,  torque from the dq identity,
    so a clean call satisfies every gate exactly.
    """
    records = []
    for i in range(n):
        id_a = -120.0 * (i % 5) / 4.0
        iq_a = 120.0 * ((i // 5) % 5) / 4.0
        if_a = 15.0 * ((i // 3) % 4) / 3.0

        lam_d = ld_h * id_a + lambda_f_per_amp * if_a
        lam_q = lq_h * iq_a
        if swap_dq:
            lam_d, lam_q = lam_q, lam_d

        torque = 1.5 * POLE_PAIRS * (lam_d * iq_a - lam_q * id_a)

        # Reconstruct a balanced abc set from dq at theta = 0, then inject
        # any requested zero-sequence component.
        la = lam_d + zero_sequence
        lb = -0.5 * lam_d + (math.sqrt(3.0) / 2.0) * lam_q + zero_sequence
        lc = -0.5 * lam_d - (math.sqrt(3.0) / 2.0) * lam_q + zero_sequence

        records.append({
            "point_id": "p%02d" % i,
            "id_a": id_a,
            "iq_a": iq_a,
            "if_a": if_a,
            "lambda_a_wb": la,
            "lambda_b_wb": lb,
            "lambda_c_wb": lc,
            "lambda_d_wb": lam_d,
            "lambda_q_wb": lam_q,
            "torque_controller_nm": torque,
        })
    return records


# ---------------------------------------------------------------------------
# zero sequence
# ---------------------------------------------------------------------------

def test_zero_sequence_passes_on_balanced_set():
    record = synthetic_records(n=6)[3]
    result = gate_zero_sequence(record)
    assert result["status"] == "pass"


def test_zero_sequence_fails_and_names_the_law():
    record = synthetic_records(n=6, zero_sequence=0.02)[3]
    result = gate_zero_sequence(record)
    assert result["status"] == "fail"
    assert "lambda_a + lambda_b + lambda_c = 0" in result["physical_law"]
    assert "VIOLATION" in result["detail"]
    # must report the measured numbers, not just complain
    assert "%" in result["detail"]
    assert result["evidence"]["ratio"] > 0.05


def test_zero_sequence_inconclusive_on_null_point():
    record = {
        "lambda_a_wb": 0.0, "lambda_b_wb": 0.0, "lambda_c_wb": 0.0,
    }
    assert gate_zero_sequence(record)["status"] == "inconclusive"


def test_missing_field_raises_rather_than_defaulting():
    with pytest.raises(FluxInvariantViolation):
        gate_zero_sequence({"lambda_a_wb": 0.1, "lambda_b_wb": 0.1})


# ---------------------------------------------------------------------------
# field couples the d axis
# ---------------------------------------------------------------------------

def test_field_coupling_passes_when_positive():
    result = gate_field_couples_d_axis(synthetic_records())
    assert result["status"] == "pass"
    assert result["evidence"]["d_lambda_d_d_if"] > 0.0


def test_field_coupling_fails_when_negative():
    records = synthetic_records(lambda_f_per_amp=-4.0e-3)
    result = gate_field_couples_d_axis(records)
    assert result["status"] == "fail"
    assert "d-axis" in result["physical_law"]
    assert "VIOLATION" in result["detail"]


def test_field_coupling_inconclusive_on_small_batch():
    result = gate_field_couples_d_axis(synthetic_records(n=4))
    assert result["status"] == "inconclusive"


# ---------------------------------------------------------------------------
# saliency
# ---------------------------------------------------------------------------

def test_saliency_passes_for_salient_pole():
    result = gate_salient_pole_saliency(synthetic_records())
    assert result["status"] == "pass"


def test_saliency_fails_when_inverted():
    records = synthetic_records(ld_h=1.0e-4, lq_h=3.0e-4)
    result = gate_salient_pole_saliency(records)
    assert result["status"] == "fail"
    assert "Lq/Ld" in result["detail"]


def test_saliency_respects_non_salient_flag():
    records = synthetic_records(ld_h=1.0e-4, lq_h=3.0e-4)
    assert gate_salient_pole_saliency(
        records, salient_pole=False
    )["status"] == "pass"


# ---------------------------------------------------------------------------
# torque closure
# ---------------------------------------------------------------------------

def test_torque_consistency_passes_on_consistent_map():
    result = gate_dq_torque_consistency(
        synthetic_records(), POLE_PAIRS, tolerance_nm=1.1
    )
    assert result["status"] == "pass"
    assert result["evidence"]["pearson_r"] > 0.99


def test_torque_scaling_error_is_reported_as_scaling_not_structure():
    """A pure scale error must keep correlation high and say so."""
    records = synthetic_records()
    for r in records:
        r["torque_controller_nm"] = r["torque_controller_nm"] / 4.0
    result = gate_dq_torque_consistency(
        records, POLE_PAIRS, tolerance_nm=1.1
    )
    assert result["status"] == "fail"
    assert result["evidence"]["pearson_r"] > 0.95
    assert "consistent with a scaling error" in result["detail"]


def test_torque_structural_error_is_not_reported_as_scaling():
    """Uncorrelated torque must be called out as unfixable by rescaling."""
    records = synthetic_records()
    for i, r in enumerate(records):
        r["torque_controller_nm"] = 10.0 * math.sin(i * 2.3987)
    result = gate_dq_torque_consistency(
        records, POLE_PAIRS, tolerance_nm=1.1
    )
    assert result["status"] == "fail"
    assert "NOT a scaling error" in result["detail"]
    assert "do not rescale" in result["detail"].lower()


# ---------------------------------------------------------------------------
# aggregate behaviour
# ---------------------------------------------------------------------------

def test_evaluate_passes_on_clean_map():
    report = evaluate_flux_invariants(
        synthetic_records(), POLE_PAIRS, torque_tolerance_nm=1.1
    )
    assert report["overall_status"] == "pass"
    assert all(g["status"] == "pass" for g in report["gates"])


def test_inconclusive_is_not_treated_as_pass():
    report = evaluate_flux_invariants(synthetic_records(n=4), POLE_PAIRS)
    assert report["overall_status"] == "inconclusive"


def test_require_raises_with_law_in_message():
    records = synthetic_records(zero_sequence=0.02)
    with pytest.raises(FluxInvariantViolation) as excinfo:
        require_flux_invariants(records, POLE_PAIRS)
    message = str(excinfo.value)
    assert "zero_sequence" in message
    assert "lambda_a + lambda_b + lambda_c = 0" in message


def test_task9_failure_signature_is_rejected():
    """Regression: the observed Task 9 signature must fail every gate.

    Reproduces the three measured pathologies together - inverted saliency,
    negative field coupling, and heavy zero-sequence contamination.
    """
    records = synthetic_records(
        ld_h=5.1e-5,
        lq_h=1.7e-4,
        lambda_f_per_amp=-4.3e-4,
        zero_sequence=0.015,
    )
    report = evaluate_flux_invariants(
        records, POLE_PAIRS, torque_tolerance_nm=1.1
    )
    assert report["overall_status"] == "fail"
    failed = {g["gate"] for g in report["gates"] if g["status"] == "fail"}
    assert "zero_sequence" in failed
    assert "field_couples_d_axis" in failed
    assert "salient_pole_saliency" in failed
