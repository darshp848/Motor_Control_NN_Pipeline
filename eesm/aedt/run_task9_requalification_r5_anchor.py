"""AEDT wrapper for one frozen direct-r5 quarter-sector qualification anchor.

The shared runner preserves raw quarter-sector flux/coenergy/torque evidence,
scales flux and coenergy by four before full-machine closure calculations, and
requires ``Torque_FEM == 4*Torque_FEM_Sector``.  This wrapper is intentionally
bound to the write-once r5 attempt-1 campaign directory.
"""

import os

os.environ["EESM_REQUAL_MODE"] = "r5"
os.environ["EESM_R5_CAMPAIGN_ROOT"] = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "out", "eesm", "task9_requalification_r5_attempt1_20260716",
)
target = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "run_task9_requalification_r3_anchor.py")
scope = globals().copy()
scope["__file__"] = target
scope["__name__"] = "__main__"
execfile(target, scope)
