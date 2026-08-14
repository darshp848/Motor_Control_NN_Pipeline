#!/usr/bin/env python
"""Seed-average the energy-gradient net on frozen FEMM truth. No FEMM launch."""

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
from experiments.energy_seed_study import (  # noqa: E402
    ThreeChannelFemmTruth,
    run_energy_seed_study,
)
from experiments.phase2_strengthen import reserved_role_ids  # noqa: E402


DEFAULT_MANIFEST = os.path.join(
    EESM_ROOT, "configs", "eesm_experiment_manifest_v2_2.json"
)
DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_OUT = os.path.join(REPO_ROOT, "out", "eesm", "energy_seed_study_20260813")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--seeds", type=int, default=8)
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
        print("REFUSED: selection IDs do not match reserved role freeze", file=sys.stderr)
        return 2

    truth = ThreeChannelFemmTruth(args.campaign)
    summary = run_energy_seed_study(
        manifest,
        truth,
        selection_ids,
        equal_budget._sample_matrix(selection),
        out_root,
        n_seeds=args.seeds,
    )
    print(
        "energy seed study: cells=%d seeds=%d runs=%d out=%s"
        % (
            len(summary["by_cell"]),
            summary["n_seeds"],
            len(summary["runs"]),
            os.path.abspath(out_root),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
