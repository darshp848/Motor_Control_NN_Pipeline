"""Physics-feature polynomial baseline for normalized EESM flux data."""

from __future__ import annotations

import numpy as np
from sklearn.linear_model import Ridge
from sklearn.preprocessing import PolynomialFeatures

from surrogates.base import FluxSurrogate


class PhysicsPolynomialSurrogate(FluxSurrogate):
    family = "physics_polynomial"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        degree = int(self.config.get("degree", 2))
        alpha = float(self.config.get("alpha", 1.0e-6))
        self.hyperparameters_ = {"degree": degree, "alpha": alpha}
        self.features_ = PolynomialFeatures(degree=degree, include_bias=False)
        transformed = self.features_.fit_transform(X)
        self.model_ = Ridge(alpha=alpha)
        self.model_.fit(transformed, y)

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        return self.model_.predict(self.features_.transform(X))
