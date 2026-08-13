# Finite-difference Hessian anchors (design only)

**Status:** run 2026-08-13. Evidence:
`out/eesm/femm_fd_anchors_20260813/fd_anchors.json` (8 centres, 48
offset solves, `femm_4.2`, 595 s). Not a threshold freeze or
promotion gate.
**Date:** 2026-08-13

Phase 1 needs L_diff validation truth. The cheap way in FEMM is a
central difference at a handful of already-solved interiors:

```text
∂λ/∂x ≈ [λ(x+h) − λ(x−h)] / (2h)     x ∈ {id, iq, If}
```

That is 6 extra solves per anchor (plus the already-solved centre).
Eight anchors → 48 new solves, about 10 minutes after the big campaign.

## Steps (fixed before any solve)

| Axis | h | Domain room required |
|---|---|---|
| id | 1.0 A | id ∈ [−119, −1] |
| iq | 1.0 A | iq ∈ [1, 119] |
| If | 0.2 A | If ∈ [0.2, 14.8] |

Steps are small versus the map box and large versus solver noise at
73,904 elements. Do not retune h after seeing L_diff.

## Anchor selection rule

Take `train` / `interior` rows from a finished campaign whose centre
already has FEMM truth and whose ±h box stays inside
`id ∈ [−120, 0]`, `iq ∈ [0, 120]`, `If ∈ [0, 15]`. Prefer spread in
|is| and If. Do not use `scheduler_audit`.

A first candidate list will be written from the 64-point baseline after
this design is accepted; it is not frozen here because those centres
are Task 9 identities, not equal-budget identities. Prefer equal-budget
interior centres once that campaign completes.

## Output contract

New directory only, for example
`out/eesm/femm_fd_anchors_YYYYMMDD/`. Each row stores the centre
`point_id`, the six offset currents, the six (λd, λq, λf) readings,
and the three estimated Jacobian columns. Reciprocity checks use
`eesm/docs/DQ_CONVENTIONS.md` (∂λf/∂id ≟ (3/2) ∂λd/∂If).

## Live result (2026-08-13)

Stator reciprocity holds: max |Ldq − Lqd| = 5.4e-8 H.

Raw `lambda_field_wb` is one pole. With terminal λf = 4 × sector field
flux, max |4 Lfd − 1.5 Ldf| = 4.0e-6 H. That is the amplitude-invariant
identity in `DQ_CONVENTIONS.md`. Do not treat raw (unscaled) Lfd as
equal to Ldf.

## Not authorized by this note

Writing thresholds, fitting, or treating FD L_diff as a promotion gate.
