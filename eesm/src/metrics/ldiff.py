"""Incremental-inductance (L_diff) error against the FEM finite-difference anchors.

`out/eesm/femm_fd_anchors_20260813/fd_anchors.json` holds 8 centres solved with
6 offset solves each, giving a measured Jacobian

    L[o, i] = d lambda_o / d x_i,
    outputs (lambda_d, lambda_q, lambda_f_terminal), inputs (id, iq, If)

The anchors store the field row both as raw sector values (`Lfd`, `Lfq`, `Lff`)
and as terminal values (`Lfd_terminal`, ...). Surrogates in this pipeline are
trained on TERMINAL lambda_f, so the terminal row is the one to compare, and
using the raw row instead reintroduces the factor-of-four bug the anchors were
written to catch.

This is a DIAGNOSTIC. It carries no threshold and cannot gate promotion.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from metrics.reciprocity import DEFAULT_STEPS, PredictFn, central_jacobian

#: (name in the anchor record, output index, input index).
#: Output order (lambda_d, lambda_q, lambda_f_terminal); input order (id, iq, If).
COMPONENTS: tuple[tuple[str, int, int], ...] = (
    ("Ldd", 0, 0), ("Ldq", 0, 1), ("Ldf", 0, 2),
    ("Lqd", 1, 0), ("Lqq", 1, 1), ("Lqf", 1, 2),
    ("Lfd_terminal", 2, 0), ("Lfq_terminal", 2, 1), ("Lff_terminal", 2, 2),
)

#: Components that couple two different axes. Every family measured so far is
#: an order of magnitude worse on these than on the diagonal, and they are the
#: ones an incremental-inductance controller actually consumes.
OFF_DIAGONAL = ("Ldq", "Ldf", "Lqd", "Lqf", "Lfd_terminal", "Lfq_terminal")


def anchor_arrays(anchors: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    """Return anchor centres ``(n, 3)`` and measured Jacobians ``(n, 3, 3)``."""
    records = anchors["anchors"]
    centres = np.array(
        [
            [rec["centre"]["id_a"], rec["centre"]["iq_a"], rec["centre"]["if_a"]]
            for rec in records
        ],
        dtype=np.float64,
    )
    measured = np.zeros((len(records), 3, 3), dtype=np.float64)
    for row, rec in enumerate(records):
        inductance = rec["inductance"]
        for name, out_i, in_i in COMPONENTS:
            measured[row, out_i, in_i] = float(inductance[name])
    return centres, measured


def ldiff_error(
    predict: PredictFn,
    anchors: Mapping[str, Any],
    steps: tuple[float, float, float] = DEFAULT_STEPS,
) -> dict[str, Any]:
    """Compare a surrogate's Jacobian to the FEM anchors at the anchor centres.

    The surrogate Jacobian uses the same central-difference steps as the FEM
    anchors, so this measures model error rather than differencing error.

    A 2-output surrogate is scored on the stator block only; the field row is
    reported as unavailable rather than silently zero-filled.
    """
    centres, measured = anchor_arrays(anchors)
    jacobian = central_jacobian(predict, centres, steps)
    n_out = jacobian.shape[1]
    measured_block = measured[:, :n_out, :]

    per_component: dict[str, Any] = {}
    for name, out_i, in_i in COMPONENTS:
        if out_i >= n_out:
            per_component[name] = {"available": False}
            continue
        truth = measured_block[:, out_i, in_i]
        predicted = jacobian[:, out_i, in_i]
        abs_rmse = float(np.sqrt(np.mean((predicted - truth) ** 2)))
        scale = float(np.mean(np.abs(truth)))
        per_component[name] = {
            "available": True,
            "abs_rmse_h": abs_rmse,
            "scale_h": scale,
            "rel_rmse": (abs_rmse / scale) if scale > 0.0 else None,
        }

    residual = np.sqrt(np.sum((jacobian - measured_block) ** 2, axis=(1, 2)))
    magnitude = np.sqrt(np.sum(measured_block ** 2, axis=(1, 2)))
    relative = residual / magnitude

    available_off = [
        per_component[name]["rel_rmse"]
        for name in OFF_DIAGONAL
        if per_component[name].get("available") and per_component[name]["rel_rmse"]
    ]
    return {
        "n_anchors": int(centres.shape[0]),
        "n_outputs": int(n_out),
        "steps_a": list(steps),
        "per_component": per_component,
        "frobenius_rel_rmse": float(np.sqrt(np.mean(relative ** 2))),
        "frobenius_rel_max": float(np.max(relative)),
        "off_diagonal_mean_rel_rmse": (
            float(np.mean(available_off)) if available_off else None
        ),
    }
