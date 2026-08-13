"""Phase 1 diagnostic metrics for the EESM magnetic map.

Everything in this package is a REPORTED DIAGNOSTIC. None of it carries a
frozen threshold, and none of it may influence promotion. Turning any of these
into a gate requires a new pre-registered phase with its own threshold freeze,
per `research_planning/eesm_protocol/EXPERIMENT_PROTOCOL.md` gate order step 2.

Modules
-------
reciprocity
    Mixed-partial identities of the co-energy, in the amplitude-invariant
    convention. Discriminates physics-structured families from unstructured
    ones by several orders of magnitude.
ldiff
    Incremental-inductance error against the FEM finite-difference anchors.
field_gauge
    The one-dimensional gauge freedom in zero-shot lambda_f recovery, plus the
    If-only control that keeps the zero-shot claim honest.
"""

from metrics import field_gauge, ldiff, reciprocity

__all__ = ["field_gauge", "ldiff", "reciprocity"]
