"""Tests for the equal-tuning-budget runner's protocol-critical helpers.

These pin the parts of the protocol that would silently corrupt a comparison if
they drifted: how configurations are drawn, how a small search space is
detected, and that inner folds partition the training design exactly.
"""

from __future__ import annotations

import importlib.util
import os

import numpy as np
import pytest

_EESM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "run_equal_tuning", os.path.join(_EESM, "run_equal_tuning.py"))
ret = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ret)


def test_choice_and_fixed_values_are_drawn_as_declared():
    rng = np.random.default_rng(0)
    space = {"a": {"type": "choice", "values": [1, 2, 3]}, "b": "fixed"}
    for _ in range(50):
        c = ret.sample_config(space, rng)
        assert c["a"] in (1, 2, 3)
        assert c["b"] == "fixed"


def test_loguniform_stays_inside_its_declared_interval():
    rng = np.random.default_rng(1)
    space = {"lr": {"type": "loguniform", "low": 1e-3, "high": 3e-2}}
    v = [ret.sample_config(space, rng)["lr"] for _ in range(200)]
    assert min(v) >= 1e-3 and max(v) <= 3e-2
    # log-spaced, so the lower decade must be well populated
    assert sum(x < 3e-3 for x in v) > 20


def test_ard_becomes_a_three_vector_length_scale_not_a_kwarg():
    rng = np.random.default_rng(2)
    c = ret.sample_config({"length_scale": 2.0, "ard": True}, rng)
    assert "ard" not in c, "ard must not reach the surrogate as a kwarg"
    assert c["length_scale"] == [2.0, 2.0, 2.0]
    c2 = ret.sample_config({"length_scale": 2.0, "ard": False}, rng)
    assert c2["length_scale"] == 2.0


def test_unknown_spec_is_rejected_rather_than_guessed():
    with pytest.raises(ValueError):
        ret.sample_config({"x": {"type": "beta", "a": 1}}, np.random.default_rng(0))


def test_space_size_counts_finite_spaces_and_flags_continuous_ones():
    assert ret.enumerate_space_size(
        {"a": {"type": "choice", "values": [1, 2]},
         "b": {"type": "choice", "values": [1, 2, 3]}}) == 6
    assert ret.enumerate_space_size({}) == 1          # pwa: no hyperparameters
    assert ret.enumerate_space_size(
        {"a": {"type": "loguniform", "low": 1e-3, "high": 1.0}}) == float("inf")


def test_config_key_is_order_independent():
    assert ret.config_key({"a": 1, "b": 2}) == ret.config_key({"b": 2, "a": 1})


@pytest.mark.parametrize("n,k", [(64, 3), (128, 3), (256, 3), (17, 2)])
def test_inner_folds_partition_the_design_exactly(n, k):
    folds = ret.kfold_indices(n, k, seed=20260710)
    assert len(folds) == k
    allidx = np.concatenate(folds)
    assert sorted(allidx.tolist()) == list(range(n)), "folds must partition"
    assert len({tuple(f) for f in folds}) == k
    assert all(len(f) > 0 for f in folds)


def test_inner_folds_are_deterministic_given_the_seed():
    a = ret.kfold_indices(128, 3, seed=7)
    b = ret.kfold_indices(128, 3, seed=7)
    c = ret.kfold_indices(128, 3, seed=8)
    assert all(np.array_equal(x, y) for x, y in zip(a, b))
    assert not all(np.array_equal(x, y) for x, y in zip(a, c))


def test_git_helper_never_raises_where_git_is_absent(monkeypatch):
    """A missing repository must not discard a completed run."""
    def boom(*a, **k):
        raise FileNotFoundError("no git")
    monkeypatch.setattr(ret.subprocess, "run", boom)
    assert ret._git("rev-parse", "HEAD") is None
