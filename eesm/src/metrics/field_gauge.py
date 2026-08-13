"""The one-dimensional gauge freedom in zero-shot lambda_f recovery.

Train a co-energy net on (lambda_d, lambda_q) only. Matching the stator
gradient of W' determines the potential up to an additive function of the field
current alone:

    W'_fit(id, iq, If) = W'_true(id, iq, If) + g(If)

Differentiating in If, the recovered field flux linkage carries one unknown
one-dimensional term:

    lambda_f_fit(x) = lambda_f_true(x) + g'(If)

Everything that depends on id or iq -- the armature-reaction part, which is the
part a controller needs -- is fully determined by reciprocity and needs no
lambda_f truth at all.

`fit_gauge` estimates g'(If) as a low-order polynomial from TRAINING rows only.
Selection and scheduler-audit rows must never enter the fit; the gauge is part
of the model, not part of the evaluation.
"""

from __future__ import annotations

from typing import Any

import numpy as np

#: Cubic is enough for a smooth open-circuit field curve and cannot absorb
#: id/iq structure, which is the whole point of the ablation. Pre-registered:
#: do not raise this after seeing residuals.
DEFAULT_DEGREE = 3


class FieldGauge:
    """Additive g'(If) correction recovered from training residuals."""

    def __init__(self, coefficients: np.ndarray, degree: int, n_train: int):
        self.coefficients = np.asarray(coefficients, dtype=np.float64)
        self.degree = int(degree)
        self.n_train = int(n_train)

    def __call__(self, if_a: np.ndarray) -> np.ndarray:
        return np.polyval(self.coefficients, np.asarray(if_a, dtype=np.float64))

    def apply(self, lambda_f_raw: np.ndarray, if_a: np.ndarray) -> np.ndarray:
        """Remove the gauge from a raw zero-shot lambda_f prediction."""
        return np.asarray(lambda_f_raw, dtype=np.float64) - self(if_a)

    def to_dict(self) -> dict[str, Any]:
        return {
            "form": "polynomial_in_if",
            "degree": self.degree,
            "coefficients_high_to_low": [float(c) for c in self.coefficients],
            "n_train": self.n_train,
            "fitted_on": "train_role_only",
        }


def fit_gauge(
    if_train: np.ndarray,
    lambda_f_raw_train: np.ndarray,
    lambda_f_truth_train: np.ndarray,
    degree: int = DEFAULT_DEGREE,
) -> FieldGauge:
    """Fit g'(If) from training-row residuals of a zero-shot lambda_f."""
    if_train = np.asarray(if_train, dtype=np.float64)
    residual = (
        np.asarray(lambda_f_raw_train, dtype=np.float64)
        - np.asarray(lambda_f_truth_train, dtype=np.float64)
    )
    if if_train.ndim != 1 or residual.shape != if_train.shape:
        raise ValueError("if_train and residuals must be 1-D and the same length")
    if if_train.size <= degree:
        raise ValueError("not enough training rows to fit the gauge")
    coefficients = np.polyfit(if_train, residual, degree)
    return FieldGauge(coefficients, degree, if_train.size)


def gauge_dimensionality_r2(
    gauge: FieldGauge,
    if_eval: np.ndarray,
    lambda_f_raw_eval: np.ndarray,
    lambda_f_truth_eval: np.ndarray,
) -> float:
    """Out-of-sample check that the zero-shot error really is 1-D in If.

    Fraction of the held-out zero-shot residual variance explained by a
    function of If alone. The identifiability argument predicts this tends to
    1 as the stator fit improves; a value well below 1 means the residual still
    carries id/iq structure and the ablation is not yet in its asymptotic
    regime.
    """
    if_eval = np.asarray(if_eval, dtype=np.float64)
    residual = (
        np.asarray(lambda_f_raw_eval, dtype=np.float64)
        - np.asarray(lambda_f_truth_eval, dtype=np.float64)
    )
    total = float(np.var(residual))
    if total <= 0.0:
        return float("nan")
    return float(1.0 - np.var(residual - gauge(if_eval)) / total)


def field_only_control(
    if_train: np.ndarray,
    lambda_f_train: np.ndarray,
    if_eval: np.ndarray,
    degree: int = DEFAULT_DEGREE,
) -> np.ndarray:
    """CONTROL: predict lambda_f from If alone.

    lambda_f correlates with If, so without this control a zero-shot result
    could just be that correlation. If the zero-shot prediction does not beat
    this by a wide margin, the claim is not about energy consistency.
    """
    coefficients = np.polyfit(
        np.asarray(if_train, dtype=np.float64),
        np.asarray(lambda_f_train, dtype=np.float64),
        degree,
    )
    return np.polyval(coefficients, np.asarray(if_eval, dtype=np.float64))
