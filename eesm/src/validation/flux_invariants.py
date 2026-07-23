"""Physical-validity gates for FEM-extracted EESM flux maps.

These gates encode laws that any correct EESM flux map must satisfy,
independent of machine parameters, winding detail, or solver settings.
They exist because the Task 9 campaign produced 64/64 "converged" rows
whose flux labels were physically impossible, and every existing gate
passed.

Each gate names the specific physical law it enforces and reports the
measured quantity that violated it. Gates never assert bare-ly.

Offline module: runs in the project venv (Python 3), not inside AEDT.

Scope note
----------
`gate_zero_sequence` is a PER-POINT gate and is the only one usable as an
inline abort during a campaign. The remaining gates are BATCH gates: they
need a spread of operating points to estimate a derivative, and should be
run after a pilot block (>= 8 points spanning the current domain) and
again on the completed campaign.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping, Sequence


# --------------------------------------------------------------------------
# Tolerances. Deliberately loose: these detect broken physics, not accuracy.
# --------------------------------------------------------------------------

#: |lambda_0| / |lambda_dq| above which the abc set is not a balanced
#: three-phase set. A correct winding gives < 0.01; 0.05 is generous.
ZERO_SEQUENCE_MAX_RATIO = 0.05

#: Minimum Pearson correlation between the dq torque identity and the FEM
#: torque. These measure the same physical quantity; below this they do not.
TORQUE_CORRELATION_MIN = 0.95

#: Minimum number of points before a batch gate will return a verdict.
BATCH_MIN_POINTS = 8


class FluxInvariantViolation(Exception):
    """Raised when a flux map violates a physical law."""


def _f(record: Mapping[str, object], key: str) -> float:
    try:
        return float(record[key])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as exc:
        raise FluxInvariantViolation(
            "flux record is missing required numeric field %r; "
            "cannot evaluate physical validity on incomplete data" % key
        ) from exc


def _ols(rows: Sequence[Sequence[float]], y: Sequence[float]) -> list[float]:
    """Least squares with an intercept appended by the caller."""
    n = len(rows[0])
    a = [[sum(r[i] * r[j] for r in rows) for j in range(n)] for i in range(n)]
    b = [sum(r[i] * yy for r, yy in zip(rows, y)) for i in range(n)]
    for i in range(n):
        pivot = max(range(i, n), key=lambda t: abs(a[t][i]))
        if abs(a[pivot][i]) < 1e-18:
            raise FluxInvariantViolation(
                "current design matrix is singular: the operating points do "
                "not span id/iq/if independently, so no derivative gate can "
                "be evaluated. Widen the pilot block."
            )
        a[i], a[pivot] = a[pivot], a[i]
        b[i], b[pivot] = b[pivot], b[i]
        for t in range(i + 1, n):
            f = a[t][i] / a[i][i]
            for c in range(i, n):
                a[t][c] -= f * a[i][c]
            b[t] -= f * b[i]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (b[i] - sum(a[i][j] * x[j] for j in range(i + 1, n))) / a[i][i]
    return x


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float:
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx <= 0.0 or vy <= 0.0:
        return 0.0
    return cov / math.sqrt(vx * vy)


def _result(name: str, law: str, status: str, detail: str, **evidence) -> dict:
    return {
        "gate": name,
        "physical_law": law,
        "status": status,
        "detail": detail,
        "evidence": evidence,
    }


# --------------------------------------------------------------------------
# Per-point gate
# --------------------------------------------------------------------------

def gate_zero_sequence(
    record: Mapping[str, object],
    max_ratio: float = ZERO_SEQUENCE_MAX_RATIO,
) -> dict:
    """Kirchhoff / balanced-winding gate. PER-POINT: safe to run inline.

    A balanced three-phase winding with no neutral connection satisfies
    lambda_a + lambda_b + lambda_c = 0 at every operating point and every
    rotor position. A non-zero zero-sequence component means the three
    reported per-phase flux linkages are not a balanced three-phase set,
    so any Park transform of them is meaningless regardless of the angle
    or sign convention used.

    This is the gate that would have stopped the Task 9 campaign at row 1.
    """
    la = _f(record, "lambda_a_wb")
    lb = _f(record, "lambda_b_wb")
    lc = _f(record, "lambda_c_wb")

    lambda_0 = (la + lb + lc) / 3.0
    d = (2.0 / 3.0) * (la - 0.5 * lb - 0.5 * lc)
    q = (2.0 / 3.0) * (math.sqrt(3.0) / 2.0) * (lb - lc)
    magnitude = math.hypot(d, q)

    if magnitude < 1e-12:
        return _result(
            "zero_sequence",
            "balanced three-phase winding: lambda_a + lambda_b + lambda_c = 0",
            "inconclusive",
            "dq flux magnitude is numerically zero (%.3e Wb); the point "
            "carries no usable flux information." % magnitude,
            lambda_0_wb=lambda_0,
            lambda_dq_magnitude_wb=magnitude,
        )

    ratio = abs(lambda_0) / magnitude
    if ratio > max_ratio:
        return _result(
            "zero_sequence",
            "balanced three-phase winding: lambda_a + lambda_b + lambda_c = 0",
            "fail",
            "VIOLATION of the balanced-winding law. Measured zero-sequence "
            "flux is %.1f%% of the dq flux magnitude (limit %.1f%%). "
            "lambda_a=%+.6f, lambda_b=%+.6f, lambda_c=%+.6f Wb sum to "
            "%+.6f Wb instead of 0. The three reported per-phase linkages "
            "are not a balanced three-phase set, so lambda_d/lambda_q "
            "derived from them are not physical. Do NOT relabel or "
            "re-permute the phases to hide this: the imbalance is upstream "
            "of the Park transform, in what the solver reports for the "
            "winding. Check winding-to-coil assignment, go/return polarity "
            "pairing, and whether the sector model's periodic images are "
            "included in the reported linkage."
            % (100.0 * ratio, 100.0 * max_ratio, la, lb, lc, 3.0 * lambda_0),
            lambda_a_wb=la,
            lambda_b_wb=lb,
            lambda_c_wb=lc,
            lambda_0_wb=lambda_0,
            lambda_dq_magnitude_wb=magnitude,
            ratio=ratio,
            limit=max_ratio,
        )

    return _result(
        "zero_sequence",
        "balanced three-phase winding: lambda_a + lambda_b + lambda_c = 0",
        "pass",
        "zero-sequence is %.2f%% of dq magnitude." % (100.0 * ratio),
        lambda_0_wb=lambda_0,
        ratio=ratio,
    )


# --------------------------------------------------------------------------
# Batch gates
# --------------------------------------------------------------------------

def _batch_design(records: Sequence[Mapping[str, object]]):
    rows = []
    ld = []
    lq = []
    for r in records:
        rows.append([_f(r, "id_a"), _f(r, "iq_a"), _f(r, "if_a"), 1.0])
        ld.append(_f(r, "lambda_d_wb"))
        lq.append(_f(r, "lambda_q_wb"))
    return rows, ld, lq


def gate_field_couples_d_axis(records: Sequence[Mapping[str, object]]) -> dict:
    """Excitation-axis gate. BATCH.

    In an EESM the rotor field winding is, by definition, aligned with the
    d-axis: the d-axis IS the rotor field axis. Therefore

        d(lambda_d)/d(If) > 0     (the field is the d-axis excitation)
        d(lambda_q)/d(If) ~ 0     (the field must not couple the q-axis)

    A negative d-axis coupling, or a q-axis coupling larger than the
    d-axis coupling, means the exported dq frame is not aligned to the
    rotor field axis.
    """
    if len(records) < BATCH_MIN_POINTS:
        return _result(
            "field_couples_d_axis",
            "the rotor field winding defines the d-axis: d(lambda_d)/d(If) > 0",
            "inconclusive",
            "need >= %d points to estimate the derivative, have %d."
            % (BATCH_MIN_POINTS, len(records)),
        )

    rows, ld, lq = _batch_design(records)
    cd = _ols(rows, ld)
    cq = _ols(rows, lq)
    dld_dif = cd[2]
    dlq_dif = cq[2]

    if dld_dif <= 0.0:
        return _result(
            "field_couples_d_axis",
            "the rotor field winding defines the d-axis: d(lambda_d)/d(If) > 0",
            "fail",
            "VIOLATION of the excitation-axis law. Measured "
            "d(lambda_d)/d(If) = %+.4e Wb/A, which is not positive. "
            "Increasing field current must increase d-axis flux linkage - "
            "that coupling is the entire purpose of the field winding. A "
            "non-positive value means the exported dq frame is not aligned "
            "to the rotor field axis (commonly ~90 deg away, which swaps "
            "the roles of d and q). Determine the true d-axis angle "
            "empirically before trusting any row."
            % dld_dif,
            d_lambda_d_d_if=dld_dif,
            d_lambda_q_d_if=dlq_dif,
        )

    if abs(dlq_dif) > abs(dld_dif):
        return _result(
            "field_couples_d_axis",
            "the rotor field winding defines the d-axis: d(lambda_d)/d(If) > 0",
            "fail",
            "VIOLATION of the excitation-axis law. The field current "
            "couples the q-axis (%+.4e Wb/A) more strongly than the d-axis "
            "(%+.4e Wb/A). The field winding cannot produce more quadrature "
            "flux than direct flux; the dq frame is rotated away from the "
            "rotor field axis."
            % (dlq_dif, dld_dif),
            d_lambda_d_d_if=dld_dif,
            d_lambda_q_d_if=dlq_dif,
        )

    return _result(
        "field_couples_d_axis",
        "the rotor field winding defines the d-axis: d(lambda_d)/d(If) > 0",
        "pass",
        "d(lambda_d)/d(If) = %+.4e Wb/A, d(lambda_q)/d(If) = %+.4e Wb/A."
        % (dld_dif, dlq_dif),
        d_lambda_d_d_if=dld_dif,
        d_lambda_q_d_if=dlq_dif,
    )


def gate_salient_pole_saliency(
    records: Sequence[Mapping[str, object]],
    salient_pole: bool = True,
) -> dict:
    """Saliency-orientation gate. BATCH.

    For a wound-field salient-pole machine the d-axis flux path runs
    through the pole body (iron, low reluctance) and the q-axis path
    crosses the interpolar gap (air, high reluctance). Therefore

        Ld > Lq

    An inverted ratio is the classic signature of d and q being swapped.
    Set salient_pole=False for machines where Lq > Ld is expected
    (e.g. interior-PM rotors); the gate then checks the opposite ordering.
    """
    if len(records) < BATCH_MIN_POINTS:
        return _result(
            "salient_pole_saliency",
            "salient-pole wound rotor: Ld > Lq",
            "inconclusive",
            "need >= %d points, have %d." % (BATCH_MIN_POINTS, len(records)),
        )

    rows, ld, lq = _batch_design(records)
    l_d = _ols(rows, ld)[0]
    l_q = _ols(rows, lq)[1]

    if l_d <= 0.0 or l_q <= 0.0:
        return _result(
            "salient_pole_saliency",
            "salient-pole wound rotor: Ld > Lq",
            "fail",
            "VIOLATION of passivity. Measured Ld = %+.4e H, Lq = %+.4e H; "
            "self-inductances must be positive. A negative self-inductance "
            "means the flux extraction has the wrong sign relative to the "
            "current injection."
            % (l_d, l_q),
            ld_h=l_d,
            lq_h=l_q,
        )

    ok = l_d > l_q if salient_pole else l_q > l_d
    if not ok:
        expected = "Ld > Lq" if salient_pole else "Lq > Ld"
        return _result(
            "salient_pole_saliency",
            "salient-pole wound rotor: Ld > Lq",
            "fail",
            "VIOLATION of the saliency-orientation law. Measured "
            "Ld = %.4e H, Lq = %.4e H, ratio Lq/Ld = %.2f, but a "
            "salient-pole wound rotor requires %s: the d-axis path is "
            "through pole iron (low reluctance) and the q-axis path "
            "crosses the interpolar air gap (high reluctance). An inverted "
            "saliency ratio is the standard signature of the d and q axes "
            "being interchanged."
            % (l_d, l_q, l_q / l_d, expected),
            ld_h=l_d,
            lq_h=l_q,
            lq_over_ld=l_q / l_d,
        )

    return _result(
        "salient_pole_saliency",
        "salient-pole wound rotor: Ld > Lq",
        "pass",
        "Ld = %.4e H, Lq = %.4e H, Ld/Lq = %.2f." % (l_d, l_q, l_d / l_q),
        ld_h=l_d,
        lq_h=l_q,
    )


def gate_dq_torque_consistency(
    records: Sequence[Mapping[str, object]],
    pole_pairs: int,
    correlation_min: float = TORQUE_CORRELATION_MIN,
    tolerance_nm: float | None = None,
) -> dict:
    """Torque-closure gate. BATCH.

    T = 1.5 * p * (lambda_d * iq - lambda_q * id) and the solver's virtual
    work torque are two computations of the same physical quantity, so
    they must correlate.

    Correlation is checked BEFORE magnitude. This ordering matters: a
    wrong stack depth, turns count or pole-pair count produces high
    correlation with a wrong slope (a fixable scale error), whereas low
    correlation means the two quantities are not measuring the same thing
    and no rescaling can reconcile them. Reporting only a magnitude
    residual conflates these two very different diagnoses - which is what
    happened in Task 9, where a 42.47 N.m residual was read as a scaling
    problem when the underlying correlation was -0.04.
    """
    if len(records) < BATCH_MIN_POINTS:
        return _result(
            "dq_torque_consistency",
            "T = 1.5*p*(lambda_d*iq - lambda_q*id) equals the virtual-work torque",
            "inconclusive",
            "need >= %d points, have %d." % (BATCH_MIN_POINTS, len(records)),
        )

    analytic = []
    solver = []
    for r in records:
        ld = _f(r, "lambda_d_wb")
        lq = _f(r, "lambda_q_wb")
        analytic.append(
            1.5 * pole_pairs * (ld * _f(r, "iq_a") - lq * _f(r, "id_a"))
        )
        solver.append(_f(r, "torque_controller_nm"))

    r_value = _pearson(analytic, solver)
    denom = sum(s * s for s in solver)
    scale = sum(a * s for a, s in zip(analytic, solver)) / denom if denom else 0.0
    residuals = [abs(a - s) for a, s in zip(analytic, solver)]
    max_residual = max(residuals)

    if r_value < correlation_min:
        return _result(
            "dq_torque_consistency",
            "T = 1.5*p*(lambda_d*iq - lambda_q*id) equals the virtual-work torque",
            "fail",
            "VIOLATION of torque closure, and it is NOT a scaling error. "
            "Pearson correlation between the dq torque identity and the "
            "solver torque is %+.4f (required >= %.2f). These two "
            "expressions compute the same physical quantity, so low "
            "correlation means the flux map and the torque are not "
            "describing the same machine state. Best-fit single scale "
            "factor is %.4f and still leaves a maximum residual of "
            "%.3f N.m - confirming no depth, turns, pole-pair or sign "
            "correction can close this. Fix the flux extraction; do not "
            "rescale."
            % (r_value, correlation_min, scale, max_residual),
            pearson_r=r_value,
            best_fit_scale=scale,
            max_residual_nm=max_residual,
        )

    if tolerance_nm is not None and max_residual > tolerance_nm:
        return _result(
            "dq_torque_consistency",
            "T = 1.5*p*(lambda_d*iq - lambda_q*id) equals the virtual-work torque",
            "fail",
            "Torque closure residual %.3f N.m exceeds the frozen tolerance "
            "%.3f N.m. Correlation is healthy (%+.4f) and the best-fit "
            "scale is %.4f, so this IS consistent with a scaling error - "
            "check model depth, series turns per phase, the sector "
            "symmetry multiplier, and pole pairs, in that order."
            % (max_residual, tolerance_nm, r_value, scale),
            pearson_r=r_value,
            best_fit_scale=scale,
            max_residual_nm=max_residual,
            tolerance_nm=tolerance_nm,
        )

    return _result(
        "dq_torque_consistency",
        "T = 1.5*p*(lambda_d*iq - lambda_q*id) equals the virtual-work torque",
        "pass",
        "r = %+.4f, max residual %.3f N.m, best-fit scale %.4f."
        % (r_value, max_residual, scale),
        pearson_r=r_value,
        max_residual_nm=max_residual,
        best_fit_scale=scale,
    )


# --------------------------------------------------------------------------
# Aggregate
# --------------------------------------------------------------------------

def evaluate_flux_invariants(
    records: Sequence[Mapping[str, object]],
    pole_pairs: int,
    salient_pole: bool = True,
    torque_tolerance_nm: float | None = None,
) -> dict:
    """Run every gate. Returns overall 'pass' / 'fail' / 'inconclusive'.

    'inconclusive' is never treated as 'pass'.
    """
    gates = []

    # A point carrying no flux at all (the source-free origin) is 'inconclusive',
    # not a violation of the balanced-winding law. Keep the two apart so a
    # null probe point cannot be mistaken for broken physics.
    failed_points = []
    null_points = []
    for index, record in enumerate(records):
        outcome = gate_zero_sequence(record)
        if outcome["status"] == "fail":
            failed_points.append((index, record.get("point_id", index), outcome))
        elif outcome["status"] == "inconclusive":
            null_points.append((index, record.get("point_id", index)))

    law = "balanced three-phase winding: lambda_a + lambda_b + lambda_c = 0"
    if failed_points:
        first = failed_points[0]
        gates.append(
            _result(
                "zero_sequence",
                law,
                "fail",
                "%d of %d points violate the balanced-winding law. First "
                "offender is row %d (point_id=%s): %s"
                % (
                    len(failed_points),
                    len(records),
                    first[0],
                    first[1],
                    first[2]["detail"],
                ),
                failing_point_count=len(failed_points),
                null_point_count=len(null_points),
                total_points=len(records),
                first_failing_point_id=str(first[1]),
            )
        )
    elif len(null_points) == len(records):
        gates.append(
            _result(
                "zero_sequence",
                law,
                "inconclusive",
                "all %d points carry numerically zero flux; the balanced-"
                "winding law cannot be evaluated." % len(records),
                null_point_count=len(null_points),
            )
        )
    else:
        gates.append(
            _result(
                "zero_sequence",
                law,
                "pass",
                "all %d evaluable points balanced (%d null point(s) skipped)."
                % (len(records) - len(null_points), len(null_points)),
                null_point_count=len(null_points),
            )
        )

    gates.append(gate_field_couples_d_axis(records))
    gates.append(gate_salient_pole_saliency(records, salient_pole=salient_pole))
    gates.append(
        gate_dq_torque_consistency(
            records, pole_pairs, tolerance_nm=torque_tolerance_nm
        )
    )

    statuses = [g["status"] for g in gates]
    if "fail" in statuses:
        overall = "fail"
    elif "inconclusive" in statuses:
        overall = "inconclusive"
    else:
        overall = "pass"

    return {
        "overall_status": overall,
        "point_count": len(records),
        "pole_pairs": pole_pairs,
        "gates": gates,
    }


def require_flux_invariants(
    records: Sequence[Mapping[str, object]],
    pole_pairs: int,
    **kwargs,
) -> dict:
    """evaluate_flux_invariants, but raise on anything that is not 'pass'."""
    report = evaluate_flux_invariants(records, pole_pairs, **kwargs)
    if report["overall_status"] != "pass":
        lines = [
            "EESM flux map failed physical validation (%s)."
            % report["overall_status"]
        ]
        for gate in report["gates"]:
            if gate["status"] != "pass":
                lines.append(
                    "  [%s] %s\n    law: %s\n    %s"
                    % (
                        gate["status"].upper(),
                        gate["gate"],
                        gate["physical_law"],
                        gate["detail"],
                    )
                )
        raise FluxInvariantViolation("\n".join(lines))
    return report
