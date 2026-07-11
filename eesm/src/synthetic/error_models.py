"""Deterministic output-level corruptions for synthetic sensitivity tests."""

from __future__ import annotations

from typing import Sequence, Union

import numpy as np

ArrayLike = Union[float, Sequence[float], np.ndarray]


def inject_flux_error(
    lambda_d: ArrayLike,
    lambda_q: ArrayLike,
    kind: str,
    magnitude: float,
    currents: ArrayLike,
) -> tuple[np.ndarray, np.ndarray]:
    """Return corrupted flux arrays without changing the underlying oracle."""
    ld, lq = np.broadcast_arrays(
        np.asarray(lambda_d, dtype=np.float64),
        np.asarray(lambda_q, dtype=np.float64),
    )
    current_array = np.asarray(currents, dtype=np.float64)
    if current_array.shape != ld.shape + (3,):
        raise ValueError("currents must have shape lambda_d.shape + (3,)")
    scale = float(magnitude)
    if not np.isfinite(scale) or not 0.0 <= scale <= 1.0:
        raise ValueError("magnitude must be finite and between zero and one")

    if kind == "d_bias":
        return ld + scale, lq.copy()
    if kind == "q_gain":
        return ld.copy(), lq * (1.0 + scale)
    if kind == "saturation_local":
        # Normalize by the frozen Stage 1 synthetic current-domain spans. This
        # keeps the corruption output-only while concentrating it at high load.
        normalized = current_array / np.array([120.0, 120.0, 15.0])
        locality = np.clip(np.mean(normalized * normalized, axis=-1), 0.0, 1.0)
        attenuation = 1.0 - scale * locality
        return ld * attenuation, lq * attenuation
    if kind == "cross_coupling":
        return ld + scale * lq, lq + scale * ld
    raise ValueError(f"unsupported flux error kind: {kind}")
