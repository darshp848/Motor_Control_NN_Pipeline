"""Sampling strategies over the synthetic EESM (id, iq, if) domain.

Strategies:
  - tensor grid
  - random (uniform, seeded)
  - Latin hypercube (SciPy when available; otherwise scrambled grid fallback)
  - sequential / uncertainty placeholder (documented TODO)
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import numpy as np

from synthetic.synthetic_map import MapDomain, SyntheticEESMMap

SAMPLE_CSV_COLUMNS = (
    "id_a",
    "iq_a",
    "if_a",
    "strategy",
    "seed",
    "sample_id",
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
    strategy: str,
    seed: int,
) -> Dict[str, np.ndarray]:
    n = points.shape[0]
    return {
        "id_a": points[:, 0].astype(np.float64),
        "iq_a": points[:, 1].astype(np.float64),
        "if_a": points[:, 2].astype(np.float64),
        "strategy": np.array([strategy] * n, dtype=object),
        "seed": np.full(n, int(seed), dtype=np.int64),
        "sample_id": np.arange(n, dtype=np.int64),
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
    return _pack(pts, "tensor_grid", seed)


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
    return _pack(pts, "random", seed)


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
        strategy = "latin_hypercube"
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
        strategy = "latin_hypercube_fallback"
    return _pack(pts, strategy, seed)


def sequential_uncertainty_placeholder(
    domain: MapDomain,
    n: int = 50,
    seed: int = 0,
    map_model: Optional[SyntheticEESMMap] = None,
) -> Dict[str, np.ndarray]:
    """Placeholder for active / uncertainty-driven sequential design.

    TODO(stage1+): implement acquisition (e.g. predictive variance from a GP
    or ensemble disagreement) to pick the next FEM-like query points.
    For now, returns a seeded random subset tagged as sequential_placeholder.
    """
    _ = map_model  # reserved for future uncertainty model
    base = random_samples(domain, n=n, seed=seed)
    base["strategy"] = np.array(
        ["sequential_placeholder"] * int(n), dtype=object
    )
    return base


def write_samples_csv(path: str, samples: Dict[str, np.ndarray]) -> str:
    """Write samples with stable column order."""
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    n = len(samples["id_a"])
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(",".join(SAMPLE_CSV_COLUMNS) + "\n")
        for i in range(n):
            row = [
                f"{float(samples['id_a'][i]):.10e}",
                f"{float(samples['iq_a'][i]):.10e}",
                f"{float(samples['if_a'][i]):.10e}",
                str(samples["strategy"][i]),
                str(int(samples["seed"][i])),
                str(int(samples["sample_id"][i])),
            ]
            f.write(",".join(row) + "\n")
    return path
