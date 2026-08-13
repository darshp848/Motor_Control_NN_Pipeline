"""FEMM 4.2 / pyFEMM replacement for the AEDT (Ansys Maxwell) EESM path.

Why this package exists
-----------------------
The Maxwell path hit a hard licence wall: AEDT Student caps 2D magnetostatic
solutions at ~2000 surface elements, and a refined 2517-element mesh was
rejected outright. Torque could therefore never be made accurate. The
decisive evidence is recorded in eesm/aedt/flux_extraction_v2.py NOTE 4: a
pure-q / negative-q mirror pair, whose flux linkages agree to 0.01%, produced
Torque_FEM values differing by 27.5%, and zero-torque points reported
0.004-0.005 N.m of spurious torque. That is solver noise, not physics.

FEMM 4.2 (build 21Apr2019) + pyFEMM 0.1.3 removes the cap and adds
antiperiodic boundaries, circuit flux linkage as a direct output, and a
sliding-band rotor-motion model.

Scope guard
-----------
Geometry, steel, and F1 (360 deg model) are closed. See
eesm/docs/PHASE0_TORQUE_CONVENTION.md. This package may generate the 90 deg
FEMM baseline. It is NOT authorised to freeze thresholds, promote a
surrogate, or start training until that baseline exists and the eight
manifest gates are committed.

The AEDT path under eesm/aedt/ is untouched and remains the parallel history.
"""

from __future__ import annotations

__all__ = ["config", "geometry", "extract", "campaign", "points", "runtime",
           "mock_femm"]
