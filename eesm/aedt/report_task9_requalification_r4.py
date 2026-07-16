"""Report the direct-r4 qualification without changing r3 defaults."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r4"

from report_task9_requalification_r3 import DEFAULT_ROOT, build


if __name__ == "__main__":
    print(json.dumps(build(
        DEFAULT_ROOT / "frozen_points.csv",
        DEFAULT_ROOT / "raw" / "diagnostic_progress.csv",
        DEFAULT_ROOT / "requalification_report.json",
    ), indent=2))
