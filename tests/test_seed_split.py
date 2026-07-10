"""Seeded train/val/test split reproducibility."""

import numpy as np

import train_flux_map_comparison as T


def test_seed_split_reproducible():
    rng = np.random.default_rng(42)
    X = rng.normal(size=(100, 2))
    Y = rng.normal(size=(100, 2))
    a = T.train_val_test_split(X, Y, seed=0)
    b = T.train_val_test_split(X, Y, seed=0)
    c = T.train_val_test_split(X, Y, seed=1)
    # indices
    assert np.array_equal(a[3], b[3])
    assert np.array_equal(a[4], b[4])
    assert np.array_equal(a[5], b[5])
    assert not np.array_equal(a[3], c[3])


def test_seed_split_sizes():
    X = np.zeros((200, 2))
    Y = np.zeros((200, 2))
    (Xtr, _), (Xva, _), (Xte, _), tr, va, te = T.train_val_test_split(
        X, Y, seed=0, val_frac=0.15, test_frac=0.15
    )
    assert len(tr) + len(va) + len(te) == 200
    assert abs(len(va) / 200 - 0.15) < 0.05
    assert abs(len(te) / 200 - 0.15) < 0.05
