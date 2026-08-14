#!/usr/bin/env python
"""Export one scheduler candidate as a Simulink corroboration LUT."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
REPO_ROOT = os.path.dirname(EESM_ROOT)
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from export.simulink_export import (  # noqa: E402
    SimulinkExportRefusal,
    export_scheduler_candidate,
)


DEFAULT_SCHEDULE = os.path.join(
    REPO_ROOT,
    "out",
    "eesm",
    "phase2_strengthen_20260813",
    "scheduler_offline",
    "scheduler_commands_offline.json",
)
DEFAULT_MODEL = os.path.join(
    REPO_ROOT,
    "out",
    "eesm",
    "equal_budget_femm_20260813",
    "runs",
    "latin_hypercube",
    "256",
    "rbf_or_gp",
    "model_metadata.json",
)
DEFAULT_OUT = os.path.join(REPO_ROOT, "out", "eesm", "simulink_export_20260813")
DEFAULT_CANDIDATE = "latin_hypercube|256|rbf_or_gp"


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", default=DEFAULT_SCHEDULE)
    parser.add_argument("--model-metadata", default=DEFAULT_MODEL)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--candidate", default=DEFAULT_CANDIDATE)
    args = parser.parse_args(argv)
    try:
        payload = export_scheduler_candidate(
            args.schedule,
            args.model_metadata,
            args.out,
            args.candidate,
        )
    except SimulinkExportRefusal as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 2
    print(
        "simulink export: candidate=%s rows=%s fem_audit=%s out=%s"
        % (
            payload["candidate_id"],
            payload["n_rows"],
            payload["fem_audit_complete"],
            os.path.abspath(args.out),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
