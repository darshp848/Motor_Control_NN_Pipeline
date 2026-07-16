"""Prepare the next immutable direct-r4 anchor project copy."""

import json
import os

os.environ["EESM_REQUAL_MODE"] = "r4"

from prepare_task9_r3_anchor_session import prepare


if __name__ == "__main__":
    print(json.dumps(prepare(), indent=2))
