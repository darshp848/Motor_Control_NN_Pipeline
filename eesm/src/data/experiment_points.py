"""Canonical point identities and deterministic experiment-role assignment."""

from __future__ import annotations

import hashlib
import math
from typing import Optional

import pandas as pd


CURRENT_COLUMNS = ("id_a", "iq_a", "if_a")
EXPERIMENT_ROLES = ("train", "selection", "scheduler_audit", "reference")


def _format_current(value: float) -> str:
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError("point currents must be finite")
    rounded = round(numeric, 9)
    if rounded == 0.0:
        rounded = 0.0
    return f"{rounded:.9f}"


def canonical_point_id(id_a: float, iq_a: float, if_a: float) -> str:
    """Return the frozen 16-character SHA-256 identity for three currents."""
    serialized = "|".join(_format_current(value) for value in (id_a, iq_a, if_a))
    return hashlib.sha256(serialized.encode("ascii")).hexdigest()[:16]


def assert_disjoint_roles(points: pd.DataFrame) -> None:
    """Reject duplicate rows or any point assigned to more than one role."""
    missing = {"point_id", "role"} - set(points.columns)
    if missing:
        raise ValueError(f"missing role columns: {sorted(missing)}")
    if points[["point_id", "role"]].isna().any().any():
        raise ValueError("point_id and role must be populated")

    unknown = sorted(set(points["role"]) - set(EXPERIMENT_ROLES))
    if unknown:
        raise ValueError(f"unknown experiment role: {unknown}")

    if points.duplicated(subset=["point_id", "role"]).any():
        raise ValueError("duplicate (point_id, role) row")

    roles_per_point = points.groupby("point_id", sort=False)["role"].nunique()
    overlaps = roles_per_point[roles_per_point > 1]
    if not overlaps.empty:
        raise ValueError(
            "role overlap: point_id assigned to multiple roles: "
            + ", ".join(str(point_id) for point_id in overlaps.index)
        )


def _assign_role(points: pd.DataFrame, role: str) -> pd.DataFrame:
    if not isinstance(points, pd.DataFrame):
        raise TypeError(f"{role} points must be a pandas DataFrame")
    missing = set(CURRENT_COLUMNS) - set(points.columns)
    if missing:
        raise ValueError(f"{role} points missing current columns: {sorted(missing)}")

    assigned = points.copy(deep=True)
    assigned["point_id"] = [
        canonical_point_id(id_a, iq_a, if_a)
        for id_a, iq_a, if_a in assigned.loc[:, CURRENT_COLUMNS].itertuples(
            index=False, name=None
        )
    ]
    assigned["role"] = role
    leading = ["point_id", "role"]
    return assigned.loc[:, leading + [c for c in assigned.columns if c not in leading]]


def assign_roles(
    train: pd.DataFrame,
    selection: pd.DataFrame,
    scheduler_audit: pd.DataFrame,
    reference: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Assign the frozen roles, concatenate the rows, and reject leakage."""
    role_frames = [
        _assign_role(train, "train"),
        _assign_role(selection, "selection"),
        _assign_role(scheduler_audit, "scheduler_audit"),
    ]
    if reference is not None:
        role_frames.append(_assign_role(reference, "reference"))

    assigned = pd.concat(role_frames, ignore_index=True, sort=False)
    assert_disjoint_roles(assigned)
    return assigned
