"""Random-forest flux surrogate."""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import RandomForestRegressor

from .base import FluxSurrogate


class TreeEnsembleSurrogate(FluxSurrogate):
    """Deterministic random-forest baseline for normalized flux targets."""

    family = "tree_ensemble"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        self.hyperparameters_ = {
            "n_estimators": int(self.config.get("n_estimators", 100)),
            "max_depth": self.config.get("max_depth", None),
            "min_samples_leaf": int(self.config.get("min_samples_leaf", 1)),
        }
        self.model_ = RandomForestRegressor(
            random_state=self.seed,
            **self.hyperparameters_,
        )
        self.model_.fit(X, y)

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        return self.model_.predict(X)
