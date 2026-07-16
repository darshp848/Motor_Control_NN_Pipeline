"""AEDT wrapper for one frozen direct-r7 quarter-sector anchor.

The shared runner preserves raw sector evidence and requires the explicit
manual x4 identities.  This wrapper never relaxes those gates.
"""

import os

os.environ["EESM_REQUAL_MODE"] = "r7"
os.environ["EESM_R7_CAMPAIGN_ROOT"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "out", "eesm", "task9_requalification_r7_attempt1_20260716",
)
target = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "run_task9_requalification_r3_anchor.py")
scope = globals().copy()
scope["__file__"] = target
scope["__name__"] = "__main__"
execfile(target, scope)
