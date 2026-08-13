# Torque-instrument review — F1 remainder

**Date:** 2026-08-12
**Status:** diagnostic complete 2026-08-12. F1 remains open. Not a campaign
authorization. Does not freeze thresholds or promote a surrogate.

## Contract

- **Outcome:** decide whether the leftover F1 miss is an even stress-tensor
  bias, and whether FEMM's air-gap / Arkkio integral is a usable second
  instrument on this 90° sector.
- **Current gate:** on the spec-rebuilt section, flux mirrors to 0.056% and
  closure passes, but weighted-stress-tensor |T| asymmetry is 3.1883% against
  the frozen 3% gate (`out/eesm/femm_f1_refined_r2_20260812/`).
- **Scope:** `eesm/femm/` geometry + extract, one new diagnostic runner, this
  document. Live FEMM 4.2 on two points only.
- **Evidence:** `out/eesm/femm_f1_instrument_<date>/f1_instrument.json`.
- **Stop rule:** stop after one honest diagnostic. Do not refine the mesh, do
  not move the 3% gate, do not start 64/128/256. If the same solve error
  repeats twice, preserve the `.fem` and stop.
- **Not included:** baseline campaign, threshold freeze, switching
  `torque_fem_nm` off weighted stress tensor, virtual-work sweep, 360° model.

## First principles

For a lossless conservative magnetic system in the amplitude-invariant dq
frame used by this foundry,

```
T = 1.5 * p * (λd * iq − λq * id)
```

is already the full-machine electromagnetic torque associated with the
winding-averaged fluxes. It is **not** an independent measurement: it is a
function of the same circuit fluxes F1 already trusts. On a d-axis mirror
pair `(id, iq, If)` and `(id, −iq, If)`, a geometrically symmetric machine
requires

```
T(id, iq, If) = −T(id, −iq, If).
```

Any measured pair therefore splits uniquely into

```
T_even = (T+ + T−) / 2     # does not reverse with current
T_odd  = (T+ − T−) / 2     # the physical reversing torque
```

`T_even` cannot be electromagnetic torque of the pair. It is instrument
bias, mesh bias, or a broken boundary. The r2 weighted-stress-tensor pair is
exactly this object:

| | N·m |
|---|---:|
| T+ | +2.8569 |
| T− | −2.7673 |
| T_even | **+0.04483** |
| T_odd | 2.8121 |
| identity T_even | ~0 |

Flux already mirrors (λd 0.056%, λq 0.012%). Identity torque therefore
mirrors. The 3.1883% |T| asymmetry is `2 * T_even / mean|T|`, not a scale
error and not a magnetic-state error. Mesh refinement from 29k to 210k
elements moved T_even only 0.050 → 0.045 N·m. Further refinement is the
wrong next experiment.

## Candidate second methods

| Method | What it measures | Independent of WST? | Cost |
|---|---|---|---|
| Identity from (λd, λq) | winding co-energy in dq | no — same fluxes | already in hand |
| Weighted stress tensor (block integral 22) | Maxwell stress on selected rotor groups | the current F1 instrument | already in hand |
| Air-gap line integral (`mo_lineintegral` type 4) | Maxwell stress on a mid-gap 90° arc | yes, different contour | one extra post-process call |
| Type-7 sliding band + `mo_gapintegral` 0 | Maxwell stress on an unmeshed band | yes | **refused** on this 90° sector |
| Virtual work ∂W′/∂θ | co-energy difference at ±δ | yes, energy not stress | two extra solves |
| Full 360° model | eliminates sector pairing | yes | new geometry |

Identity cannot close F1: k would be identically 1. Virtual work and a 360°
model stay reserved. Type-7 was the first attempt and failed on the first
live solve: `Material properties have not been defined for all regions`.
The saved model is
`out/eesm/femm_f1_instrument_20260812/eesm_sector.fem`. Both band arcs
carry `BdryType=7`, but a 90° open band is not a closed air-gap element, so
FEMM still sees an unlabeled region. That path is stopped.

The authorized second method is therefore the **same Maxwell-stress physics
on a contour**, implemented with `mo_lineintegral(4)` on a mid-airgap arc
from 0° to 90°. That does not change the r2 topology.

## Decisions locked before the solve

1. **Do not move the 3% gate** to admit 3.1883%.
2. **Do not replace `torque_fem_nm`** with the gap reading in this milestone.
   Both columns are recorded. Switching the campaign primary is a later,
   explicit decision.
3. **Do not put a type-7 sliding band in the default builder.** It does not
   solve on this sector. Rotor motion stays a later revision.
4. **Line-integral torque is treated as a sector quantity and ×4**, same as
   the block integral. That factor is a hypothesis the diagnostic must be
   able to falsify (k near 4 or 1/4 would show it).
5. **F1 remains open** unless the declared instrument — still weighted stress
   tensor unless a later commit says otherwise — passes both gates.

## Pass / fail on the diagnostic

On `(id, iq, If) = (0, ±30, 2)` A:

| Check | Pass |
|---|---|
| section solves; θ_d stays ~150° | required or stop |
| λd, λq still mirror | required or stop |
| identity T_even ≈ 0 | required or the pair is not a magnetic mirror |
| WST asymmetry ≤ 3% | F1 instrument on this model |
| gap asymmetry ≤ 3% | second method usable |
| k_WST, k_gap ∈ [0.90, 1.10] | closure, each instrument |

Interpretation (written before the solve; the live result is below):

