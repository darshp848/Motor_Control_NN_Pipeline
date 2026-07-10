"""Training / validation CSV quality checks."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

EXPECTED_HEADER = ("Id", "Iq", "Phi_d", "Phi_q")


def load_flux_csv(path: str) -> Tuple[np.ndarray, np.ndarray, List[str]]:
    """Load Id,Iq,Phi_d,Phi_q CSV. Returns X, Y, issues."""
    issues: List[str] = []
    try:
        import pandas as pd

        df = pd.read_csv(path)
        cols = list(df.columns[:4])
        if cols != list(EXPECTED_HEADER):
            issues.append(f"header expected {EXPECTED_HEADER}, got {cols}")
        X = df[["Id", "Iq"]].to_numpy(np.float64)
        Y = df[["Phi_d", "Phi_q"]].to_numpy(np.float64)
    except Exception:
        with open(path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]
        header = lines[0].split(",")[:4]
        if header != list(EXPECTED_HEADER):
            issues.append(f"header expected {EXPECTED_HEADER}, got {header}")
        rows = np.array(
            [[float(v) for v in ln.split(",")[:4]] for ln in lines[1:]],
            dtype=np.float64,
        )
        X, Y = rows[:, :2], rows[:, 2:4]
    return X, Y, issues


def qa_flux_map(
    X: np.ndarray,
    Y: np.ndarray,
    *,
    expected_id_range: Optional[Tuple[float, float]] = None,
    expected_iq_range: Optional[Tuple[float, float]] = None,
) -> dict:
    """Return a QA report dict with issues list and basic stats."""
    issues: List[str] = []
    n = X.shape[0]
    if n == 0:
        issues.append("empty dataset")
    if np.any(~np.isfinite(X)) or np.any(~np.isfinite(Y)):
        issues.append("non-finite values present")
    # Duplicates on (Id, Iq)
    rounded = np.round(X, 9)
    _, counts = np.unique(rounded, axis=0, return_counts=True)
    n_dup = int(np.sum(counts > 1))
    if n_dup:
        issues.append(f"duplicate (Id,Iq) keys: {n_dup}")

    id_min, id_max = float(X[:, 0].min()), float(X[:, 0].max())
    iq_min, iq_max = float(X[:, 1].min()), float(X[:, 1].max())
    if expected_id_range is not None:
        if abs(id_min - expected_id_range[0]) > 1e-6 or abs(id_max - expected_id_range[1]) > 1e-6:
            issues.append(
                f"Id range [{id_min}, {id_max}] != expected {expected_id_range}"
            )
    if expected_iq_range is not None:
        if abs(iq_min - expected_iq_range[0]) > 1e-6 or abs(iq_max - expected_iq_range[1]) > 1e-6:
            issues.append(
                f"Iq range [{iq_min}, {iq_max}] != expected {expected_iq_range}"
            )

    # Physically implausible: huge flux vs current scale (soft warn only)
    if np.nanmax(np.abs(Y)) > 50.0:
        issues.append("Phi magnitude > 50 Wb (check units / scale)")

    return {
        "n_rows": int(n),
        "id_range": [id_min, id_max],
        "iq_range": [iq_min, iq_max],
        "phi_d_range": [float(Y[:, 0].min()), float(Y[:, 0].max())],
        "phi_q_range": [float(Y[:, 1].min()), float(Y[:, 1].max())],
        "n_duplicate_keys": n_dup,
        "issues": issues,
        "ok": len(issues) == 0,
    }
