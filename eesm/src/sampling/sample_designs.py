"""Sampling strategies over the synthetic EESM (id, iq, if) domain.

Strategies:
  - tensor grid
  - random (uniform, seeded)
  - Latin hypercube (SciPy when available; otherwise scrambled grid fallback)
"""

from __future__ import annotations

import csv
import os
from typing import Dict, Tuple

import numpy as np

from data.experiment_points import canonical_point_id
from synthetic.synthetic_map import MapDomain

CANONICAL_POINT_COLUMNS = (
    "point_id",
    "role",
    "source",
    "region",
    "id_a",
    "iq_a",
    "if_a",
    "lambda_d_wb",
    "lambda_q_wb",
    "solver_status",
    "converged",
    "provenance_id",
)
SAMPLE_CSV_COLUMNS = CANONICAL_POINT_COLUMNS + (
    "strategy",
    "budget",
    "seed",
)

try:
    from scipy.stats import qmc

    _HAS_SCIPY_QMC = True
except ImportError:  # pragma: no cover
    _HAS_SCIPY_QMC = False


def _domain_bounds(domain: MapDomain) -> Tuple[np.ndarray, np.ndarray]:
    low = np.array(
        [domain.id_min_a, domain.iq_min_a, domain.if_min_a], dtype=np.float64
    )
    high = np.array(
        [domain.id_max_a, domain.iq_max_a, domain.if_max_a], dtype=np.float64
    )
    return low, high


def _pack(
    points: np.ndarray,
    domain: MapDomain,
    strategy: str,
    seed: int,
) -> Dict[str, np.ndarray]:
    n = points.shape[0]
    low, high = _domain_bounds(domain)
    on_boundary = np.any(
        np.isclose(points, low, rtol=0.0, atol=1.0e-9)
        | np.isclose(points, high, rtol=0.0, atol=1.0e-9),
        axis=1,
    )
    provenance_id = f"design:{strategy}:seed={int(seed)}:budget={n}"
    return {
        "point_id": np.array(
            [canonical_point_id(*point) for point in points], dtype=object
        ),
        "role": np.full(n, "train", dtype=object),
        "source": np.full(n, "synthetic_design", dtype=object),
        "region": np.where(on_boundary, "boundary", "interior").astype(object),
        "id_a": points[:, 0].astype(np.float64),
        "iq_a": points[:, 1].astype(np.float64),
        "if_a": points[:, 2].astype(np.float64),
        "lambda_d_wb": np.full(n, None, dtype=object),
        "lambda_q_wb": np.full(n, None, dtype=object),
        "solver_status": np.full(n, "not_run", dtype=object),
        "converged": np.zeros(n, dtype=bool),
        "provenance_id": np.full(n, provenance_id, dtype=object),
        "strategy": np.array([strategy] * n, dtype=object),
        "budget": np.full(n, n, dtype=np.int64),
        "seed": np.full(n, int(seed), dtype=np.int64),
    }


def tensor_grid_samples(
    domain: MapDomain,
    n_id: int = 8,
    n_iq: int = 8,
    n_if: int = 5,
    seed: int = 0,
) -> Dict[str, np.ndarray]:
    """Full factorial tensor product grid."""
    id_vals = np.linspace(domain.id_min_a, domain.id_max_a, int(n_id))
    iq_vals = np.linspace(domain.iq_min_a, domain.iq_max_a, int(n_iq))
    if_vals = np.linspace(domain.if_min_a, domain.if_max_a, int(n_if))
    ID, IQ, IF = np.meshgrid(id_vals, iq_vals, if_vals, indexing="ij")
    pts = np.column_stack([ID.ravel(), IQ.ravel(), IF.ravel()])
    return _pack(pts, domain, "tensor_grid", seed)


def random_samples(
    domain: MapDomain,
    n: int = 500,
    seed: int = 0,
) -> Dict[str, np.ndarray]:
    """IID uniform samples in the axis-aligned box (seeded)."""
    rng = np.random.default_rng(int(seed))
    low, high = _domain_bounds(domain)
    u = rng.random((int(n), 3))
    pts = low + u * (high - low)
    return _pack(pts, domain, "random", seed)


def latin_hypercube_samples(
    domain: MapDomain,
    n: int = 500,
    seed: int = 0,
) -> Dict[str, np.ndarray]:
    """Space-filling Latin hypercube via SciPy qmc, with fallback."""
    low, high = _domain_bounds(domain)
    n = int(n)
    if _HAS_SCIPY_QMC:
        sampler = qmc.LatinHypercube(d=3, seed=int(seed))
        u = sampler.random(n=n)
        pts = qmc.scale(u, low, high)
    else:  # pragma: no cover - exercised only without SciPy
        # Deterministic scrambled stratified fallback
        rng = np.random.default_rng(int(seed))
        pts = np.zeros((n, 3), dtype=np.float64)
        for dim in range(3):
            edges = np.linspace(0.0, 1.0, n + 1)
            mids = 0.5 * (edges[:-1] + edges[1:])
            mids = mids + (rng.random(n) - 0.5) / n
            mids = np.clip(mids, 0.0, 1.0)
            rng.shuffle(mids)
            pts[:, dim] = low[dim] + mids * (high[dim] - low[dim])
    return _pack(pts, domain, "latin_hypercube", seed)


def _format_csv_value(column: str, value: object) -> str:
    if value is None:
        return ""
    if column in {"id_a", "iq_a", "if_a", "lambda_d_wb", "lambda_q_wb"}:
        numeric = float(value)
        return "" if np.isnan(numeric) else f"{numeric:.10e}"
    if column == "converged":
        return "true" if bool(value) else "false"
    if column in {"budget", "seed"}:
        return str(int(value))
    return str(value)


def write_samples_csv(path: str, samples: Dict[str, np.ndarray]) -> str:
    """Write samples with stable column order."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    n = len(samples["id_a"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(SAMPLE_CSV_COLUMNS)
        for i in range(n):
            writer.writerow(
                [_format_csv_value(column, samples[column][i]) for column in SAMPLE_CSV_COLUMNS]
            )
    return path
