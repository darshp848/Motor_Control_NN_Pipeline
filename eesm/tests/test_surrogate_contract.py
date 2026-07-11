"""Shared Task 4 contract for every baseline flux surrogate."""

from __future__ import annotations

import os
import json
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


def test_rbf_or_gp_enforces_256_sample_training_limit():
    X = np.zeros((256, 3), dtype=np.float64)
    y = np.zeros((256, 2), dtype=np.float64)
    build_surrogate("rbf_or_gp", seed=1701, config={}).fit(X, y)

    with pytest.raises(ValueError, match="at most 256 training samples"):
        build_surrogate("rbf_or_gp", seed=1701, config={}).fit(
            np.zeros((257, 3)), np.zeros((257, 2))
        )


@pytest.mark.parametrize(
    ("name", "required"),
    [
        ("physics_polynomial", {"polynomial_features", "ridge"}),
        ("rbf_or_gp", {"kernel", "gaussian_process_regressor"}),
        ("tree_ensemble", {"random_forest_regressor"}),
        ("compact_mlp", {"architecture", "activation", "dtype", "loss", "adam", "epochs"}),
    ],
)
def test_metadata_is_json_serializable_and_records_complete_effective_config(
    name, required, tiny_training_set, tmp_path
):
    X, y = tiny_training_set
    model = build_surrogate(name, seed=1701, config={})
    model.fit(X, y)
    metadata = model.save(str(tmp_path / name))
    json.dumps(metadata, sort_keys=True)
    effective = metadata["hyperparameters"]
    assert set(effective) == required

    if name == "physics_polynomial":
        assert effective["polynomial_features"] == {
            "degree": 2, "include_bias": False, "interaction_only": False, "order": "C"
        }
        assert {"alpha", "fit_intercept", "solver", "tol"} <= set(effective["ridge"])
    elif name == "rbf_or_gp":
        assert effective["kernel"] == {
            "composition": "ConstantKernel * RBF + WhiteKernel",
            "amplitude": 1.0,
            "amplitude_bounds": [0.001, 1000.0],
            "length_scale": 1.0,
            "length_scale_bounds": [0.001, 1000.0],
            "noise_level": 1e-6,
            "noise_level_bounds": [1e-10, 1.0],
        }
        assert {"alpha", "copy_X_train", "normalize_y", "optimizer", "random_state"} <= set(
            effective["gaussian_process_regressor"]
        )
    elif name == "tree_ensemble":
        assert effective["random_forest_regressor"] == model.model_.get_params(deep=False)
    else:
        assert effective["architecture"] == [3, 32, 32, 2]
        assert effective["adam"] == {
            "lr": 0.01, "betas": [0.9, 0.999], "eps": 1e-8,
            "weight_decay": 0, "amsgrad": False, "maximize": False,
            "foreach": None, "capturable": False, "differentiable": False,
            "fused": None, "decoupled_weight_decay": False,
        }
