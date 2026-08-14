#!/usr/bin/env python
"""Freeze Phase 2 identities, run offline studies, or fit design replicates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
REPO_ROOT = os.path.dirname(EESM_ROOT)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from experiments import equal_budget  # noqa: E402
from data.femm_truth import FemmCampaignTruth  # noqa: E402
from experiments.phase2_strengthen import (  # noqa: E402
    load_campaign_rows,
    load_equal_tuning_configs,
    merge_campaign_csvs,
    reserved_role_ids,
    run_design_replicate_fit,
    run_existing_map_schedules,
    run_model_tests,
    run_seed_replication,
    write_freeze,
    write_no_promotion_bundle,
)


DEFAULT_MANIFEST = os.path.join(EESM_ROOT, "configs", "eesm_experiment_manifest.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "out", "eesm", "phase2_strengthen_20260813")
DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_STUDY = os.path.join(REPO_ROOT, "out", "eesm", "equal_budget_femm_20260813")
DEFAULT_PHASE2_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "phase2_design_replicates_20260813", "femm_results.csv"
)
DEFAULT_EQUAL_TUNING = os.path.join(
    REPO_ROOT, "out", "eesm", "equal_tuning_20260814", "equal_tuning.json"
)
DEFAULT_FIT_OUT = os.path.join(
    REPO_ROOT, "out", "eesm", "phase2_design_replicate_fit_20260814"
)
DEFAULT_TEST_OUT = os.path.join(
    REPO_ROOT, "out", "eesm", "phase2_model_test_20260814"
)
DEFAULT_BOUNDARY = os.path.join(
    REPO_ROOT, "out", "eesm", "phase2_boundary_20260814", "femm_results.csv"
)
DEFAULT_SCHEDULER_AUDIT = os.path.join(
    REPO_ROOT, "out", "eesm", "phase2_scheduler_audit_20260814", "femm_results.csv"
)
DEFAULT_WST360 = os.path.join(
    REPO_ROOT, "out", "eesm", "phase2_wst360_20260814", "femm_results.csv"
)


def _load_manifest(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _selection_matrix(manifest: dict, summary_path: Path | None):
    reserved = reserved_role_ids(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    _, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    role_budget = max(budgets)
    selection_seed = equal_budget._derived_seed(
        seeds["split"], "selection", role_budget
    )
    samples = equal_budget.latin_hypercube_samples(
        domain, n=role_budget, seed=selection_seed
    )
    selection_ids = [str(value) for value in samples["point_id"]]
    if summary_path and summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        frozen_ids = list(summary["role_point_ids"]["selection"])
        if frozen_ids != selection_ids:
            raise RuntimeError(
                "reconstructed selection IDs do not match the Phase 0 study"
            )
    return selection_ids, equal_budget._sample_matrix(samples)


def cmd_freeze(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    campaign_rows = None
    if args.campaign and Path(args.campaign).is_file():
        campaign_rows = load_campaign_rows(args.campaign)
    freeze = write_freeze(args.out, manifest, campaign_rows)
    print(
        "phase2 freeze: new_train=%s boundary=%s wst360=%s commands=%s out=%s"
        % (
            freeze["n_new_unique_femm_train"],
            freeze["n_boundary"],
            freeze["n_wst360"],
            freeze["n_scheduler_commands"],
            os.path.abspath(args.out),
        )
    )
    return 0


def cmd_seed_replication(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    if not Path(args.campaign).is_file():
        print("REFUSED: missing campaign CSV %s" % args.campaign, file=sys.stderr)
        return 2
    selection_ids, selection_X = _selection_matrix(
        manifest, Path(args.study) / "equal_budget_summary.json"
    )
    truth = FemmCampaignTruth(args.campaign)
    summary = run_seed_replication(
        manifest,
        truth,
        selection_ids,
        selection_X,
        Path(args.out) / "seed_replication",
    )
    print(
        "phase2 seed-replication: runs=%d status=%s out=%s"
        % (
            len(summary["runs"]),
            summary["status"],
            os.path.abspath(Path(args.out) / "seed_replication"),
        )
    )
    return 0


def _git(*git_args: str) -> str | None:
    try:
        return subprocess.run(
            ["git", *git_args],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except Exception:
        return None


def cmd_design_replicate_fit(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    phase0 = Path(args.campaign)
    phase2 = Path(args.phase2_campaign)
    if not phase0.is_file():
        print("REFUSED: missing Phase 0 campaign %s" % phase0, file=sys.stderr)
        return 2
    if not phase2.is_file():
        print("REFUSED: missing Phase 2 campaign %s" % phase2, file=sys.stderr)
        return 2
    et_path = Path(args.equal_tuning)
    if not et_path.is_file():
        print("REFUSED: missing equal-tuning study %s" % et_path, file=sys.stderr)
        return 2
    out_root = Path(args.out).resolve()
    if (out_root / "result_bundle.json").is_file():
        print(
            "REFUSED: %s already exists" % (out_root / "result_bundle.json"),
            file=sys.stderr,
        )
        return 2
    out_root.mkdir(parents=True, exist_ok=True)
    merged_path = out_root / "merged_femm_truth.csv"
    merge_info = merge_campaign_csvs([phase0, phase2], merged_path)
    selection_ids, selection_X = _selection_matrix(
        manifest, Path(args.study) / "equal_budget_summary.json"
    )
    configs = load_equal_tuning_configs(et_path)
    truth = FemmCampaignTruth(merged_path)
    print(
        "phase2 design-replicate-fit: merged unique_truth=%d configs=%d"
        % (merge_info["n_unique"], len(configs)),
        flush=True,
    )
    summary = run_design_replicate_fit(
        manifest,
        truth,
        selection_ids,
        selection_X,
        out_root,
        configs,
    )
    commit = _git("rev-parse", "HEAD") or ("0" * 40)
    dirty = _git("status", "--porcelain")
    manifest_sha = hashlib.sha256(Path(args.manifest).read_bytes()).hexdigest()
    write_no_promotion_bundle(
        out_root,
        summary,
        manifest,
        foundry_commit=commit,
        manifest_sha256=manifest_sha,
        extra_artifacts=[
            {
                "path": "merged_femm_truth.csv",
                "sha256": hashlib.sha256(merged_path.read_bytes()).hexdigest(),
            }
        ],
        working_tree_may_be_dirty=bool(dirty) if dirty is not None else True,
    )
    print(
        "phase2 design-replicate-fit: runs=%d unique_truth=%d status=%s out=%s"
        % (
            len(summary["runs"]),
            merge_info["n_unique"],
            summary["status"],
            os.path.abspath(out_root),
        )
    )
    return 0


def cmd_test_maps(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    fit_root = Path(args.fit)
    if not (fit_root / "design_replicate_fit.json").is_file():
        print("REFUSED: missing fit summary in %s" % fit_root, file=sys.stderr)
        return 2
    holdouts = {
        "boundary": args.boundary,
        "scheduler_audit": args.scheduler_campaign,
        "wst360": args.wst360,
    }
    known = [args.campaign, args.phase2_campaign, args.boundary, args.scheduler_campaign]
    payload = run_model_tests(
        fit_root,
        manifest,
        Path(args.out),
        holdouts,
        known,
    )
    print(
        "phase2 test-maps: recommended=%s holdouts=%s new_audit=%s out=%s"
        % (
            payload["recommended_cell_budget256"],
            {
                label: info.get("status")
                for label, info in payload["holdouts"].items()
            },
            payload["new_audit_points"]["n_missing"],
            os.path.abspath(args.out),
        )
    )
    return 0


def cmd_schedule(args: argparse.Namespace) -> int:
    manifest = _load_manifest(args.manifest)
    payload = run_existing_map_schedules(
        args.study,
        manifest,
        Path(args.out) / "scheduler_offline",
    )
    print(
        "phase2 schedule: maps=%d commands=%d unique_currents=%d out=%s"
        % (
            payload["n_candidates"],
            payload["n_commands"],
            payload["n_unique_selected_currents"],
            os.path.abspath(Path(args.out) / "scheduler_offline"),
        )
    )
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--study", default=DEFAULT_STUDY)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    _add_common_args(parser)
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser(
        "freeze", help="Write Phase 2 point and command identities"
    )
    _add_common_args(freeze_parser)
    seed_parser = sub.add_parser(
        "seed-replication",
        help="Refit stochastic families on the nine Phase 0 designs",
    )
    _add_common_args(seed_parser)
    schedule_parser = sub.add_parser(
        "schedule",
        help="Re-optimize the frozen (rpm, T) commands on Phase 0 maps",
    )
    _add_common_args(schedule_parser)
    fit_parser = sub.add_parser(
        "design-replicate-fit",
        help="Fit Phase 2 design replicates with equal-tuning configs",
    )
    _add_common_args(fit_parser)
    fit_parser.set_defaults(out=DEFAULT_FIT_OUT)
    fit_parser.add_argument("--phase2-campaign", default=DEFAULT_PHASE2_CAMPAIGN)
    fit_parser.add_argument("--equal-tuning", default=DEFAULT_EQUAL_TUNING)
    test_parser = sub.add_parser(
        "test-maps",
        help="Score saved maps on holdouts and schedule control tests",
    )
    _add_common_args(test_parser)
    test_parser.set_defaults(out=DEFAULT_TEST_OUT)
    test_parser.add_argument("--fit", default=DEFAULT_FIT_OUT)
    test_parser.add_argument("--phase2-campaign", default=DEFAULT_PHASE2_CAMPAIGN)
    test_parser.add_argument("--boundary", default=DEFAULT_BOUNDARY)
    test_parser.add_argument(
        "--scheduler-campaign", default=DEFAULT_SCHEDULER_AUDIT
    )
    test_parser.add_argument("--wst360", default=DEFAULT_WST360)
    args = parser.parse_args(argv)
    if args.command == "freeze":
        return cmd_freeze(args)
    if args.command == "seed-replication":
        return cmd_seed_replication(args)
    if args.command == "schedule":
        return cmd_schedule(args)
    if args.command == "design-replicate-fit":
        return cmd_design_replicate_fit(args)
    if args.command == "test-maps":
        return cmd_test_maps(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
