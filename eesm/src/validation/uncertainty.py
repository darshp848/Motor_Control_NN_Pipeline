"""Predictive-uncertainty calibration on the frozen off-grid FEM set.

This is the first uncertainty-quantification leg of the pipeline. It is
REPORT-ONLY: it does not gate promotion. Per the research framing, raw GP
variance may NOT be treated as a safety signal until its calibration is
demonstrated -- so this module MEASURES calibration (coverage, sharpness,
reliability, error-vs-uncertainty discrimination) rather than assuming it.

It answers, for a probabilistic surrogate evaluated against INDEPENDENT frozen
off-grid FEM truth (never the training or the same-set selection points):

  - Coverage: at nominal central level p (e.g. 68/90/95%), what fraction of
    truths actually fall inside pred +/- z(p)*sigma? Well-calibrated => empirical
    ~= nominal.
  - Reliability: the full nominal-vs-empirical curve, and a scalar calibration
    error (mean |nominal - empirical|, an ECE-style summary).
  - Sharpness: mean predictive sigma (only meaningful alongside coverage; a model
    can be sharp and wrong or wide and useless).
  - Discrimination: does a larger predicted sigma actually co-occur with larger
    absolute error? (Spearman rank correlation of |error| vs sigma.) This is what
    an "unsupported-region detector" needs, independent of absolute calibration.

Everything is computed per flux component (lambda_d, lambda_q) and, when region
labels are supplied, per region -- because a controller cares about worst-region
behaviour, not a pooled average (the same principle as controller_metrics).
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

import numpy as np

#: Standard-normal two-sided central-interval z-multipliers. A calibrated
#: Gaussian predictive interval pred +/- z*sigma should cover `level` of truths.
_DEFAULT_LEVELS = (0.5, 0.6827, 0.9, 0.9545, 0.99)

#: Normal inverse-CDF at (1+level)/2, hard-coded so the module needs no scipy.
_Z_FOR_LEVEL = {
    0.5: 0.6744897501960817,
    0.6827: 1.0000345054970227,
    0.9: 1.6448536269514722,
    0.9545: 2.0000024438996036,
    0.95: 1.959963984540054,
    0.99: 2.5758293035489004,
}


def _z_for(level: float) -> float:
    if level in _Z_FOR_LEVEL:
        return _Z_FOR_LEVEL[level]
    # Fallback: Acklam-style rational approximation of the normal quantile.
    p = (1.0 + level) / 2.0
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
               ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p <= phigh:
        q = p - 0.5
        r = q * q
        return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / \
               (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)
    q = math.sqrt(-2 * math.log(1 - p))
    return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / \
            ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)


def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    """Spearman rank correlation, stdlib-only (scipy not a dependency here)."""
    n = a.size
    if n < 2:
        return float("nan")

    def rank(x: np.ndarray) -> np.ndarray:
        order = np.argsort(x, kind="mergesort")
        ranks = np.empty(n, dtype=np.float64)
        ranks[order] = np.arange(1, n + 1, dtype=np.float64)
        # average ties
        _, inv, counts = np.unique(x, return_inverse=True, return_counts=True)
        sums = np.zeros(counts.size)
        np.add.at(sums, inv, ranks)
        return (sums / counts)[inv]

    ra, rb = rank(a), rank(b)
    ra -= ra.mean()
    rb -= rb.mean()
    denom = math.sqrt(float(np.dot(ra, ra)) * float(np.dot(rb, rb)))
    if denom == 0.0:
        return float("nan")
    return float(np.dot(ra, rb) / denom)


def _component_calibration(
    error: np.ndarray, sigma: np.ndarray, levels: Sequence[float]
) -> dict[str, Any]:
    """Calibration stats for one flux component over one point set."""
    n = int(error.size)
    if n == 0:
        return {"n": 0, "coverage": {}, "calibration_error": float("nan"),
                "mean_sigma": float("nan"), "rmse": float("nan"),
                "error_sigma_spearman": float("nan"),
                "mean_abs_z": float("nan"), "std_z": float("nan")}
    abs_err = np.abs(error)
    safe_sigma = np.where(sigma > 0.0, sigma, np.nan)
    z = error / safe_sigma  # standardized residual; ~N(0,1) if calibrated

    coverage = {}
    deviations = []
    for level in levels:
        zc = _z_for(level)
        empirical = float(np.mean(abs_err <= zc * sigma))
        coverage["%.4f" % level] = {
            "nominal": float(level),
            "empirical": empirical,
            "z_multiplier": zc,
            "deviation": empirical - float(level),
        }
        deviations.append(abs(empirical - float(level)))

    return {
        "n": n,
        "coverage": coverage,
        # ECE-style scalar: mean |nominal - empirical| across levels. 0 = perfect.
        "calibration_error": float(np.mean(deviations)),
        "mean_sigma": float(np.mean(sigma)),         # sharpness
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        # discrimination: does bigger sigma predict bigger |error|?
        "error_sigma_spearman": _spearman(abs_err, sigma),
        # standardized-residual moments: ~0 mean, ~1 std, ~0.8 mean|z| if calibrated
        "mean_abs_z": float(np.nanmean(np.abs(z))),
        "std_z": float(np.nanstd(z)),
    }


def evaluate_calibration(
    truth: Mapping[str, Any],
    predicted: Mapping[str, Any],
    predicted_std: Mapping[str, Any],
    regions: Sequence[str] | None = None,
    levels: Sequence[float] = _DEFAULT_LEVELS,
) -> dict[str, Any]:
    """Calibration of predictive intervals against independent frozen FEM truth.

    truth / predicted / predicted_std each provide 'lambda_d_wb' and
    'lambda_q_wb' arrays of equal length. `regions` (optional) is a per-point
    label used to report worst-region calibration. Report-only; never a gate.
    """
    components = ("lambda_d_wb", "lambda_q_wb")
    arrays = {}
    n = None
    for comp in components:
        t = np.asarray(truth[comp], dtype=np.float64).ravel()
        p = np.asarray(predicted[comp], dtype=np.float64).ravel()
        s = np.asarray(predicted_std[comp], dtype=np.float64).ravel()
        if not (t.size == p.size == s.size):
            raise ValueError(comp + ": truth/predicted/std length mismatch")
        if n is None:
            n = t.size
        elif t.size != n:
            raise ValueError("components must share length")
        if np.any(s < 0.0):
            raise ValueError(comp + ": predictive std must be non-negative")
        arrays[comp] = (p - t, s)

    levels = tuple(float(x) for x in levels)
    overall = {}
    worst_cal_err = 0.0
    for comp in components:
        error, sigma = arrays[comp]
        overall[comp] = _component_calibration(error, sigma, levels)
        if math.isfinite(overall[comp]["calibration_error"]):
            worst_cal_err = max(worst_cal_err, overall[comp]["calibration_error"])

    result: dict[str, Any] = {
        "report_only": True,
        "is_gate": False,
        "n_points": int(n or 0),
        "levels": list(levels),
        "components": overall,
        "worst_component_calibration_error": worst_cal_err,
    }

    if regions is not None:
        region_labels = np.asarray(list(regions), dtype=object).ravel()
        if region_labels.size != n:
            raise ValueError("regions length must match point count")
        by_region: dict[str, Any] = {}
        worst_region_err = 0.0
        for label in sorted(set(map(str, region_labels.tolist()))):
            mask = region_labels.astype(str) == label
            comp_block = {}
            for comp in components:
                error, sigma = arrays[comp]
                comp_block[comp] = _component_calibration(
                    error[mask], sigma[mask], levels)
                ce = comp_block[comp]["calibration_error"]
                if math.isfinite(ce):
                    worst_region_err = max(worst_region_err, ce)
            by_region[label] = comp_block
        result["by_region"] = by_region
        result["worst_region_calibration_error"] = worst_region_err

    return result
