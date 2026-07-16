"""Freeze the direct-Maxwell r8 generated-orientation Task 9 qualification."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r8"

from prepare_task9_requalification_r3 import freeze


if __name__ == "__main__":
    print(json.dumps(freeze(), indent=2))
