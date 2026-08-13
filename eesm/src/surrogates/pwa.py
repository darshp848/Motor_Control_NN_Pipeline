"""Piecewise-affine flux map: Delaunay simplices + per-simplex least squares."""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay, QhullError

from surrogates.base import FluxSurrogate


class PWASurrogate(FluxSurrogate):
    """Steyaert/Preindl-style PWA on the training cloud."""

    family = "pwa"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        self.points_ = np.asarray(X, dtype=np.float64)
        self.values_ = np.asarray(y, dtype=np.float64)
        try:
            self.tri_ = Delaunay(self.points_)
        except QhullError:
            self.tri_ = None
            self.affines_ = None
            self.hyperparameters_ = {"fallback": "nearest_neighbor", "n_simplices": 0}
            return
        affines = []
        for simplex in self.tri_.simplices:
            vertices = self.points_[simplex]
            design = np.column_stack([np.ones(len(simplex)), vertices])
            coef, _, _, _ = np.linalg.lstsq(design, self.values_[simplex], rcond=None)
            affines.append(coef)
        self.affines_ = np.stack(affines, axis=0)
        self.hyperparameters_ = {
            "triangulation": "delaunay",
            "n_simplices": int(self.tri_.simplices.shape[0]),
            "outside_hull": "nearest_training_vertex",
        }

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        query = np.asarray(X, dtype=np.float64)
        if self.tri_ is None or self.affines_ is None:
            return self._nearest(query)
        simplex_id = self.tri_.find_simplex(query)
        out = np.empty(
            (query.shape[0], self.values_.shape[1]), dtype=np.float64
        )
        for index, sid in enumerate(simplex_id):
            if sid < 0:
                out[index] = self._nearest(query[index:index + 1])[0]
                continue
            feature = np.concatenate(([1.0], query[index]))
            out[index] = feature @ self.affines_[sid]
        return out

    def _nearest(self, query: np.ndarray) -> np.ndarray:
        out = np.empty(
            (query.shape[0], self.values_.shape[1]), dtype=np.float64
        )
        for i, point in enumerate(query):
            nearest = int(np.argmin(np.linalg.norm(self.points_ - point, axis=1)))
            out[i] = self.values_[nearest]
        return out
