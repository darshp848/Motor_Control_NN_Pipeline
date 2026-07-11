"""Baseline EESM flux-surrogate families and shared registry."""

from surrogates.base import FluxSurrogate
from surrogates.registry import build_surrogate, load_surrogate

__all__ = ["FluxSurrogate", "build_surrogate", "load_surrogate"]
