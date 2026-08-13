#!/usr/bin/env python
"""Write the Phase 0 threshold proposal. Does not edit the manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
REPO_ROOT = os.path.dirname(EESM_ROOT)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from validation.threshold_method import (  # noqa: E402
    DESIGN_KEYS,
    load_campaign_rows,
    load_design_ids,
    propose_thresholds,
    write_proposal,
)

DEFAULT_MANIFEST = os.path.join(EESM_ROOT, "configs", "eesm_experiment_manifest.json")
DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_DESIGNS = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_points_20260813", "designs"
)
DEFAULT_OUT = os.path.join(
    REPO_ROOT, "out", "eesm", "threshold_proposal_20260813.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--designs", default=DEFAULT_DESIGNS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    ns = parser.parse_args(argv)

    manifest = json.loads(Path(ns.manifest).read_text(encoding="utf-8"))
    if manifest["gates"]["status"] != "baseline_required":
        print("REFUSED: manifest gates are not baseline_required", file=sys.stderr)
        return 2
    from validation.threshold_method import _machine_from_manifest

    rows = load_campaign_rows(Path(ns.campaign))
    designs = {
        key: load_design_ids(Path(ns.designs), key) for key in DESIGN_KEYS
    }
    payload = propose_thresholds(rows, designs, _machine_from_manifest(manifest))
    payload["campaign_path"] = os.path.abspath(ns.campaign)
    payload["manifest_path"] = os.path.abspath(ns.manifest)
    payload["not_written_to_manifest"] = True
    write_proposal(Path(ns.out), payload)
    print(json.dumps({
        "out": os.path.abspath(ns.out),
        "status": payload["status"],
        "proposed_thresholds": payload["proposed_thresholds"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
