"""Reciprocity residuals for EESM flux surrogates.

Every identity here is the amplitude-invariant form fixed in
`eesm/docs/DQ_CONVENTIONS.md`. The naive equalities are wrong in this
convention by roughly three orders of magnitude on the measured anchors, so
they are computed too and reported as `R_fd_naive` -- a regression tripwire,
not a metric to optimize.

For a conservative machine the co-energy W'(id, iq, If) satisfies

    dW' = (3/2) lambda_d did + (3/2) lambda_q diq + lambda_f dIf

so the mixed partials of W' give three testable identities:

    R_dq = d lambda_d / d iq   -   d lambda_q / d id
    R_fd = d lambda_f / d id   -   (3/2) d lambda_d / d If
    R_fq = d lambda_f / d iq   -   (3/2) d lambda_q / d If

`lambda_f` here is the TERMINAL field flux linkage. On the 90 degree sector
model the raw campaign column `lambda_field_wb` is one pole, so terminal
lambda_f = 4 * lambda_field_wb (see `FIELD_SECTOR_TO_TERMINAL`).

These are DIAGNOSTICS. They are not frozen gates, they carry no threshold, and
nothing in this module may influence promotion. Introducing them as gates
requires a new pre-registered phase with its own threshold freeze.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

import numpy as np

#: Central-difference steps, in amperes. These deliberately match
#: `eesm/docs/FD_HESSIAN_ANCHORS.md` so a surrogate Jacobian and the FEM
#: Jacobian are the same secant slope over the same interval, isolating model
#: error from discretization error. Do not retune after seeing results.
DEFAULT_STEPS = (1.0, 1.0, 0.2)

#: Raw `lambda_field_wb` on the 90 degree model is one pole.
FIELD_SECTOR_TO_TERMINAL = 4.0

#: The 3/2 in the amplitude-invariant stator-field identity.
FIELD_RECIPROCITY_FACTOR = 1.5

#: Map domain, from the frozen manifest.
DEFAULT_DOMAIN_LO = (-120.0, 0.0, 0.0)
DEFAULT_DOMAIN_HI = (0.0, 120.0, 15.0)

PredictFn = Callable[[np.ndarray], np.ndarray]


def interior_mask(
    X: np.ndarray,
    steps: tuple[float, float, float] = DEFAULT_STEPS,
    domain_lo: tuple[float, float, float] = DEFAULT_DOMAIN_LO,
    domain_hi: tuple[float, float, float] = DEFAULT_DOMAIN_HI,
) -> np.ndarray:
    """Rows with +/- step room inside the map domain.

    Same admissibility rule the FD anchors used. A central difference that
    leaves the domain is not evaluated rather than silently one-sided.
    """
    X = np.asarray(X, dtype=np.float64)
    h = np.asarray(steps, dtype=np.float64)
    lo = np.asarray(domain_lo, dtype=np.float64)
    hi = np.asarray(domain_hi, dtype=np.float64)
    return np.all((X - h >= lo) & (X + h <= hi), axis=1)


def central_jacobian(
    predict: PredictFn,
    X: np.ndarray,
    steps: tuple[float, float, float] = DEFAULT_STEPS,
) -> np.ndarray:
    """Central-difference Jacobian of a surrogate.

    Returns ``J`` with ``J[n, o, i] = d lambda_o / d x_i`` at row ``n``, where
    the output order is ``(lambda_d, lambda_q[, lambda_f_terminal])`` and the
    input order is ``(id, iq, If)``.

    This is deliberately family-agnostic: no family needs to expose an analytic
    gradient, and a piecewise-constant family (tree ensemble) or a piecewise-
    affine one (PWA) is measured on exactly the same secant as everything else.
    """
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] != 3:
        raise ValueError("X must have shape (n, 3)")
    if X.shape[0] == 0:
        raise ValueError("X must be non-empty")
    h = np.asarray(steps, dtype=np.float64)
    if np.any(h <= 0.0):
        raise ValueError("steps must be positive")

    probe = np.asarray(predict(X[:1]), dtype=np.float64)
    if probe.ndim != 2 or probe.shape[1] not in (2, 3):
        raise ValueError("predict must return shape (n, 2) or (n, 3)")
    n_out = probe.shape[1]

    jacobian = np.empty((X.shape[0], n_out, 3), dtype=np.float64)
    for axis in range(3):
        offset = np.zeros(3, dtype=np.float64)
        offset[axis] = h[axis]
        plus = np.asarray(predict(X + offset), dtype=np.float64)
        minus = np.asarray(predict(X - offset), dtype=np.float64)
        if plus.shape != (X.shape[0], n_out) or minus.shape != plus.shape:
            raise ValueError("predict returned an inconsistent shape")
        jacobian[:, :, axis] = (plus - minus) / (2.0 * h[axis])
    return jacobian


def reciprocity_residuals(
    predict: PredictFn,
    X: np.ndarray,
    steps: tuple[float, float, float] = DEFAULT_STEPS,
) -> dict[str, np.ndarray]:
    """Per-point reciprocity residuals, in henries.

    Only rows with +/- step room inside the domain are evaluated; the mask is
    returned so a caller can report coverage rather than assume it.
    """
    X = np.asarray(X, dtype=np.float64)
    mask = interior_mask(X, steps)
    if not mask.any():
        raise ValueError("no evaluation point has +/- step room in the domain")
    jacobian = central_jacobian(predict, X[mask], steps)

    out: dict[str, np.ndarray] = {
        "mask": mask,
        "R_dq": jacobian[:, 0, 1] - jacobian[:, 1, 0],
    }
    if jacobian.shape[1] == 3:
        out["R_fd"] = (
            jacobian[:, 2, 0] - FIELD_RECIPROCITY_FACTOR * jacobian[:, 0, 2]
        )
        out["R_fq"] = (
            jacobian[:, 2, 1] - FIELD_RECIPROCITY_FACTOR * jacobian[:, 1, 2]
        )
        # Wrong-convention control. Large here means the convention is right;
        # small here would mean somebody dropped the 3/2 or the sector factor.
        out["R_fd_naive"] = jacobian[:, 2, 0] - jacobian[:, 0, 2]
    return out


def summarize(
    residuals: Mapping[str, np.ndarray],
    floors: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """Reduce per-point residuals to reportable statistics.

    `floors` optionally carries the FEM truth's own reciprocity residual (from
    the FD anchors). A surrogate cannot meaningfully beat that number, so the
    ratio to it is the honest way to read these -- an absolute residual near
    zero means "at the noise floor", not "exactly conservative".
    """
    mask = np.asarray(residuals["mask"], dtype=bool)
    summary: dict[str, Any] = {
        "n_eval": int(mask.sum()),
        "n_total": int(mask.size),
        "steps_a": list(DEFAULT_STEPS),
    }
    for key in ("R_dq", "R_fd", "R_fq", "R_fd_naive"):
        if key not in residuals:
            continue
        values = np.asarray(residuals[key], dtype=np.float64)
        entry: dict[str, Any] = {
            "rms_h": float(np.sqrt(np.mean(values ** 2))),
            "max_abs_h": float(np.max(np.abs(values))),
            "mean_h": float(np.mean(values)),
        }
        if floors and key in floors and floors[key]:
            entry["ratio_to_fem_floor"] = entry["max_abs_h"] / float(floors[key])
        summary[key] = entry
    return summary


def fem_reciprocity_floors(anchors: Mapping[str, Any]) -> dict[str, float]:
    """The FEM truth's own reciprocity residual, read from an anchors bundle.

    This is the measurement noise floor for every surrogate comparison.
    """
    rows = [anchor["inductance"] for anchor in anchors["anchors"]]

    def worst(key: str) -> float:
        return float(max(abs(float(row[key])) for row in rows))

    return {
        "R_dq": worst("reciprocity_dq"),
        "R_fd": worst("reciprocity_fd_terminal_minus_1p5_Ldf"),
        "R_fq": worst("reciprocity_fq_terminal_minus_1p5_Lqf"),
        "R_fd_naive": worst("reciprocity_fd_naive"),
    }
