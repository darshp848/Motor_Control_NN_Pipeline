"""Freeze the direct-Maxwell r4 Task 9 qualification without changing r3 defaults."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r4"

from prepare_task9_requalification_r3 import freeze


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
