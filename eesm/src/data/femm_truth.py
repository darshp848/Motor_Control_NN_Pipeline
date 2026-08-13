"""Look up FEMM campaign truth by canonical point identity."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence, Union

import numpy as np

from data.experiment_points import canonical_point_id
from synthetic.synthetic_map import MapDomain

ArrayLike = Union[float, Sequence[float], np.ndarray]
ORIGIN_ID = canonical_point_id(0.0, 0.0, 0.0)


class FemmCampaignTruth:
    """Exact (id, iq, if) -> (λd, λq) from a finished FEMM campaign CSV.

    The source-free origin is analytic zeros. Any other missing identity
    raises — the 36-cell study must not interpolate training labels.
    """

    def __init__(self, results_csv: str | Path, domain: MapDomain | None = None):
        self.results_csv = str(results_csv)
        self.domain = domain or MapDomain()
        self._flux: dict[str, tuple[float, float]] = {}
        self._roles: dict[str, str] = {}
        self._regions: dict[str, str] = {}
        self._currents: dict[str, tuple[float, float, float]] = {}
        with open(self.results_csv, newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                point_id = row["point_id"]
                self._flux[point_id] = (
                    float(row["lambda_d_wb"]),
                    float(row["lambda_q_wb"]),
                )
                self._roles[point_id] = row["role"]
                self._regions[point_id] = row["region"]
                self._currents[point_id] = (
                    float(row["id_a"]),
                    float(row["iq_a"]),
                    float(row["if_a"]),
                )
        if not self._flux:
            raise ValueError("FEMM campaign CSV has no rows")

    def flux(
        self, id_: ArrayLike, iq: ArrayLike, if_: ArrayLike
    ) -> tuple[np.ndarray, np.ndarray]:
        id_a = np.asarray(id_, dtype=np.float64)
        iq_a = np.asarray(iq, dtype=np.float64)
        if_a = np.asarray(if_, dtype=np.float64)
        shape = np.broadcast_shapes(id_a.shape, iq_a.shape, if_a.shape)
        id_a = np.broadcast_to(id_a, shape)
        iq_a = np.broadcast_to(iq_a, shape)
        if_a = np.broadcast_to(if_a, shape)
        lambda_d = np.empty(shape, dtype=np.float64)
        lambda_q = np.empty(shape, dtype=np.float64)
        for index in np.ndindex(shape):
            point_id = canonical_point_id(
                float(id_a[index]), float(iq_a[index]), float(if_a[index])
            )
            if point_id == ORIGIN_ID:
                lambda_d[index] = 0.0
                lambda_q[index] = 0.0
                continue
            try:
                pair = self._flux[point_id]
            except KeyError as exc:
                raise KeyError(
                    "no FEMM truth for %s at (%s, %s, %s)"
                    % (point_id, id_a[index], iq_a[index], if_a[index])
                ) from exc
            lambda_d[index], lambda_q[index] = pair
        return lambda_d, lambda_q

    def is_in_domain(
        self, id_: ArrayLike, iq: ArrayLike, if_: ArrayLike
    ) -> np.ndarray:
        return self.domain.contains(id_, iq, if_)

    def role_of(self, point_id: str) -> str:
        return self._roles[point_id]

    def region_of(self, point_id: str) -> str:
        return self._regions[point_id]
