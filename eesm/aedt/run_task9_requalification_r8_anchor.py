"""AEDT wrapper for one frozen direct-r8 quarter-sector anchor."""

import os

os.environ["EESM_REQUAL_MODE"] = "r8"
os.environ["EESM_R8_CAMPAIGN_ROOT"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "out", "eesm", "task9_requalification_r8_attempt1_20260716",
)
target = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "run_task9_requalification_r3_anchor.py")
scope = globals().copy()
scope["__file__"] = target
scope["__name__"] = "__main__"
execfile(target, scope)
