# Amplitude-invariant dq / field conventions

**Status:** appendix to the Phase 0 contract. Not a threshold freeze and
not authorization to write a v2 energy-network model.
**Date:** 2026-08-13

This is the document the 2026 H2 roadmap required before any co-energy
network is coded. The ×4 torque, 1000× depth, and 77 mm-stack mistakes
were all convention bugs. Read this before touching λf, L_diff, or W′.

## What the pipeline uses

Peak, amplitude-invariant Park. Executable pins:

- `eesm/femm/extract.py` `dq_from_abc` / `abc_from_dq` (2/3 forward)
- `eesm/femm/extract.py` `torque_from_dq` → `T = 1.5 · p · (λd iq − λq id)`
- manifest objective `1.5 * rs_ohm * (id_a^2 + iq_a^2) + rf_ohm * if_a^2`
- `eesm/src/scheduler/copper_loss_scheduler.py` (same two formulas)

`id`, `iq`, `λd`, `λq` have the same peak amplitude as the corresponding
phase quantity. `If` and `λf` are DC field quantities. They do **not**
carry a 3/2.

## Co-energy and the 3/2 that is easy to get wrong

For a lossless conservative system the co-energy differential in these
coordinates is

```text
dW′ = (3/2) λd did + (3/2) λq diq + λf dIf
```

so the only consistent outputs of a co-energy network are

```text
λd = (2/3) ∂W′/∂id
λq = (2/3) ∂W′/∂iq
λf =      ∂W′/∂If
```

Stator–field reciprocity is then the mixed-partial identity on W′,

```text
∂λf/∂id = (3/2) ∂λd/∂If
∂λf/∂iq = (3/2) ∂λq/∂If
∂λd/∂iq =       ∂λq/∂id
```

The naive statement `∂λf/∂id = ∂λd/∂If` is **false** in this convention.
It is true in power-invariant Park and in some referred-rotor / per-unit
frames (Preindl 2026, Hinkkanen 2026). Copying those papers’ L-symmetry
into this codebase without the 3/2 will pin a wrong constraint.

Incremental inductances inherit the same factor:

```text
Ldd = ∂λd/∂id    Lqq = ∂λq/∂iq    Lff = ∂λf/∂If
Ldq = ∂λd/∂iq = ∂λq/∂id
Ldf = ∂λd/∂If    Lfd = ∂λf/∂id = (3/2) Ldf
Lqf = ∂λq/∂If    Lfq = ∂λf/∂iq = (3/2) Lqf
```

A Hessian of W′ is therefore **not** the inductance matrix in (id, iq, If)
until the 2/3 and 3/2 scalings are applied.

## Sector and circuit scaling (FEMM)

These are independent of Park and have already been burned once:

| Quantity | 90° sector | 360° machine |
|---|---|---|
| Terminal phase flux from FEMM circuits | ×1 (already terminal) | ÷4 (four poles on one circuit) |
| WST block integral 22 | ×4 | ×1 |
| dq identity torque | ×1 (never a sector factor) | ×1 |

Stator current injected into the modelled branch is `I_terminal / 4`.
Field current is the commanded terminal current.

Raw `lambda_field_wb` on the 90° model is **one pole**. Terminal field
flux is `4 × lambda_field_wb`. The 2026-08-13 FD anchors make this
load-bearing: `|4 ∂λf_sector/∂id − (3/2) ∂λd/∂If| ≤ 4e-6 H`.
Campaign CSVs keep the raw side-channel; apply the ×4 only when
comparing to λd / λq.

## Schema

- Map outputs are `lambda_d_wb`, `lambda_q_wb`.
- `lambda_f_wb` is **forbidden** by `eesm_point.schema.json`.
- Field flux, if captured, is the side-channel `lambda_field_wb`.
- Campaign torque reader: `eesm.femm.campaign.campaign_torque_nm`.

## What this appendix does not authorize

Energy-gradient nets, PWA Hessians, finite-difference L_diff campaigns,
threshold writes, or any change to the running FEMM solve.
