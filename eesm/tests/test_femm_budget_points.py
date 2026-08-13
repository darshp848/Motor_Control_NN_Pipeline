"""Equal-budget 64/128/256 identity freeze. No FEMM solve."""

from __future__ import annotations

import json
import os
import sys

import pytest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eesm.femm import budget_points, campaign  # noqa: E402
from eesm.femm.budget_points import BudgetPointsRefusal  # noqa: E402


def test_origin_is_excluded_from_femm_points():
    assert budget_points.is_origin(0.0, 0.0, 0.0)
    assert not budget_points.is_origin(-120.0, 120.0, 15.0)


def test_region_rule_matches_task9_generated_cutoffs():
    domain = {"id_a": (-120.0, 0.0), "iq_a": (0.0, 120.0), "if_a": (0.0, 15.0)}
    assert budget_points.classify_region(-100.0, 30.0, 3.0, domain) == "field_weakening"
    assert budget_points.classify_region(-30.0, 110.0, 14.0, domain) == "saturation"
    assert budget_points.classify_region(-40.0, 40.0, 6.0, domain) == "interior"
    assert budget_points.classify_region(0.0, 60.0, 8.0, domain) == "boundary"


def test_identities_match_equal_budget_sampler(monkeypatch):
    # Import after conftest has put eesm/src on the path.
    from experiments import equal_budget

    with open(budget_points.MANIFEST_PATH, "rb") as stream:
        manifest = json.loads(stream.read())
    built = budget_points.build_equal_budget_identities(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    _, _, _, seeds = equal_budget._validate_manifest(manifest)

    assert built["n_identities"] == 1760
    assert built["n_femm_solvable"] == 1759
    assert built["origin_in_train"] is True
    assert built["role_counts_femm"]["train"] == 1247
    assert built["role_counts_femm"]["selection"] == 256
    assert built["role_counts_femm"]["scheduler_audit"] == 256

    for key, design in built["designs"].items():
        samples = equal_budget._sample_training(
            design["strategy"], domain, design["budget"], design["seed"]
        )
        expected = [str(value) for value in samples["point_id"]]
        assert design["point_ids"] == expected, key
        assert design["seed"] == equal_budget._derived_seed(
            seeds["split"], design["strategy"], design["budget"]
        )

    femm_ids = {row["point_id"] for row in built["femm_rows"]}
    assert built["origin_point_id"] not in femm_ids
    assert not any(
        budget_points.is_origin(row["id_a"], row["iq_a"], row["if_a"])
        for row in built["femm_rows"]
    )


def test_freeze_is_deterministic_and_refuses_task9(tmp_path):
    first_root = tmp_path / "freeze_a"
    second_root = tmp_path / "freeze_b"
    first = budget_points.freeze_equal_budget_points(str(first_root))
    second = budget_points.freeze_equal_budget_points(str(second_root))
    assert first["points_sha256"] == second["points_sha256"]
    assert (first_root / "frozen_points.csv").read_bytes() == (
        second_root / "frozen_points.csv"
    ).read_bytes()

    replay = budget_points.freeze_equal_budget_points(str(first_root))
    assert replay["points_sha256"] == first["points_sha256"]

    points = campaign.read_points(str(first_root / "frozen_points.csv"))
    assert len(points) == first["n_femm_solvable"]
    assert {row["role"] for row in points} == {
        "train", "selection", "scheduler_audit"
    }

    with pytest.raises(BudgetPointsRefusal, match="Task 9"):
        budget_points.freeze_equal_budget_points(budget_points.TASK9_ROOT)

    other = tmp_path / "conflict"
    other.mkdir()
    (other / "frozen_points.csv").write_text("not-the-freeze\n", encoding="ascii")
    (other / "point_freeze.json").write_text(
        json.dumps({"points_sha256": "deadbeef"}), encoding="utf-8"
    )
    with pytest.raises(BudgetPointsRefusal, match="different identity freeze"):
        budget_points.freeze_equal_budget_points(str(other))
