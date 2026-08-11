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
This package is qualified for CONVENTION AND PLUMBING only. It is NOT
authorised for dataset generation, promotion, or training. Two inputs are
still missing (see eesm/docs/FEMM_MIGRATION.md):

  - the real BH curve (a documented placeholder steel is used), which makes
    any point the manifest would label 'saturation' physically meaningless;
  - a confirmed airgap dimension (RMxprt emitted conflicting DiaGap values).

The AEDT path under eesm/aedt/ is untouched and remains the parallel history.
"""

from __future__ import annotations

__all__ = ["config", "geometry", "extract", "campaign", "points", "runtime",
           "mock_femm"]
