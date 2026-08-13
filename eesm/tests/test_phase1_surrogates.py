"""Phase 1 energy-gradient and PWA families. No FEMM."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from surrogates.registry import build_surrogate

EESM_ROOT = Path(__file__).resolve().parents[1]


def _linear_data(n: int = 40, seed: int = 0):
    rng = np.random.default_rng(seed)
    id_a = rng.uniform(-80.0, -10.0, n)
    iq_a = rng.uniform(10.0, 80.0, n)
    if_a = rng.uniform(1.0, 10.0, n)
    X = np.column_stack([id_a, iq_a, if_a])
    y = np.column_stack([0.004 * id_a + 0.005 * if_a, 0.002 * iq_a])
    return X, y


def test_registry_builds_phase1_families():
    assert build_surrogate("energy_gradient_net", 1).family == "energy_gradient_net"
    assert build_surrogate("pwa", 1).family == "pwa"


def test_pwa_interpolates_training_vertices():
    X, y = _linear_data(24)
    model = build_surrogate("pwa", 0)
    model.fit(X, y)
    pred = model.predict(X)
    assert pred == pytest.approx(y, abs=1e-8)


def test_energy_net_fits_a_linear_map():
    X, y = _linear_data(48, seed=1)
    model = build_surrogate(
        "energy_gradient_net", 0, {"epochs": 250, "hidden_width": 24}
    )
    model.fit(X, y)
    pred = model.predict(X)
    rmse = float(np.sqrt(np.mean((pred - y) ** 2)))
    assert rmse < 0.05


def test_v2_manifest_keeps_frozen_gates_and_adds_families():
    v1 = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    v2 = json.loads(
        (EESM_ROOT / "configs" / "eesm_experiment_manifest_v2.json").read_text(
            encoding="utf-8"
        )
    )
    assert v1["gates"]["thresholds"] == v2["gates"]["thresholds"]
    assert v1["gates"]["status"] == v2["gates"]["status"] == "frozen"
    assert "energy_gradient_net" in v2["surrogates"]
    assert "pwa" in v2["surrogates"]
    assert v1["surrogates"] == [
        "physics_polynomial",
        "rbf_or_gp",
        "tree_ensemble",
        "compact_mlp",
    ]
