"""AEDT wrapper selecting the direct-r4 one-anchor qualification mode."""

import os

os.environ["EESM_REQUAL_MODE"] = "r4"
target = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "run_task9_requalification_r3_anchor.py")
scope = globals().copy()
scope["__file__"] = target
scope["__name__"] = "__main__"
execfile(target, scope)
