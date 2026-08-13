#!/usr/bin/env python
"""One-command entry point for the FEMM EESM campaign.

Does not launch AEDT / Maxwell. Launches FEMM only when a real handle is
resolved, which cannot happen on a machine without FEMM 4.2.

Three modes:

    --check                 report what this machine can actually run, exit
    --mock                  drive the campaign with MockFemm (NOT evidence)
    (neither)               resolve a real FEMM handle, or fail loudly

The mock mode exists so the plumbing -- conversion, resume, schema validation,
provenance -- can be rehearsed offline. It never produces a physics result.
See eesm/docs/FEMM_MIGRATION.md.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional

_EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_EESM_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from eesm.femm import campaign, geometry, points, runtime  # noqa: E402
from eesm.femm.campaign import CampaignPaths, CampaignRefusal  # noqa: E402
from eesm.femm.config import DEFAULT_CONFIG  # noqa: E402
from eesm.femm.points import PointsRefusal  # noqa: E402

DEFAULT_OUTPUT = os.path.join(_REPO_ROOT, "out", "eesm", "femm_campaign")

#: A directory holding any of these is preserved evidence from another
#: campaign. The FEMM driver refuses to write beside it -- a new campaign is a
#: new directory, never an addition to a freeze.
PRESERVED_FREEZE_MARKERS = (
    "campaign_freeze.json",
    "canonical_campaign.csv",
    "campaign_report.json",
    "raw",
    "failed_runs",
)


class RunnerRefusal(RuntimeError):
    """A precondition failed. Nothing was run."""


def guard_campaign_root(root: str) -> None:
    """Refuse a campaign root that already holds another campaign's evidence."""
    found = [marker for marker in PRESERVED_FREEZE_MARKERS
             if os.path.exists(os.path.join(root, marker))]
    if found:
        raise RunnerRefusal(
            "Refusing run: %s holds preserved evidence %s. A FEMM campaign "
            "must not deposit results into another campaign's freeze. Choose "
            "a new --out directory." % (root, sorted(found))
        )


def prepare_points(paths: CampaignPaths, source: Optional[str]) -> Dict[str, Any]:
    """Ensure the campaign root has a points file this driver can read."""
    if os.path.exists(paths.points_csv):
        return {"action": "existing", "path": paths.points_csv}
    if source is None:
        raise RunnerRefusal(
            "Refusing run: %s has no frozen_points.csv and no --points source "
            "was given." % paths.root
        )
    dialect = points.dialect_of(source)
    paths.ensure()
    if dialect == "femm":
        payload = points.copy_femm_points_file(source, paths.points_csv)
        return {"action": "copied", "source_dialect": dialect,
                "path": paths.points_csv, "provenance": payload}
    payload = points.adapt_points_file(source, paths.points_csv)
    return {"action": "converted", "source_dialect": dialect,
            "path": paths.points_csv, "provenance": payload}


def resolve_handle(use_mock: bool) -> Any:
    """The mock is opt-in and loudly labelled; otherwise demand a real FEMM."""
    if use_mock:
        from eesm.femm.mock_femm import MockFemm
        return MockFemm(cfg=DEFAULT_CONFIG), "mock_femm"
    return runtime.resolve_femm(), "femm_4.2"


def run_femm_campaign(output_dir: str = DEFAULT_OUTPUT,
                      points_source: Optional[str] = None,
                      use_mock: bool = False,
                      max_new_points: Optional[int] = None,
                      rotor_angle_deg: float = 0.0) -> Dict[str, Any]:
    """Convert points if needed, then run (or resume) the campaign."""
    paths = CampaignPaths(root=os.path.abspath(output_dir))
    if os.path.isdir(paths.root):
        guard_campaign_root(paths.root)
    paths.ensure()

    prepared = prepare_points(paths, points_source)
    handle, backend = resolve_handle(use_mock)
    if not use_mock:
        document = os.path.join(paths.root, "eesm_sector.fem")
        geometry.open_and_build(handle, document, DEFAULT_CONFIG)

    try:
        status = campaign.run_campaign(
            handle, paths, cfg=DEFAULT_CONFIG,
            max_new_points=max_new_points,
            rotor_angle_deg=rotor_angle_deg,
            solver_backend=backend,
        )
    finally:
        closer = getattr(handle, "closefemm", None)
        if callable(closer):
            try:
                closer()
            except BaseException:
                pass
    status["points_preparation"] = prepared
    campaign.write_status(paths.status_json, status)
    return status


def print_report(status: Dict[str, Any], paths: CampaignPaths) -> None:
    print("=== FEMM EESM campaign ===")
    print("root:      %s" % paths.root)
    print("backend:   %s" % status.get("solver_backend"))
    print("points:    %s (sha256 %s)"
          % (status.get("points_total"), str(status.get("points_sha256"))[:16]))
    print("completed: %d / %d"
          % (len(status.get("completed", [])), status.get("points_total", 0)))
    print("this run:  %d solved" % len(status.get("solved_this_run", [])))
    print("status:    %s" % status.get("status"))
    prepared = status.get("points_preparation", {})
    if prepared.get("action") in ("converted", "copied"):
        print("%s: %s -> %s"
              % (prepared["action"], prepared["provenance"]["source_path"],
                 prepared["path"]))
    if status.get("solver_backend") == "mock_femm":
        print("")
        print("  *** MOCK RUN. These numbers came from a closed-form stand-in,")
        print("  *** not a solver. They are NOT evidence and must never be")
        print("  *** normalized, fitted, promoted, or reported as FEM results.")
    unverified = status.get("config_provenance", {}).get("unverified", {})
    if unverified:
        print("")
        print("unverified constants carried by this run: %d" % len(unverified))
        for key in sorted(unverified)[:4]:
            print("  - %s" % key)
        if len(unverified) > 4:
            print("  - ... see femm_status.json for the full list")


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true",
                        help="Report FEMM availability on this machine and exit")
    parser.add_argument("--out", default=DEFAULT_OUTPUT,
                        help="Campaign root (default: out/eesm/femm_campaign)")
    parser.add_argument("--points", default=None,
                        help="Frozen points source; converted into the root "
                             "if it is in the AEDT dialect")
    parser.add_argument("--mock", action="store_true",
                        help="Drive with MockFemm. Produces plumbing evidence "
                             "only, never a physics result.")
    parser.add_argument("--max-new-points", type=int, default=None,
                        help="Solve at most N new points, then stop resumably")
    parser.add_argument("--rotor-angle-deg", type=float, default=0.0)
    ns = parser.parse_args(argv)

    if ns.check:
        print(json.dumps(runtime.availability_payload(), indent=2, sort_keys=True))
        print("\nFEMM call surface to confirm on the first Windows run: %d"
              % len(runtime.FEMM_CALL_SURFACE))
        return 0

    try:
        status = run_femm_campaign(
            output_dir=ns.out,
            points_source=ns.points,
            use_mock=ns.mock,
            max_new_points=ns.max_new_points,
            rotor_angle_deg=ns.rotor_angle_deg,
        )
    except (RunnerRefusal, CampaignRefusal, PointsRefusal) as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 2
    except RuntimeError as exc:
        print("FAILED: %s" % exc, file=sys.stderr)
        return 2

    print_report(status, CampaignPaths(root=os.path.abspath(ns.out)))
    return 0 if status.get("status") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
