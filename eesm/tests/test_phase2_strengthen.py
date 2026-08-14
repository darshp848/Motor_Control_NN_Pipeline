"""Phase 2 identity and seed-replication contracts. No FEMM launch."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experiments import equal_budget
from experiments.phase2_strengthen import (
    N_BOUNDARY,
    N_DESIGN_REPLICATES,
    PHASE2_THRESHOLDS,
    FittedSurrogateMap,
    build_boundary_set,
    build_design_replicates,
    build_scheduler_commands,
    build_wst360_set,
    classify_region,
    design_replicate_seed,
    model_replicate_seeds,
    phase0_sample_seed,
    run_seed_replication,
    write_freeze,
)
from surrogates.registry import build_surrogate
from synthetic.synthetic_map import SyntheticEESMMap


EESM_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = EESM_ROOT / "configs" / "eesm_experiment_manifest.json"


def _manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_replicate_zero_matches_phase0_design_seed() -> None:
    manifest = _manifest()
    split = manifest["seeds"]["split"]
    for strategy in manifest["sampling"]["baseline_strategies"]:
        for budget in manifest["budgets"]:
            assert design_replicate_seed(split, strategy, budget, 0) == (
                phase0_sample_seed(split, strategy, budget)
            )
            if strategy in {"random", "latin_hypercube"}:
                other = design_replicate_seed(split, strategy, budget, 1)
                assert other != phase0_sample_seed(split, strategy, budget)


def test_model_seeds_include_original_and_are_unique() -> None:
    seeds = model_replicate_seeds(1701, 5)
    assert seeds[0] == 1701
    assert len(set(seeds)) == 5


def test_new_designs_do_not_overlap_reserved_roles() -> None:
    manifest = _manifest()
    built = build_design_replicates(manifest, n_replicates=N_DESIGN_REPLICATES)
    reserved = set(built["reserved"]["selection"]) | set(
        built["reserved"]["scheduler_audit"]
    )
    new_ids = {row["point_id"] for row in built["new_femm_rows"]}
    assert not (new_ids & reserved)
    assert built["n_new_unique_femm"] == len(new_ids)
    assert any(key.endswith("|r1") for key in built["designs"])
    assert not any(key.startswith("tensor_grid|") and "|r1" in key for key in built["designs"])


def test_boundary_set_is_labeled_boundary_and_disjoint() -> None:
    manifest = _manifest()
    domain = equal_budget._domain_from_manifest(manifest)
    built = build_design_replicates(manifest, n_replicates=1)
    reserved = set(built["reserved"]["selection"]) | set(
        built["reserved"]["scheduler_audit"]
    )
    rows = build_boundary_set(domain, reserved)
    assert len(rows) == N_BOUNDARY
    bounds = {
        "id_a": (domain.id_min_a, domain.id_max_a),
        "iq_a": (domain.iq_min_a, domain.iq_max_a),
        "if_a": (domain.if_min_a, domain.if_max_a),
    }
    ids = [row["point_id"] for row in rows]
    assert len(ids) == len(set(ids))
    assert not (set(ids) & reserved)
    for row in rows:
        assert classify_region(row["id_a"], row["iq_a"], row["if_a"], bounds) == (
            "boundary"
        )


def test_scheduler_commands_are_sixty_four_and_cover_regimes() -> None:
    commands = build_scheduler_commands()
    assert len(commands) == 64
    regimes = {row["regime"] for row in commands}
    assert regimes >= {
        "mtpa_like",
        "high_torque",
        "field_weakening",
        "voltage_boundary",
        "near_rated",
    }
    assert max(row["torque_nm"] for row in commands) == 31.83
    assert max(row["rpm_mech"] for row in commands) == 9000.0


def test_wst_set_samples_campaign_regions() -> None:
    campaign = []
    regions = ["interior", "field_weakening", "saturation", "boundary"]
    for region in regions:
        for index in range(12):
            campaign.append(
                {
                    "point_id": f"{region}_{index:02d}",
                    "region": region,
                    "id_a": "-10.0",
                    "iq_a": "20.0",
                    "if_a": "3.0",
                }
            )
    rows = build_wst360_set(campaign, n_points=40)
    assert len(rows) == 40
    assert {row["region"] for row in rows} == set(regions)


def test_phase2_torque_threshold_is_five_percent_rated() -> None:
    assert abs(PHASE2_THRESHOLDS["torque"] - 0.05 * 31.83) < 1e-12


def test_seed_replication_smoke_on_synthetic(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["budgets"] = [16]
    manifest["sampling"] = {
        "baseline_strategies": ["tensor_grid", "random"]
    }
    manifest["surrogates"] = ["compact_mlp", "tree_ensemble"]
    manifest["surrogate_configs"] = {
        "compact_mlp": {"hidden_width": 8, "epochs": 5, "learning_rate": 0.05},
        "tree_ensemble": {"n_estimators": 8},
    }
    domain = equal_budget._domain_from_manifest(manifest)
    selection = equal_budget.latin_hypercube_samples(domain, n=16, seed=11)
    summary = run_seed_replication(
        manifest,
        SyntheticEESMMap(),
        [str(value) for value in selection["point_id"]],
        equal_budget._sample_matrix(selection),
        tmp_path / "seed",
        families=("compact_mlp", "tree_ensemble"),
        n_model_seeds=2,
        include_deterministic=False,
    )
    assert summary["status"] == "completed"
    # 2 strategies x 1 budget x 2 families x 2 seeds
    assert len(summary["runs"]) == 8
    assert (tmp_path / "seed" / "seed_replication.json").is_file()


def test_fitted_surrogate_map_matches_predict() -> None:
    rng = np.random.default_rng(0)
    train_X = rng.uniform([-120.0, 0.0, 0.0], [0.0, 120.0, 15.0], size=(20, 3))
    oracle = SyntheticEESMMap()
    train_y = np.column_stack(oracle.flux(train_X[:, 0], train_X[:, 1], train_X[:, 2]))
    model = build_surrogate("physics_polynomial", 1701, {})
    model.fit(train_X, train_y)
    adapted = FittedSurrogateMap(model, oracle.domain)
    query = np.array([[-40.0, 50.0, 6.0]])
    predicted = model.predict(query)
    lambda_d, lambda_q = adapted.flux(query[:, 0], query[:, 1], query[:, 2])
    assert np.allclose(lambda_d, predicted[:, 0])
    assert np.allclose(lambda_q, predicted[:, 1])
    assert bool(adapted.is_in_domain(-40.0, 50.0, 6.0))


def test_write_freeze_without_campaign(tmp_path: Path) -> None:
    freeze = write_freeze(tmp_path / "freeze", _manifest(), campaign_rows=None)
    assert freeze["n_scheduler_commands"] == 64
    assert freeze["n_boundary"] == N_BOUNDARY
    assert freeze["n_wst360"] == 0
    assert freeze["n_new_unique_femm_train"] > 0
    assert (tmp_path / "freeze" / "points" / "design_replicate_new_femm.csv").is_file()
    assert (tmp_path / "freeze" / "points" / "boundary_set.csv").is_file()
