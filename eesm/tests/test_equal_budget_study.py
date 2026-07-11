"""Task 5 contract for deterministic equal-budget baseline studies."""

from __future__ import annotations

import json
import hashlib
import importlib.util
import importlib
from pathlib import Path

import pytest

from experiments.equal_budget import run_equal_budget_study
from data.experiment_points import canonical_point_id
from synthetic.synthetic_map import SyntheticEESMMap


EESM_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = EESM_ROOT / "configs" / "eesm_experiment_manifest.json"
RUNNER_PATH = EESM_ROOT / "run_equal_budget_study.py"


@pytest.fixture
def smoke_manifest(tmp_path: Path) -> Path:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["budgets"] = [16]
    path = tmp_path / "eesm_experiment_manifest.json"
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def test_every_strategy_budget_family_runs_once(
    smoke_manifest: Path, tmp_path: Path
) -> None:
    summary = run_equal_budget_study(
        str(smoke_manifest),
        str(tmp_path / "study"),
        SyntheticEESMMap(),
    )

    expected_keys = {
        (strategy, 16, family)
        for strategy in ("tensor_grid", "random", "latin_hypercube")
        for family in (
            "physics_polynomial",
            "rbf_or_gp",
            "tree_ensemble",
            "compact_mlp",
        )
    }
    actual_keys = {
        (run["strategy"], run["budget"], run["family"])
        for run in summary["runs"]
    }

    assert len(summary["runs"]) == 12
    assert actual_keys == expected_keys
    for run in summary["runs"]:
        assert run["status"] == "completed"
        assert run["n_train"] == 16
        for artifact in run["artifacts"].values():
            assert (tmp_path / "study" / artifact).is_file()

    assert (tmp_path / "study" / "equal_budget_summary.json").is_file()


def test_frozen_manifest_builds_the_full_36_cell_matrix() -> None:
    equal_budget = importlib.import_module("experiments.equal_budget")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    matrix = equal_budget._build_run_matrix(manifest)

    assert len(matrix) == 36
    assert len(set(matrix)) == 36
    assert set(matrix) == {
        (strategy, budget, family)
        for strategy in manifest["sampling"]["baseline_strategies"]
        for budget in manifest["budgets"]
        for family in manifest["surrogates"]
    }


def test_training_hash_excludes_selection_and_scheduler_audit_points(
    smoke_manifest: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "study"
    summary = run_equal_budget_study(
        str(smoke_manifest), str(output_dir), SyntheticEESMMap()
    )
    selection_ids = set(summary["role_point_ids"]["selection"])
    audit_ids = set(summary["role_point_ids"]["scheduler_audit"])

    assert selection_ids.isdisjoint(audit_ids)
    for run in summary["runs"]:
        metadata = json.loads(
            (output_dir / run["artifacts"]["run_metadata"]).read_text(
                encoding="utf-8"
            )
        )
        train_ids = set(metadata["training_point_ids"])
        expected_hash = hashlib.sha256(
            "\n".join(sorted(train_ids)).encode("ascii")
        ).hexdigest()

        assert train_ids.isdisjoint(selection_ids | audit_ids)
        assert metadata["training_point_ids_sha256"] == expected_hash
        assert run["training_point_ids_sha256"] == expected_hash


def test_scheduler_audit_truth_is_never_requested(
    smoke_manifest: Path, tmp_path: Path
) -> None:
    oracle = SyntheticEESMMap()
    evaluated_ids: set[str] = set()

    class RecordingTruth:
        def flux(self, id_a, iq_a, if_a):
            evaluated_ids.update(
                canonical_point_id(id_value, iq_value, if_value)
                for id_value, iq_value, if_value in zip(id_a, iq_a, if_a)
            )
            return oracle.flux(id_a, iq_a, if_a)

    summary = run_equal_budget_study(
        str(smoke_manifest), str(tmp_path / "study"), RecordingTruth()
    )

    audit_ids = set(summary["role_point_ids"]["scheduler_audit"])
    assert evaluated_ids
    assert evaluated_ids.isdisjoint(audit_ids)


def test_cli_runs_the_smoke_manifest(
    smoke_manifest: Path, tmp_path: Path
) -> None:
    spec = importlib.util.spec_from_file_location("run_equal_budget_cli", RUNNER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    output_dir = tmp_path / "cli-study"
    assert module.main(
        ["--config", str(smoke_manifest), "--out", str(output_dir)]
    ) == 0
    summary = json.loads(
        (output_dir / "equal_budget_summary.json").read_text(encoding="utf-8")
    )
    assert summary["status"] == "completed"
    assert len(summary["runs"]) == 12


def test_role_overlap_is_rejected_before_any_model_is_built(
    smoke_manifest: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    equal_budget = importlib.import_module("experiments.equal_budget")
    manifest = json.loads(smoke_manifest.read_text(encoding="utf-8"))
    domain = equal_budget._domain_from_manifest(manifest)
    selection_seed = equal_budget._derived_seed(
        manifest["seeds"]["split"], "selection", 16
    )
    selection = equal_budget.latin_hypercube_samples(
        domain, n=16, seed=selection_seed
    )
    colliding_id = str(selection["point_id"][0])
    original_sample_training = equal_budget._sample_training

    def sample_with_late_overlap(strategy, domain, budget, seed):
        samples = original_sample_training(strategy, domain, budget, seed)
        if strategy == "random":
            samples["point_id"][0] = colliding_id
        return samples

    builds: list[str] = []
    original_build_surrogate = equal_budget.build_surrogate

    def record_build(family, seed, config):
        builds.append(family)
        return original_build_surrogate(family, seed, config)

    monkeypatch.setattr(equal_budget, "_sample_training", sample_with_late_overlap)
    monkeypatch.setattr(equal_budget, "build_surrogate", record_build)

    with pytest.raises(ValueError, match="point overlap"):
        run_equal_budget_study(
            str(smoke_manifest), str(tmp_path / "study"), SyntheticEESMMap()
        )
    assert builds == []


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda manifest: manifest.pop("budgets"), "missing budgets"),
        (
            lambda manifest: manifest.__setitem__("budgets", [16, 16]),
            "duplicate budgets",
        ),
        (
            lambda manifest: manifest["seeds"].__setitem__(
                "scheduler_audit", None
            ),
            "unfrozen role seeds",
        ),
        (
            lambda manifest: manifest["surrogates"].append(
                manifest["surrogates"][0]
            ),
            "duplicate surrogates",
        ),
    ],
)
def test_invalid_run_matrix_is_rejected_before_truth_evaluation(
    smoke_manifest: Path,
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    manifest = json.loads(smoke_manifest.read_text(encoding="utf-8"))
    mutate(manifest)
    smoke_manifest.write_text(json.dumps(manifest), encoding="utf-8")

    def unexpected_truth_call(_):
        raise AssertionError("truth provider was called before validation")

    with pytest.raises(ValueError, match=message):
        run_equal_budget_study(
            str(smoke_manifest), str(tmp_path / "study"), unexpected_truth_call
        )


def test_repeated_summaries_are_deterministic_after_removing_timestamp(
    smoke_manifest: Path, tmp_path: Path
) -> None:
    first = run_equal_budget_study(
        str(smoke_manifest), str(tmp_path / "first"), SyntheticEESMMap()
    )
    second = run_equal_budget_study(
        str(smoke_manifest), str(tmp_path / "second"), SyntheticEESMMap()
    )

    first.pop("created_utc")
    second.pop("created_utc")
    assert first == second
