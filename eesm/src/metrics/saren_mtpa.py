"""Sárén-style stator MTPA residual from the forward map and L_diff.

Sarén, Hartikainen, Piippo, Hinkkanen, arXiv:2607.08528 eqs. (6)–(8):

    L = dψ/di
    ψ_a = J ψ - L J i
    e = ψ_a^T J i

J = [[0, -1], [1, 0]]. This is the 2-DOF stator condition at a frozen
field current. It is not the 3-DOF copper-loss QCQP. A nonzero e is not
itself a fault: selection points are not MTPA points. The Paper 2 metric
is the change in e (and a one-step current correction) when L and ψ
come from a surrogate instead of the FEM anchors.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from metrics.ldiff import COMPONENTS, anchor_arrays
from metrics.reciprocity import DEFAULT_STEPS, PredictFn, central_jacobian


def mtpa_residual(
    id_a: float,
    iq_a: float,
    lambda_d: float,
    lambda_q: float,
    Ldd: float,
    Ldq: float,
    Lqd: float,
    Lqq: float,
) -> float:
    """Scalar MTPA residual e = ψ_a^T J i, in Wb·A."""
    ji_d = -float(iq_a)
    ji_q = float(id_a)
    psi_a_d = -float(lambda_q) - (
        float(Ldd) * ji_d + float(Ldq) * ji_q
    )
    psi_a_q = float(lambda_d) - (
        float(Lqd) * ji_d + float(Lqq) * ji_q
    )
    return float(psi_a_d * ji_d + psi_a_q * ji_q)


def mtpa_residual_gradient(
    id_a: float,
    iq_a: float,
    lambda_d: float,
    lambda_q: float,
    Ldd: float,
    Ldq: float,
    Lqd: float,
    Lqq: float,
) -> np.ndarray:
    """φ_γ from Sárén (9) without the ∂L/∂i term they omit in practice."""
    ji = np.array([-iq_a, id_a], dtype=np.float64)
    psi = np.array([lambda_d, lambda_q], dtype=np.float64)
    L = np.array([[Ldd, Ldq], [Lqd, Lqq]], dtype=np.float64)
    j_mat = np.array([[0.0, -1.0], [1.0, 0.0]], dtype=np.float64)
    psi_a = j_mat @ psi - L @ j_mat @ np.array([id_a, iq_a], dtype=np.float64)
    phi = -j_mat @ psi_a + (j_mat @ L - L @ j_mat) @ ji
    return phi


def newton_current_step(
    id_a: float,
    iq_a: float,
    lambda_d: float,
    lambda_q: float,
    Ldd: float,
    Ldq: float,
    Lqd: float,
    Lqq: float,
) -> np.ndarray:
    """One Gauss step that drives e to 0 in the (id, iq) plane, amperes."""
    residual = mtpa_residual(id_a, iq_a, lambda_d, lambda_q, Ldd, Ldq, Lqd, Lqq)
    phi = mtpa_residual_gradient(
        id_a, iq_a, lambda_d, lambda_q, Ldd, Ldq, Lqd, Lqq
    )
    denom = float(phi @ phi)
    if denom <= 1.0e-18:
        return np.zeros(2, dtype=np.float64)
    return -residual * phi / denom


def _stator_L(jacobian: np.ndarray) -> tuple[float, float, float, float]:
    return (
        float(jacobian[0, 0]),
        float(jacobian[0, 1]),
        float(jacobian[1, 0]),
        float(jacobian[1, 1]),
    )


def compare_at_anchors(
    predict: PredictFn,
    anchors: Mapping[str, Any],
    steps: tuple[float, float, float] = DEFAULT_STEPS,
) -> dict[str, Any]:
    """Price L_diff as MTPA-residual and one-step current error vs FEM."""
    centres, measured = anchor_arrays(anchors)
    jacobian = central_jacobian(predict, centres, steps)
    flux = np.asarray(predict(centres), dtype=np.float64)
    records = []
    for row, rec in enumerate(anchors["anchors"]):
        centre = rec["centre"]
        fem_L = {name: float(rec["inductance"][name]) for name, _, _ in COMPONENTS}
        e_fem = mtpa_residual(
            centre["id_a"],
            centre["iq_a"],
            centre["lambda_d_wb"],
            centre["lambda_q_wb"],
            fem_L["Ldd"],
            fem_L["Ldq"],
            fem_L["Lqd"],
            fem_L["Lqq"],
        )
        Ldd, Ldq, Lqd, Lqq = _stator_L(jacobian[row])
        e_hat = mtpa_residual(
            centre["id_a"],
            centre["iq_a"],
            float(flux[row, 0]),
            float(flux[row, 1]),
            Ldd,
            Ldq,
            Lqd,
            Lqq,
        )
        step_hat = newton_current_step(
            centre["id_a"],
            centre["iq_a"],
            float(flux[row, 0]),
            float(flux[row, 1]),
            Ldd,
            Ldq,
            Lqd,
            Lqq,
        )
        step_fem = newton_current_step(
            centre["id_a"],
            centre["iq_a"],
            centre["lambda_d_wb"],
            centre["lambda_q_wb"],
            fem_L["Ldd"],
            fem_L["Ldq"],
            fem_L["Lqd"],
            fem_L["Lqq"],
        )
        records.append(
            {
                "point_id": rec["centre"].get("point_id"),
                "e_fem_wba": e_fem,
                "e_hat_wba": e_hat,
                "delta_e_wba": abs(e_hat - e_fem),
                "newton_di_a": float(np.linalg.norm(step_hat - step_fem)),
            }
        )
    delta_e = np.array([row["delta_e_wba"] for row in records], dtype=np.float64)
    di = np.array([row["newton_di_a"] for row in records], dtype=np.float64)
    return {
        "n_anchors": int(len(records)),
        "delta_e_rms_wba": float(np.sqrt(np.mean(delta_e**2))),
        "delta_e_max_wba": float(np.max(delta_e)),
        "newton_di_rms_a": float(np.sqrt(np.mean(di**2))),
        "newton_di_max_a": float(np.max(di)),
        "anchors": records,
    }
