"""Shared Task 4 contract for every baseline flux surrogate."""

from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pytest

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from surrogates.registry import build_surrogate, load_surrogate  # noqa: E402


@pytest.fixture
def tiny_training_set():
    rng = np.random.default_rng(20260710)
    X = np.column_stack(
        [
            rng.uniform(-120.0, 0.0, 32),
            rng.uniform(0.0, 120.0, 32),
            rng.uniform(0.0, 15.0, 32),
        ]
    )
    id_a, iq_a, if_a = X.T
    y = np.column_stack(
        [
            0.0012 * id_a + 0.018 * if_a + 0.00015 * iq_a,
            0.0020 * iq_a - 0.00015 * id_a + 0.00008 * if_a,
        ]
    )
    return X, y


@pytest.mark.parametrize(
    "name",
    ["physics_polynomial", "rbf_or_gp", "tree_ensemble", "compact_mlp"],
)
def test_surrogate_fit_predict_save_load(name, tiny_training_set, tmp_path):
    X, y = tiny_training_set
    model = build_surrogate(name, seed=1701, config={})
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        returned = model.fit(X, y)
    assert returned is model

    pred = model.predict(X[:4])
    assert pred.shape == (4, 2)
    assert np.isfinite(pred).all()

    metadata = model.save(str(tmp_path / name))
    assert metadata["family"] == name
    assert metadata["seed"] == 1701
    assert metadata["hyperparameters"]
    assert metadata["training_data_sha256"]
    assert metadata["artifact_sha256"]
    assert metadata["library_versions"]

    restored = load_surrogate(metadata)
    np.testing.assert_allclose(
        restored.predict(X[:4]), pred, rtol=1e-6, atol=1e-9
    )


def test_surrogate_load_rejects_artifact_hash_mismatch(
    tiny_training_set, tmp_path
):
    X, y = tiny_training_set
    model = build_surrogate("physics_polynomial", seed=1701, config={})
    model.fit(X, y)
    metadata = model.save(str(tmp_path / "polynomial"))

    with open(metadata["artifact_path"], "ab") as artifact:
        artifact.write(b"tampered")

    with pytest.raises(ValueError, match="artifact hash mismatch"):
        load_surrogate(metadata)
