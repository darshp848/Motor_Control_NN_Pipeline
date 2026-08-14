#!/usr/bin/env python
"""Rescore 54 cells under frozen physics gates. No FEMM. No threshold edit."""

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

from experiments import equal_budget  # noqa: E402
from experiments.energy_seed_study import ThreeChannelFemmTruth  # noqa: E402
from experiments.phase2_strengthen import reserved_role_ids  # noqa: E402
from experiments.physics_gate_study import run_physics_gate_study  # noqa: E402


DEFAULT_MANIFEST = os.path.join(
    EESM_ROOT, "configs", "eesm_experiment_manifest_v2_3.json"
)
DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_ANCHORS = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_fd_anchors_20260813", "fd_anchors.json"
)
DEFAULT_OUT = os.path.join(
    REPO_ROOT, "out", "eesm", "physics_gate_study_20260813"
)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--anchors", default=DEFAULT_ANCHORS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--seeds", type=int, default=None)
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    if out_root.exists() and any(out_root.iterdir()):
        print("REFUSED: non-empty output root %s" % out_root, file=sys.stderr)
        return 2

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    reserved = reserved_role_ids(manifest)
    domain = equal_budget._domain_from_manifest(manifest)
    _, budgets, _, seeds = equal_budget._validate_manifest(manifest)
    role_budget = max(budgets)
    selection = equal_budget.latin_hypercube_samples(
        domain,
        n=role_budget,
        seed=equal_budget._derived_seed(seeds["split"], "selection", role_budget),
    )
    selection_ids = [str(value) for value in selection["point_id"]]
    if selection_ids != reserved["selection"]:
        print("REFUSED: selection IDs do not match reserved freeze", file=sys.stderr)
        return 2

    anchors = json.loads(Path(args.anchors).read_text(encoding="utf-8"))
    summary = run_physics_gate_study(
        manifest,
        ThreeChannelFemmTruth(args.campaign),
        selection_ids,
        equal_budget._sample_matrix(selection),
        anchors,
        out_root,
        n_seeds=args.seeds,
    )
    ranking = summary["ranking"]
    print(
        "physics-gate study: cells=%d pass=%d runs=%d out=%s"
        % (
            ranking["n_cells"],
            ranking["n_pass"],
            len(summary["runs"]),
            os.path.abspath(out_root),
        )
    )
    if ranking["ranked_passers"]:
        winner = ranking["ranked_passers"][0]
        print(
            "lowest-median-torque passer: %s  T=%s"
            % (winner["candidate_id"], winner["median_torque_rmse_nm"])
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
