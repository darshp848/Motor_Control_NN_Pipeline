"""Construction and verified loading for baseline EESM flux surrogates."""

from __future__ import annotations

from typing import Any, Mapping

from surrogates.base import FluxSurrogate, load_verified_artifact
from surrogates.kernel import RBFOrGPSurrogate
from surrogates.mlp import CompactMLPSurrogate
from surrogates.polynomial import PhysicsPolynomialSurrogate
from surrogates.tree import TreeEnsembleSurrogate

_SURROGATES: dict[str, type[FluxSurrogate]] = {
    "physics_polynomial": PhysicsPolynomialSurrogate,
    "rbf_or_gp": RBFOrGPSurrogate,
    "tree_ensemble": TreeEnsembleSurrogate,
    "compact_mlp": CompactMLPSurrogate,
}


def build_surrogate(
    name: str, seed: int, config: Mapping[str, Any] | None = None
) -> FluxSurrogate:
    """Build one registered baseline surrogate family."""
    try:
        surrogate_class = _SURROGATES[name]
    except KeyError as exc:
        raise ValueError(f"unknown surrogate family: {name}") from exc
    return surrogate_class(seed=seed, config=config)


def load_surrogate(metadata: Mapping[str, Any]) -> FluxSurrogate:
    """Verify and restore a persisted surrogate artifact."""
    return load_verified_artifact(metadata)