- line-integral passes, WST still even-biased → leftover F1 miss is the
  block stress-tensor instrument; do not start the baseline until the
  primary column is chosen.
- both pass → F1 can be proposed closed on this model after a human look
  at the JSON.
- identity T_even is not ~0 → not an instrument question; re-open geometry.
- line integral has the wrong sign or |k| far from 1 → the open 90° arc is
  not a closed Maxwell surface; do not adopt it.

## Live result — 2026-08-12

Evidence: `out/eesm/femm_f1_instrument_line_20260812/f1_instrument.json`
(73,904 elements, default `airgap_mesh_fraction = 1/3`). Type-7 refusal:
`out/eesm/femm_f1_instrument_20260812/`.

| Instrument | T_even N·m | asymmetry | k | verdict |
|---|---:|---:|---|---|
| identity (from λ) | +0.00041 | 0.030% | 1 | magnetic mirror is clean |
| weighted stress tensor | −0.04310 | **3.061%** | 1.011 / 1.042 | closure pass, mirror fail |
| mid-gap line integral ×4 | −0.03763 | 3.563% | **−0.784 / −0.756** | not an instrument |

Flux λd/λq mirrors to 0.030% / 0.048%. θ_d = 150°. The machine state is a
mirror. The leftover F1 miss is still an even WST bias of ~0.043 N·m — the
same size as r2 (0.045 N·m at 210k elements), so it is not a mesh-density
effect.

The line integral is the **reaction** (wrong sign) on an **open** 90° arc.
Maxwell stress is defined on a closed surface around the rotor. An open
sector arc omits the antiperiodic edges, so ×4 cannot recover T. Do not
flip the sign to dress k. Do not adopt this readout.

**F1 stays open. Baseline stays blocked.** Next independent method, if
authorized, is virtual work (∂W′/∂θ at fixed current) or a 360° model —
both supply a closed energy or closed surface. Do not retry type-7 on this
sector. Do not move the 3% gate.

## Live result — detent, |iq| sweep, virtual work

Evidence:

- `out/eesm/femm_f1_blocker_20260812/f1_blocker.json`
- `out/eesm/femm_f1_even_sweep_20260812/even_sweep.json`

Field-only WST at the same locked angle is **−0.0067 N·m**, only 16% of the
pair's T_even (−0.043 N·m). Simple If-only detent does **not** explain the
mirror miss. `mi_moverotate` virtual work returned identical coenergy at ±δ
(T=0) — the rotor groups did not actually move; that energy number is not
evidence.

T_even vs |iq| at If = 2 A, 73,904 elements:

| |iq| A | T_even N·m | T_odd N·m | k_odd | |T| asym % |
|---:|---:|---:|---:|---:|
| 0 | −0.0067 | 0 | — | — |
| 15 | −0.0251 | 1.767 | 1.121 | 2.84 |
| 30 | −0.0431 | 2.816 | **1.027** | 3.06 |
| 45 | −0.0605 | 3.137 | 0.931 | 3.86 |
| 60 | −0.0596 | 3.643 | 0.886 | 3.27 |

T_even is almost linear in |iq| up to 45 A, then saturates. It is
reproducible and mesh-stable (0.045 N·m at 210k, 0.043 N·m at 74k). Identity
T_even stays ~0. Flux still mirrors to 0.03%.

So the leftover is a **load-linear even Maxwell residual**, not AEDT-style
instrument noise and not field-only cogging. The flux map and the dq identity
do not contain it. At the **declared F1 point** (0, ±30, 2):

- flux mirror 0.030%
- identity mirror 0.030%
- k on raw WST 1.011 / 1.042 (closure **pass**)
- k on T_odd 1.027 (closure **pass**)
- |T+| vs |T−| 3.061% (letter of the 3% gate **fail**)

Type-7 is still not a working second instrument on this sector (open band
refused; `<No Mesh>` became a hole and still refused). A 360° model would
test whether T_even is a sector-AP artifact; that is the remaining
independent experiment, not another mesh refine.

Do not start the 64-point baseline until this even residual is either
accepted as a reported (not map) quantity or killed by a 360° / working
energy method. Do not move the 3% number.

## Live result — 360 deg model, 2026-08-12

Evidence: `out/eesm/femm_f1_360_20260812/f1_360.json` (285,339 elements,
no antiperiodic cuts, odd poles sign-flipped).

| | 90° sector | 360° full |
|---|---:|---:|
| T_even | −0.04310 N·m | **−0.00236 N·m** |
| \|T\| asymmetry | 3.061% | **0.168%** |
| k | 1.011 / 1.042 | **1.0235 / 1.0255** |
| k_odd | 1.027 | 1.0245 |
| λd mirror | 0.030% | 0.034% |
| field λq | — | −3.3e-6 Wb |
| field WST | −0.0067 N·m | −0.00088 N·m |
| F1 letter | fail | **pass** |

T_even dropped by **18×**. Flux scale 1/4 is confirmed (k ≈ 1.02, not 4 or
0.25). Field-only λq ≈ 0, so the odd-pole winding flip is right.

**The 90° sector's 3% miss was the antiperiodic cuts, not the geometry,
steel, or identity.** F1 passes on the 360° model. The production 90° path
is still faster, but its WST even residual is a sector artifact and must
not be used to fail or retune the 3% gate. Campaign torque on the sector
should be identity or T_odd, or F1 should be cited from the 360° evidence.
Do not start the 64-point baseline until that choice is explicit.
