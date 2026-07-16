"""Freeze the direct-Maxwell r6 quarter-sector Task 9 qualification."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r6"

from prepare_task9_requalification_r3 import freeze


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
