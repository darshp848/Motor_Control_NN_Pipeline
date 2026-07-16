"""Independently report a frozen direct-r5 quarter-sector qualification."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r5"
os.environ["EESM_R5_CAMPAIGN_ROOT"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "out", "eesm", "task9_requalification_r5_attempt1_20260716",
)

from report_task9_requalification_r3 import DEFAULT_ROOT, build


if __name__ == "__main__":
    print(json.dumps(build(
        DEFAULT_ROOT / "frozen_points.csv",
        DEFAULT_ROOT / "raw" / "diagnostic_progress.csv",
        DEFAULT_ROOT / "requalification_report.json",
    ), indent=2))
