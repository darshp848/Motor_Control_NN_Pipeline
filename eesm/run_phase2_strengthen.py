#!/usr/bin/env python
"""Freeze Phase 2 identities or run the offline seed-replication study."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
REPO_ROOT = os.path.dirname(EESM_ROOT)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from data.femm_truth import FemmCampaignTruth  # noqa: E402
from experiments import equal_budget  # noqa: E402
from experiments.phase2_strengthen import (  # noqa: E402
    load_campaign_rows,
    reserved_role_ids,
    run_existing_map_schedules,
    run_seed_replication,
    write_freeze,
)


DEFAULT_MANIFEST = os.path.join(EESM_ROOT, "configs", "eesm_experiment_manifest.json")
DEFAULT_OUT = os.path.join(REPO_ROOT, "out", "eesm", "phase2_strengthen_20260813")
DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_STUDY = os.path.join(REPO_ROOT, "out", "eesm", "equal_budget_femm_20260813")


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
    args = parser.parse_args(argv)
    if args.command == "freeze":
        return cmd_freeze(args)
    if args.command == "seed-replication":
        return cmd_seed_replication(args)
    if args.command == "schedule":
        return cmd_schedule(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
