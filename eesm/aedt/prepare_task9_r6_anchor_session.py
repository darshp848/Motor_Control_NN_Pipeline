"""Prepare the next immutable direct-r6 quarter-sector anchor copy."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r6"

from prepare_task9_r3_anchor_session import prepare


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
