"""Training-domain labels for validation points.

Separates three questions that must not be mixed in metrics:

  - in_domain_interpolation: point strictly inside the training rectangle
    (and not within one grid step of the outer edge when boundary_steps set)
  - boundary: inside or on the rectangle but within boundary margin of edge
  - extrapolation: outside the axis-aligned training domain

Historical IPM training: Id in [-300, 0], Iq in [0, 300].
Historical off-grid set mixed Id > 0 (extrapolation) with Id <= 0.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np


class DomainLabel(str, Enum):
    IN_DOMAIN_INTERPOLATION = "in_domain_interpolation"
    BOUNDARY = "boundary"
    EXTRAPOLATION = "extrapolation"


@dataclass(frozen=True)
class TrainingDomain:
    """Axis-aligned training rectangle in current space (A)."""

    id_min: float
    id_max: float
    iq_min: float
    iq_max: float
    # Optional typical grid steps used for boundary band (A).
    id_step: Optional[float] = None
    iq_step: Optional[float] = None

    def contains(self, id_v: float, iq_v: float, atol: float = 1e-9) -> bool:
        return (
            self.id_min - atol <= id_v <= self.id_max + atol
            and self.iq_min - atol <= iq_v <= self.iq_max + atol
        )

    def to_dict(self) -> dict:
        return asdict(self)


def domain_from_training_xy(
    X: np.ndarray,
    id_step: Optional[float] = None,
    iq_step: Optional[float] = None,
) -> TrainingDomain:
    """Infer domain from training feature matrix X[:,0]=Id, X[:,1]=Iq."""
    X = np.asarray(X, dtype=np.float64)
    if X.ndim != 2 or X.shape[1] < 2:
        raise ValueError("X must be (n, >=2) with Id, Iq columns")
    ids = X[:, 0]
    iqs = X[:, 1]
    # Infer step from unique sorted values when not provided.
    if id_step is None:
        uniq = np.unique(np.round(ids, 9))
        if len(uniq) >= 2:
            id_step = float(np.min(np.diff(uniq)))
    if iq_step is None:
        uniq = np.unique(np.round(iqs, 9))
        if len(uniq) >= 2:
            iq_step = float(np.min(np.diff(uniq)))
    return TrainingDomain(
        id_min=float(ids.min()),
        id_max=float(ids.max()),
        iq_min=float(iqs.min()),
        iq_max=float(iqs.max()),
        id_step=id_step,
        iq_step=iq_step,
    )


def _distance_to_boundary(id_v: float, iq_v: float, d: TrainingDomain) -> float:
    """Chebyshev distance to the outside of the rectangle (0 if outside).

    Inside: min distance to any edge along each axis (positive).
    """
    to_id = min(id_v - d.id_min, d.id_max - id_v)
    to_iq = min(iq_v - d.iq_min, d.iq_max - iq_v)
    return float(min(to_id, to_iq))


def label_point(
    id_v: float,
    iq_v: float,
    domain: TrainingDomain,
    boundary_steps: float = 1.0,
    atol: float = 1e-9,
) -> DomainLabel:
    """Label one (Id, Iq) relative to the training domain.

    boundary_steps: multiples of grid step used as boundary band width.
    If steps are unknown, only in-domain vs extrapolation are used
    (boundary is empty unless points sit exactly on the edge within atol
    of the half-step default of 0).
    """
    if not domain.contains(id_v, iq_v, atol=atol):
        return DomainLabel.EXTRAPOLATION

    # Boundary band from inferred grid steps (default one cell).
    margin_id = 0.0
    margin_iq = 0.0
    if domain.id_step is not None and domain.id_step > 0:
        margin_id = boundary_steps * domain.id_step
    if domain.iq_step is not None and domain.iq_step > 0:
        margin_iq = boundary_steps * domain.iq_step
    margin = max(margin_id, margin_iq)

    if margin <= 0:
        # No grid metadata: treat on-edge as boundary, interior as interp.
        on_edge = (
            abs(id_v - domain.id_min) <= atol
            or abs(id_v - domain.id_max) <= atol
            or abs(iq_v - domain.iq_min) <= atol
            or abs(iq_v - domain.iq_max) <= atol
        )
        return DomainLabel.BOUNDARY if on_edge else DomainLabel.IN_DOMAIN_INTERPOLATION

    dist = _distance_to_boundary(id_v, iq_v, domain)
    # Use axis-aware margins: near edge if within that axis step.
    near_id = (id_v - domain.id_min) < margin_id or (domain.id_max - id_v) < margin_id
    near_iq = (iq_v - domain.iq_min) < margin_iq or (domain.iq_max - iq_v) < margin_iq
    if margin_id <= 0:
        near_id = False
    if margin_iq <= 0:
        near_iq = False
    if near_id or near_iq or dist < max(margin_id, margin_iq, 0.0):
        # Only mark boundary if within one step of *an* edge that has a step.
        if near_id or near_iq:
            return DomainLabel.BOUNDARY

    return DomainLabel.IN_DOMAIN_INTERPOLATION


def label_points(
    X: np.ndarray,
    domain: TrainingDomain,
    boundary_steps: float = 1.0,
) -> List[str]:
    """Return list of DomainLabel.value strings for each row of X."""
    X = np.asarray(X, dtype=np.float64)
    labels = []
    for i in range(X.shape[0]):
        labels.append(
            label_point(float(X[i, 0]), float(X[i, 1]), domain, boundary_steps).value
        )
    return labels


def default_ipm_training_domain() -> TrainingDomain:
    """Canonical IPM FEM map domain from the frozen 40x40 sweep."""
    # Id: linspace(-300, 0, 40) step 300/39; Iq: linspace(0, 300, 40) step 300/39
    step = 300.0 / 39.0
    return TrainingDomain(
        id_min=-300.0,
        id_max=0.0,
        iq_min=0.0,
        iq_max=300.0,
        id_step=step,
        iq_step=step,
    )


def count_labels(labels: Sequence[str]) -> dict:
    out = {lab.value: 0 for lab in DomainLabel}
    for lab in labels:
        out[lab] = out.get(lab, 0) + 1
    return out
