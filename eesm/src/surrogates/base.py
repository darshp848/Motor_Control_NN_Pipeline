"""Shared normalized interface and persistence for EESM flux surrogates."""

from __future__ import annotations

import hashlib
import os
import pickle
from abc import ABC, abstractmethod
from importlib.metadata import PackageNotFoundError, version
from typing import Any, Mapping

import numpy as np


def _json_safe(value: Any) -> Any:
    """Return a deterministic JSON-compatible representation."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return [_json_safe(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "get_params"):
        return {
            "type": type(value).__name__,
            "params": _json_safe(value.get_params(deep=False)),
        }
    return str(value)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_versions() -> dict[str, str]:
    versions = {}
    for package in ("numpy", "scikit-learn", "torch"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            continue
    return versions


class FluxSurrogate(ABC):
    """Base class for `(id, iq, if) -> (lambda_d, lambda_q)` models."""

    family: str

    def __init__(self, seed: int, config: Mapping[str, Any] | None = None):
        self.seed = int(seed)
        self.config = dict(config or {})
        self._fitted = False

    def fit(self, X: np.ndarray, y: np.ndarray) -> "FluxSurrogate":
        X_array = np.asarray(X, dtype=np.float64)
        y_array = np.asarray(y, dtype=np.float64)
        if X_array.ndim != 2 or X_array.shape[1] != 3:
            raise ValueError("X must have shape (n, 3)")
        if y_array.ndim != 2 or y_array.shape != (X_array.shape[0], 2):
            raise ValueError("y must have shape (n, 2)")
        if X_array.shape[0] == 0 or not (
            np.isfinite(X_array).all() and np.isfinite(y_array).all()
        ):
            raise ValueError("training data must be non-empty and finite")

        self.x_mean_ = X_array.mean(axis=0)
        self.x_scale_ = X_array.std(axis=0)
        self.x_scale_[self.x_scale_ == 0.0] = 1.0
        self.y_mean_ = y_array.mean(axis=0)
        self.y_scale_ = y_array.std(axis=0)
        self.y_scale_[self.y_scale_ == 0.0] = 1.0
        training_bytes = np.ascontiguousarray(
            np.column_stack([X_array, y_array]), dtype=np.float64
        ).tobytes()
        self.training_data_sha256_ = hashlib.sha256(training_bytes).hexdigest()
        self._fit_normalized(
            (X_array - self.x_mean_) / self.x_scale_,
            (y_array - self.y_mean_) / self.y_scale_,
        )
        self._fitted = True
        return self

    def predict(self, X: np.ndarray) -> np.ndarray:
        if not self._fitted:
            raise RuntimeError("surrogate must be fitted before prediction")
        X_array = np.asarray(X, dtype=np.float64)
        if X_array.ndim != 2 or X_array.shape[1] != 3:
            raise ValueError("X must have shape (n, 3)")
        normalized = np.asarray(
            self._predict_normalized((X_array - self.x_mean_) / self.x_scale_),
            dtype=np.float64,
        )
        if normalized.shape != (X_array.shape[0], 2):
            raise ValueError("surrogate prediction must have shape (n, 2)")
        return normalized * self.y_scale_ + self.y_mean_

    def save(self, path: str) -> dict[str, Any]:
        if not self._fitted:
            raise RuntimeError("surrogate must be fitted before saving")
        artifact_path = os.path.abspath(path)
        if not artifact_path.endswith(".pkl"):
            artifact_path += ".pkl"
        os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
        with open(artifact_path, "wb") as stream:
            pickle.dump(self, stream, protocol=pickle.HIGHEST_PROTOCOL)
        return {
            "family": self.family,
            "seed": self.seed,
            "hyperparameters": _json_safe(self.hyperparameters_),
            "training_data_sha256": self.training_data_sha256_,
            "library_versions": _package_versions(),
            "artifact_format": "python_pickle",
            "artifact_path": artifact_path,
            "artifact_sha256": _sha256_file(artifact_path),
        }

    @abstractmethod
    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        """Fit family-specific state using normalized arrays."""

    @abstractmethod
    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        """Return normalized `(lambda_d, lambda_q)` predictions."""


def load_verified_artifact(metadata: Mapping[str, Any]) -> FluxSurrogate:
    """Load a local artifact only after verifying its recorded SHA-256."""
    path = os.path.abspath(str(metadata["artifact_path"]))
    if _sha256_file(path) != metadata["artifact_sha256"]:
        raise ValueError("artifact hash mismatch")
    with open(path, "rb") as stream:
        model = pickle.load(stream)
    if not isinstance(model, FluxSurrogate):
        raise ValueError("artifact is not a FluxSurrogate")
    if model.family != metadata["family"]:
        raise ValueError("artifact family mismatch")
    return model
