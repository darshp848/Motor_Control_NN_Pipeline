"""Phase 2 identity and seed-replication contracts. No FEMM launch."""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pytest

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
    campaign_arrays,
    classify_region,
    design_replicate_seed,
    load_equal_tuning_configs,
    merge_campaign_csvs,
    missing_audit_points,
    model_replicate_seeds,
    phase0_sample_seed,
    recommend_cell,
    run_design_replicate_fit,
    run_seed_replication,
    score_model_on_arrays,
    select_control_test_runs,
    write_freeze,
    write_no_promotion_bundle,
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


def test_merge_campaign_csvs_dedupes_identical_rows(tmp_path: Path) -> None:
    header = "point_id,lambda_d_wb,lambda_q_wb\n"
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text(header + "aa,0.1,0.2\nbb,0.3,0.4\n", encoding="utf-8")
    b.write_text(header + "bb,0.3,0.4\ncc,0.5,0.6\n", encoding="utf-8")
    dest = tmp_path / "merged.csv"
    info = merge_campaign_csvs([a, b], dest)
    assert info["n_unique"] == 3
    assert info["n_identical_collisions"] == 1
    text = dest.read_text(encoding="utf-8")
    assert text.count("\n") == 4


def test_merge_campaign_csvs_refuses_conflict(tmp_path: Path) -> None:
    header = "point_id,lambda_d_wb,lambda_q_wb\n"
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    a.write_text(header + "aa,0.1,0.2\n", encoding="utf-8")
    b.write_text(header + "aa,0.9,0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="conflicting"):
        merge_campaign_csvs([a, b], tmp_path / "merged.csv")


def test_design_replicate_fit_uses_equal_tuning_configs(tmp_path: Path) -> None:
    manifest = _manifest()
    manifest["budgets"] = [16]
    manifest["sampling"] = {"baseline_strategies": ["tensor_grid", "random"]}
    manifest["surrogates"] = ["physics_polynomial"]
    domain = equal_budget._domain_from_manifest(manifest)
    selection = equal_budget.latin_hypercube_samples(domain, n=16, seed=11)
    configs = {
        "tensor_grid|16|physics_polynomial": {"degree": 2, "alpha": 1e-3},
        "random|16|physics_polynomial": {"degree": 2, "alpha": 1e-3},
    }
    summary = run_design_replicate_fit(
        manifest,
        SyntheticEESMMap(),
        [str(value) for value in selection["point_id"]],
        equal_budget._sample_matrix(selection),
        tmp_path / "fit",
        configs,
        families=("physics_polynomial",),
        n_replicates=1,
    )
    # tensor r0 + random r0 + random r1
    assert len(summary["runs"]) == 3
    assert all(row["selected_config"]["degree"] == 2 for row in summary["runs"])
    assert summary["runs"][0]["model_seed"] == 1701
    assert (tmp_path / "fit" / summary["runs"][0]["artifacts"]["model"]).is_file()
    cwd = Path.cwd()
    try:
        os.chdir(tmp_path)
        summary_rel = run_design_replicate_fit(
            manifest,
            SyntheticEESMMap(),
            [str(value) for value in selection["point_id"]],
            equal_budget._sample_matrix(selection),
            "rel_fit",
            configs,
            families=("physics_polynomial",),
            n_replicates=0,
        )
    finally:
        os.chdir(cwd)
    model_rel = summary_rel["runs"][0]["artifacts"]["model"]
    assert not Path(model_rel).is_absolute()
    assert (tmp_path / "rel_fit" / model_rel).is_file()
    bundle = write_no_promotion_bundle(
        tmp_path / "fit",
        summary,
        manifest,
        foundry_commit="a" * 40,
        manifest_sha256="b" * 64,
    )
    payload = json.loads(bundle.read_text(encoding="utf-8"))
    assert payload["decisions"]["promotion"]["status"] == "no_promotion"
    assert payload["decisions"]["promotion"]["candidate"] is None


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


def test_recommend_cell_and_control_selection() -> None:
    summary = {
        "group_summary": {
            "random|256|compact_mlp": {"median": 0.2, "iqr": 0.05},
            "latin_hypercube|256|rbf_or_gp": {"median": 0.4, "iqr": 0.01},
            "random|128|compact_mlp": {"median": 0.1, "iqr": 0.01},
        },
        "runs": [
            {
                "strategy": "random",
                "budget": 256,
                "family": "compact_mlp",
                "design_replicate": 0,
            },
            {
                "strategy": "random",
                "budget": 256,
                "family": "compact_mlp",
                "design_replicate": 2,
            },
            {
                "strategy": "latin_hypercube",
                "budget": 256,
                "family": "rbf_or_gp",
                "design_replicate": 0,
            },
            {
                "strategy": "latin_hypercube",
                "budget": 256,
                "family": "rbf_or_gp",
                "design_replicate": 1,
            },
        ],
    }
    assert recommend_cell(summary) == "random|256|compact_mlp"
    chosen = select_control_test_runs(summary)
    keys = {
        (row["strategy"], row["family"], row["design_replicate"]) for row in chosen
    }
    assert ("random", "compact_mlp", 0) in keys
    assert ("random", "compact_mlp", 2) in keys
    assert ("latin_hypercube", "rbf_or_gp", 0) in keys
    assert ("latin_hypercube", "rbf_or_gp", 1) not in keys


def test_campaign_arrays_skips_incomplete(tmp_path: Path) -> None:
    path = tmp_path / "partial.csv"
    path.write_text(
        "point_id,id_a,iq_a,if_a,lambda_d_wb,lambda_q_wb,region,converged\n"
        "aa,-10,20,3,0.1,0.2,boundary,True\n"
        "bb,-11,21,4,,,boundary,True\n",
        encoding="utf-8",
    )
    arrays = campaign_arrays(path)
    assert arrays["n_rows"] == 2
    assert arrays["n_usable"] == 1
    assert arrays["X"].shape == (1, 3)


def test_score_model_on_arrays_and_missing_points(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    train_X = rng.uniform([-120.0, 0.0, 0.0], [0.0, 120.0, 15.0], size=(20, 3))
    oracle = SyntheticEESMMap()
    train_y = np.column_stack(oracle.flux(train_X[:, 0], train_X[:, 1], train_X[:, 2]))
    model = build_surrogate("physics_polynomial", 1701, {"degree": 2})
    model.fit(train_X, train_y)
    scored = score_model_on_arrays(
        model, train_X, train_y, ["interior"] * len(train_X), pole_pairs=2
    )
    assert scored["n"] == 20
    assert scored["torque_rmse_nm"] < 5.0
    known = tmp_path / "known.csv"
    known.write_text(
        "point_id,id_a,iq_a,if_a,lambda_d_wb,lambda_q_wb\n"
        "aa,-1,2,3,0.1,0.2\n",
        encoding="utf-8",
    )
    scheduled = tmp_path / "sched.csv"
    scheduled.write_text(
        "point_name,point_id,role,region,id_a,iq_a,if_a\n"
        "aa,aa,reference,interior,-1,2,3\n"
        "bb,bb,reference,interior,-4,5,6\n",
        encoding="utf-8",
    )
    info = missing_audit_points(scheduled, [known], tmp_path / "missing.csv")
    assert info["n_missing"] == 1
    assert "bb" in (tmp_path / "missing.csv").read_text(encoding="utf-8")


def test_write_freeze_without_campaign(tmp_path: Path) -> None:
    freeze = write_freeze(tmp_path / "freeze", _manifest(), campaign_rows=None)
    assert freeze["n_scheduler_commands"] == 64
    assert freeze["n_boundary"] == N_BOUNDARY
    assert freeze["n_wst360"] == 0
    assert freeze["n_new_unique_femm_train"] > 0
    assert (tmp_path / "freeze" / "points" / "design_replicate_new_femm.csv").is_file()
    assert (tmp_path / "freeze" / "points" / "boundary_set.csv").is_file()
