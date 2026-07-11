"""Gaussian-process baseline for normalized EESM flux data."""

from __future__ import annotations

import numpy as np
from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import ConstantKernel, RBF, WhiteKernel

from .base import FluxSurrogate


class RBFOrGPSurrogate(FluxSurrogate):
    """RBF-kernel Gaussian process intended for small training budgets."""

    family = "rbf_or_gp"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        if X.shape[0] > 256:
            raise ValueError("rbf_or_gp supports at most 256 training samples")
        length_scale = self.config.get("length_scale", 1.0)
        noise_level = float(self.config.get("noise_level", 1e-6))
        alpha = float(self.config.get("alpha", 1e-10))
        optimizer = self.config.get("optimizer", None)
        n_restarts = int(self.config.get("n_restarts_optimizer", 0))
        kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(
            length_scale=length_scale,
            length_scale_bounds=(1e-3, 1e3),
        ) + WhiteKernel(
            noise_level=noise_level,
            noise_level_bounds=(1e-10, 1e0),
        )
        self.model_ = GaussianProcessRegressor(
            kernel=kernel,
            alpha=alpha,
            normalize_y=False,
            optimizer=optimizer,
            n_restarts_optimizer=n_restarts,
            random_state=self.seed,
        )
        self.model_.fit(X, y)
        self.hyperparameters_ = {
            "kernel": {
                "composition": "ConstantKernel * RBF + WhiteKernel",
                "amplitude": 1.0,
                "amplitude_bounds": [1e-3, 1e3],
                "length_scale": length_scale,
                "length_scale_bounds": [1e-3, 1e3],
                "noise_level": noise_level,
                "noise_level_bounds": [1e-10, 1.0],
            },
            "gaussian_process_regressor": self.model_.get_params(deep=False),
        }

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        return np.asarray(self.model_.predict(X), dtype=np.float64)
