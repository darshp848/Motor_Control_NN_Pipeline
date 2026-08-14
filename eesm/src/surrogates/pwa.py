"""Piecewise-affine flux map: Delaunay simplices + per-simplex affine fit.

This is an as-described reimplementation, not Steyaert/Preindl's released
code. See ``eesm/docs/PWA_FIDELITY.md``. Default triangulation is in the
normalized current box used by every other family. Set
``delaunay_space='physical'`` to Delaunay the training currents in amperes,
which is what Steyaert 2023 / Parson-Scherban 2026 describe.
"""

from __future__ import annotations

import numpy as np
from scipy.spatial import Delaunay, QhullError

from surrogates.base import FluxSurrogate


class PWASurrogate(FluxSurrogate):
    """Delaunay PWA interpolant of the training cloud."""

    family = "pwa"

    def _fit_normalized(self, X: np.ndarray, y: np.ndarray) -> None:
        space = str(self.config.get("delaunay_space", "normalized"))
        if space not in {"normalized", "physical"}:
            raise ValueError("delaunay_space must be 'normalized' or 'physical'")
        self.delaunay_space_ = space
        if space == "physical":
            points = X * self.x_scale_ + self.x_mean_
            values = y * self.y_scale_ + self.y_mean_
        else:
            points = np.asarray(X, dtype=np.float64)
            values = np.asarray(y, dtype=np.float64)
        self.points_ = points
        self.values_ = values
        try:
            self.tri_ = Delaunay(self.points_)
        except QhullError:
            self.tri_ = None
            self.affines_ = None
            self.hyperparameters_ = {
                "fallback": "nearest_neighbor",
                "n_simplices": 0,
                "delaunay_space": space,
                "construction": "as_described_reimplementation",
            }
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
            "delaunay_space": space,
            "fit": "affine_least_squares_on_simplex_vertices",
            "construction": "as_described_reimplementation",
            "not_vendor_code": True,
        }

    def _to_query_space(self, X_normalized: np.ndarray) -> np.ndarray:
        if self.delaunay_space_ == "physical":
            return X_normalized * self.x_scale_ + self.x_mean_
        return np.asarray(X_normalized, dtype=np.float64)

    def _from_value_space(self, values: np.ndarray) -> np.ndarray:
        if self.delaunay_space_ == "physical":
            return (values - self.y_mean_) / self.y_scale_
        return values

    def _predict_normalized(self, X: np.ndarray) -> np.ndarray:
        query = self._to_query_space(X)
        if self.tri_ is None or self.affines_ is None:
            return self._from_value_space(self._nearest(query))
        simplex_id = self.tri_.find_simplex(query)
        out = np.empty((query.shape[0], self.values_.shape[1]), dtype=np.float64)
        for index, sid in enumerate(simplex_id):
            if sid < 0:
                out[index] = self._nearest(query[index : index + 1])[0]
                continue
            feature = np.concatenate(([1.0], query[index]))
            out[index] = feature @ self.affines_[sid]
        return self._from_value_space(out)

    def _nearest(self, query: np.ndarray) -> np.ndarray:
        out = np.empty((query.shape[0], self.values_.shape[1]), dtype=np.float64)
        for i, point in enumerate(query):
            nearest = int(np.argmin(np.linalg.norm(self.points_ - point, axis=1)))
            out[i] = self.values_[nearest]
        return out
