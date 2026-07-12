#!/usr/bin/env python
"""Run the frozen equal-budget EESM surrogate matrix against synthetic truth."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Optional


EESM_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(EESM_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
if EESM_ROOT not in sys.path:
    sys.path.insert(0, EESM_ROOT)

from experiments.equal_budget import run_equal_budget_study  # noqa: E402
from run_synthetic_stage1 import (  # noqa: E402
    DEFAULT_MANIFEST as DEFAULT_TRUTH_CONFIG,
    build_synthetic_truth_provider,
)


DEFAULT_CONFIG = os.path.join(
    EESM_ROOT, "configs", "eesm_experiment_manifest.json"
)
REPO_ROOT = os.path.dirname(EESM_ROOT)
DEFAULT_OUTPUT = os.path.join(REPO_ROOT, "out", "eesm", "equal_budget")


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--out", default=DEFAULT_OUTPUT)
    parser.add_argument("--truth-config", default=DEFAULT_TRUTH_CONFIG)
    args = parser.parse_args(argv)

    truth_provider = build_synthetic_truth_provider(args.truth_config)
    summary = run_equal_budget_study(
        manifest_path=args.config,
        output_dir=args.out,
        truth_provider=truth_provider,
    )
    print(
        "equal-budget study: "
        f"status={summary['status']} runs={len(summary['runs'])} "
        f"output={os.path.abspath(args.out)}"
    )
    return 0 if summary["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
