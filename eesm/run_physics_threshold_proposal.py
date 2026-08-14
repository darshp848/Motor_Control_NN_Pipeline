#!/usr/bin/env python
"""Write the Paper 2 physics-gate proposal from IDW. No family fits."""

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

from validation.physics_threshold_method import (  # noqa: E402
    propose_physics_thresholds,
    write_proposal,
)
from validation.threshold_method import (  # noqa: E402
    DESIGN_KEYS,
    load_campaign_rows,
    load_design_ids,
)


DEFAULT_CAMPAIGN = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_20260813", "femm_results.csv"
)
DEFAULT_DESIGNS = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_equal_budget_points_20260813", "designs"
)
DEFAULT_ANCHORS = os.path.join(
    REPO_ROOT, "out", "eesm", "femm_fd_anchors_20260813", "fd_anchors.json"
)
DEFAULT_OUT = os.path.join(
    REPO_ROOT, "out", "eesm", "physics_threshold_proposal_20260813.json"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default=DEFAULT_CAMPAIGN)
    parser.add_argument("--designs", default=DEFAULT_DESIGNS)
    parser.add_argument("--anchors", default=DEFAULT_ANCHORS)
    parser.add_argument("--out", default=DEFAULT_OUT)
    ns = parser.parse_args(argv)

    out_path = Path(ns.out)
    if out_path.exists():
        print("REFUSED: proposal already exists at %s" % out_path, file=sys.stderr)
        return 2

    rows = load_campaign_rows(Path(ns.campaign))
    designs = {
        key: load_design_ids(Path(ns.designs), key) for key in DESIGN_KEYS
    }
    anchors = json.loads(Path(ns.anchors).read_text(encoding="utf-8"))
    payload = propose_physics_thresholds(rows, designs, anchors)
    payload["campaign_path"] = os.path.abspath(ns.campaign)
    payload["anchors_path"] = os.path.abspath(ns.anchors)
    payload["not_written_to_phase0_manifest"] = True
    write_proposal(out_path, payload)
    print(
        json.dumps(
            {
                "out": os.path.abspath(ns.out),
                "status": payload["status"],
                "proposed_thresholds": payload["proposed_thresholds"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
