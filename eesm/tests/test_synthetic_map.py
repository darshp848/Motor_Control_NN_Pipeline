"""Tests for the synthetic EESM flux map and sampling schemas."""

from __future__ import annotations

import csv
import os
import sys

import numpy as np
import pytest

# Ensure src on path when collected from repo root
_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from sampling.sample_designs import (  # noqa: E402
    SAMPLE_CSV_COLUMNS,
    latin_hypercube_samples,
    random_samples,
    tensor_grid_samples,
    write_samples_csv,
)
from synthetic.synthetic_map import (  # noqa: E402
    MapDomain,
    SyntheticEESMMap,
    load_map_from_manifest,
)


def _manifest_path() -> str:
    return os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "..",
            "configs",
            "synthetic_eesm_manifest.json",
        )
    )


EXPECTED_SAMPLE_COLUMNS = [
    "point_id",
    "role",
    "source",
    "region",
    "id_a",
    "iq_a",
    "if_a",
    "lambda_d_wb",
    "lambda_q_wb",
    "solver_status",
    "converged",
    "provenance_id",
    "strategy",
    "budget",
    "seed",
]


def test_flux_returns_finite_values():
    m = SyntheticEESMMap()
    ld, lq = m.flux_point(-50.0, 80.0, 5.0)
    assert np.isfinite(ld) and np.isfinite(lq)
    ld_a, lq_a = m.flux(
        np.array([-10.0, -50.0]),
        np.array([20.0, 80.0]),
        np.array([1.0, 10.0]),
    )
    assert np.all(np.isfinite(ld_a)) and np.all(np.isfinite(lq_a))


def test_increasing_if_increases_lambda_d():
    m = SyntheticEESMMap()
    id_, iq = -40.0, 60.0
    ld_low, _ = m.flux_point(id_, iq, 2.0)
    ld_high, _ = m.flux_point(id_, iq, 10.0)
    assert ld_high > ld_low


def test_load_from_manifest_coefficients():
    m = load_map_from_manifest(_manifest_path())
    assert m.coefficients.Mdf0 > 0
    assert m.domain.if_max_a == 15.0
    ld, lq = m.flux_point(-20.0, 40.0, 5.0)
    assert np.isfinite(ld) and np.isfinite(lq)


def test_oracle_csv_schema_stable(tmp_path):
    m = SyntheticEESMMap()
    path = tmp_path / "oracle.csv"
    m.write_oracle_csv(str(path), n_id=3, n_iq=3, n_if=2)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    assert header == [
        "id_a",
        "iq_a",
        "if_a",
        "lambda_d_wb",
        "lambda_q_wb",
    ]
    assert len(rows) == 3 * 3 * 2
    for row in rows:
        assert len(row) == 5
        assert all(np.isfinite(float(x)) for x in row)


def test_random_seed_repeatable():
    domain = MapDomain()
    a = random_samples(domain, n=100, seed=42)
    b = random_samples(domain, n=100, seed=42)
    c = random_samples(domain, n=100, seed=7)
    assert np.allclose(a["id_a"], b["id_a"])
    assert np.allclose(a["iq_a"], b["iq_a"])
    assert np.allclose(a["if_a"], b["if_a"])
    assert not np.allclose(a["id_a"], c["id_a"])


def test_sampling_functions_return_only_approved_canonical_designs():
    domain = MapDomain()
    g = tensor_grid_samples(domain, n_id=4, n_iq=3, n_if=2, seed=0)
    assert len(g["id_a"]) == 4 * 3 * 2
    assert set(g["strategy"]) == {"tensor_grid"}

    lhs = latin_hypercube_samples(domain, n=50, seed=0)
    assert len(lhs["id_a"]) == 50
    assert set(lhs["strategy"]) == {"latin_hypercube"}

    for samples, budget in ((g, 24), (lhs, 50)):
        assert list(samples) == EXPECTED_SAMPLE_COLUMNS
        assert set(samples["role"]) == {"train"}
        assert set(samples["budget"]) == {budget}
        assert len(set(samples["point_id"])) == budget


def test_samples_csv_schema_stable(tmp_path):
    domain = MapDomain()
    samples = random_samples(domain, n=5, seed=0)
    path = tmp_path / "samples.csv"
    write_samples_csv(str(path), samples)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(SAMPLE_CSV_COLUMNS)
        rows = list(reader)
    assert len(rows) == 5
    assert rows[0]["strategy"] == "random"
    assert rows[0]["budget"] == "5"


def test_domain_contains():
    m = SyntheticEESMMap()
    assert bool(m.is_in_domain(-10.0, 10.0, 5.0))
    assert not bool(m.is_in_domain(50.0, 10.0, 5.0))  # id positive OOD default
