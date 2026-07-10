"""Deterministic synthetic EESM flux map: (id, iq, if) -> (lambda_d, lambda_q).

Physically motivated (not a real machine):
  - field current increases d-axis flux (mutual Mdf * if)
  - soft saturation at high stator / field current
  - d/q cross-coupling and q/field coupling
  - smooth rational saturation for optimizers

Units:
  currents in A (peak dq, field DC A), flux in Wb.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np

ArrayLike = Union[float, Sequence[float], np.ndarray]


@dataclass
class MapCoefficients:
    """Configurable linear + saturation coefficients."""

    Ld0: float = 0.0012
    Lq0: float = 0.0020
    Mdf0: float = 0.018
    L_cross_dq: float = 0.00015
    L_cross_qf: float = 0.00008
    sat_d: float = 8.0e-6
    sat_q: float = 6.0e-6
    sat_f: float = 4.0e-3
    lambda_d_offset: float = 0.0
    lambda_q_offset: float = 0.0


@dataclass
class MapDomain:
    """Axis-aligned current domain for sampling and domain checks."""

    id_min_a: float = -120.0
    id_max_a: float = 0.0
    iq_min_a: float = 0.0
    iq_max_a: float = 120.0
    if_min_a: float = 0.0
    if_max_a: float = 15.0

    def contains(
        self,
        id_: ArrayLike,
        iq: ArrayLike,
        if_: ArrayLike,
        tol: float = 1e-9,
    ) -> np.ndarray:
        id_a = np.asarray(id_, dtype=np.float64)
        iq_a = np.asarray(iq, dtype=np.float64)
        if_a = np.asarray(if_, dtype=np.float64)
        return (
            (id_a >= self.id_min_a - tol)
            & (id_a <= self.id_max_a + tol)
            & (iq_a >= self.iq_min_a - tol)
            & (iq_a <= self.iq_max_a + tol)
            & (if_a >= self.if_min_a - tol)
            & (if_a <= self.if_max_a + tol)
        )

    def as_dict(self) -> Dict[str, float]:
        return asdict(self)


@dataclass
class SyntheticEESMMap:
    """Smooth synthetic (id, iq, if) -> (lambda_d, lambda_q) map."""

    coefficients: MapCoefficients = field(default_factory=MapCoefficients)
    domain: MapDomain = field(default_factory=MapDomain)
    name: str = "synthetic_eesm_v0"

    def flux(
        self,
        id_: ArrayLike,
        iq: ArrayLike,
        if_: ArrayLike,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return (lambda_d, lambda_q) with broadcast-friendly arrays."""
        id_a = np.asarray(id_, dtype=np.float64)
        iq_a = np.asarray(iq, dtype=np.float64)
        if_a = np.asarray(if_, dtype=np.float64)
        c = self.coefficients

        # Soft saturation factors in (0, 1]: L_eff = L0 / (1 + alpha * i^2)
        sat_id = 1.0 / (1.0 + c.sat_d * id_a * id_a)
        sat_iq = 1.0 / (1.0 + c.sat_q * iq_a * iq_a)
        sat_if = 1.0 / (1.0 + c.sat_f * if_a * if_a)
        sat_cross = sat_id * sat_iq * sat_if

        # d-axis: self inductance + field mutual + cross from iq
        lambda_d = (
            c.Ld0 * sat_id * id_a
            + c.Mdf0 * sat_if * if_a
            + c.L_cross_dq * sat_cross * iq_a
            + c.lambda_d_offset
        )
        # q-axis: self inductance + reverse cross from id + field cross
        lambda_q = (
            c.Lq0 * sat_iq * iq_a
            - c.L_cross_dq * sat_cross * id_a
            + c.L_cross_qf * sat_if * if_a * np.sign(iq_a + 1e-30)
            + c.lambda_q_offset
        )
        return lambda_d, lambda_q

    def flux_point(
        self, id_: float, iq: float, if_: float
    ) -> Tuple[float, float]:
        ld, lq = self.flux(id_, iq, if_)
        return float(np.asarray(ld)), float(np.asarray(lq))

    def is_in_domain(
        self, id_: ArrayLike, iq: ArrayLike, if_: ArrayLike
    ) -> np.ndarray:
        return self.domain.contains(id_, iq, if_)

    def generate_oracle_grid(
        self,
        n_id: int = 21,
        n_iq: int = 21,
        n_if: int = 11,
    ) -> Dict[str, np.ndarray]:
        """Dense tensor grid for validation / later surrogate training."""
        d = self.domain
        id_vals = np.linspace(d.id_min_a, d.id_max_a, int(n_id))
        iq_vals = np.linspace(d.iq_min_a, d.iq_max_a, int(n_iq))
        if_vals = np.linspace(d.if_min_a, d.if_max_a, int(n_if))
        ID, IQ, IF = np.meshgrid(id_vals, iq_vals, if_vals, indexing="ij")
        id_flat = ID.ravel()
        iq_flat = IQ.ravel()
        if_flat = IF.ravel()
        ld, lq = self.flux(id_flat, iq_flat, if_flat)
        return {
            "id_a": id_flat,
            "iq_a": iq_flat,
            "if_a": if_flat,
            "lambda_d_wb": ld,
            "lambda_q_wb": lq,
        }

    def write_oracle_csv(
        self,
        path: str,
        n_id: int = 21,
        n_iq: int = 21,
        n_if: int = 11,
    ) -> str:
        """Write dense oracle CSV with a stable schema."""
        grid = self.generate_oracle_grid(n_id=n_id, n_iq=n_iq, n_if=n_if)
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        header = "id_a,iq_a,if_a,lambda_d_wb,lambda_q_wb\n"
        data = np.column_stack(
            [
                grid["id_a"],
                grid["iq_a"],
                grid["if_a"],
                grid["lambda_d_wb"],
                grid["lambda_q_wb"],
            ]
        )
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(header)
            np.savetxt(f, data, delimiter=",", fmt="%.10e")
        return path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "coefficients": asdict(self.coefficients),
            "domain": self.domain.as_dict(),
            "map": "(id, iq, if) -> (lambda_d, lambda_q)",
            "units": {"current": "A", "flux": "Wb"},
        }


def load_map_from_manifest(
    manifest_path: Optional[str] = None,
    manifest: Optional[dict] = None,
) -> SyntheticEESMMap:
    """Build map from JSON manifest coefficients + domain."""
    if manifest is None:
        if manifest_path is None:
            root = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..")
            )
            manifest_path = os.path.join(
                root, "configs", "synthetic_eesm_manifest.json"
            )
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    coef = MapCoefficients(**manifest.get("synthetic_map_coefficients", {}))
    dom_raw = manifest.get("map_domain", {})
    domain = MapDomain(
        id_min_a=float(dom_raw.get("id_min_a", -120.0)),
        id_max_a=float(dom_raw.get("id_max_a", 0.0)),
        iq_min_a=float(dom_raw.get("iq_min_a", 0.0)),
        iq_max_a=float(dom_raw.get("iq_max_a", 120.0)),
        if_min_a=float(dom_raw.get("if_min_a", 0.0)),
        if_max_a=float(dom_raw.get("if_max_a", 15.0)),
    )
    return SyntheticEESMMap(coefficients=coef, domain=domain)
