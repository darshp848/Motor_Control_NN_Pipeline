"""Tests for canonical EESM point IDs and disjoint dataset roles."""

from __future__ import annotations

import hashlib

import pandas as pd
import pytest

from data.experiment_points import (
    assign_roles,
    assert_disjoint_roles,
    canonical_point_id,
)


def test_point_id_is_stable_to_csv_precision():
    expected = hashlib.sha256(
        b"-10.000000000|20.000000000|3.000000000"
    ).hexdigest()[:16]

    assert canonical_point_id(-10.0, 20.0, 3.0) == expected
    assert canonical_point_id(-10.00000000001, 20.0, 3.0) == expected


def test_role_overlap_is_rejected():
    points = pd.DataFrame(
        [
            {"point_id": "p1", "role": "train"},
            {"point_id": "p1", "role": "selection"},
        ]
    )

    with pytest.raises(ValueError, match="role overlap"):
        assert_disjoint_roles(points)


def test_duplicate_point_role_row_is_rejected():
    points = pd.DataFrame(
        [
            {"point_id": "p1", "role": "train"},
            {"point_id": "p1", "role": "train"},
        ]
    )

    with pytest.raises(ValueError, match="duplicate"):
        assert_disjoint_roles(points)


def test_assign_roles_adds_stable_ids_and_frozen_roles():
    train = pd.DataFrame(
        [{"id_a": -10.0, "iq_a": 20.0, "if_a": 3.0, "source": "synthetic"}]
    )
    selection = pd.DataFrame(
        [{"id_a": -20.0, "iq_a": 30.0, "if_a": 4.0, "source": "synthetic"}]
    )
    audit = pd.DataFrame(
        [{"id_a": -30.0, "iq_a": 40.0, "if_a": 5.0, "source": "synthetic"}]
    )
    reference = pd.DataFrame(
        [{"id_a": -40.0, "iq_a": 50.0, "if_a": 6.0, "source": "synthetic"}]
    )

    assigned = assign_roles(train, selection, audit, reference)

    assert assigned["role"].tolist() == [
        "train",
        "selection",
        "scheduler_audit",
        "reference",
    ]
    assert assigned["point_id"].tolist() == [
        canonical_point_id(-10.0, 20.0, 3.0),
        canonical_point_id(-20.0, 30.0, 4.0),
        canonical_point_id(-30.0, 40.0, 5.0),
        canonical_point_id(-40.0, 50.0, 6.0),
    ]


def test_assign_roles_rejects_cross_role_current_overlap():
    point = {"id_a": -10.0, "iq_a": 20.0, "if_a": 3.0}

    with pytest.raises(ValueError, match="role overlap"):
        assign_roles(
            pd.DataFrame([point]),
            pd.DataFrame([point]),
            pd.DataFrame([{"id_a": -30.0, "iq_a": 40.0, "if_a": 5.0}]),
        )
