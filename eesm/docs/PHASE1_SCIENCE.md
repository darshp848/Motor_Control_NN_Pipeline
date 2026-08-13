# Phase 1 science: field flux, reciprocity, and L_diff

**Status:** implemented and dry-run verified 2026-08-13. The numbers below come
from a dry run on the finished campaign; the authoritative run is whatever
`eesm/run_phase1_science.py` writes into a fresh output root on a clean commit.
**Not** a threshold freeze, **not** a promotion, and it does not supersede
`out/eesm/phase1_close_20260813/`.
**Conventions:** `eesm/docs/DQ_CONVENTIONS.md` (read first).

## Why this exists

`out/eesm/phase1_close_20260813/` registered `energy_gradient_net` and `pwa`
and then scored them on the Phase 0 axes only: two outputs, the eight frozen
gates, torque-RMSE ranking. All 54 cells passed every gate, so the gates did no
discriminating work and the promoted candidate was unchanged from Phase 0.

None of the physics that motivates a structured surrogate was measured:

* `prediction_outputs` was still `[lambda_d_wb, lambda_q_wb]` -- lambda_f never
  entered schema v2, although `lambda_field_wb` is populated on all 1759
  campaign rows.
* No reciprocity metric existed. The strings `reciprocity` and `l_diff`
  appeared only in `eesm/femm/fd_anchors.py` and its tests.
* The 8 FD Hessian anchors (48 solves, 595 s) were computed and then consumed
  by nothing.

This document specifies the three missing pieces and records the dry-run
evidence that they behave as the physics predicts.

## 1. lambda_f as a third output

Raw `lambda_field_wb` on the 90 degree model is **one pole**. Terminal field
flux linkage is `4 x lambda_field_wb`. Surrogates are trained on the terminal
quantity, because that is what reciprocity relates to lambda_d and lambda_q.

The v1 point schema forbids `lambda_f_wb`, and that stays true: the frozen
Phase 0 experiment is untouched. `eesm/configs/eesm_experiment_manifest_v2_1.json`
is a new sibling manifest that declares three prediction outputs.
`eesm_experiment_manifest_v2.json` is **not** edited -- its SHA-256 is recorded
inside the Phase 1 bundle, so editing it in place would silently invalidate
that bundle's provenance.

## 2. Reciprocity as a cross-family metric

For a conservative machine, in the amplitude-invariant convention:

```text
R_dq = d(lambda_d)/d(iq) - d(lambda_q)/d(id)
R_fd = d(lambda_f)/d(id) - (3/2) d(lambda_d)/d(If)
R_fq = d(lambda_f)/d(iq) - (3/2) d(lambda_q)/d(If)
```

The `3/2` is not optional and the sector factor is not optional. On the
measured anchors the naive form `d(lambda_f)/d(id) - d(lambda_d)/d(If)` is
**2798x** larger than the correct one, so `R_fd_naive` is computed and reported
as a permanent tripwire: it must stay large.

Jacobians come from central differences **at the same steps the FD anchors
used** (`h = 1.0, 1.0, 0.2 A`). That is deliberate. Both sides are then the
same secant slope over the same interval, so the comparison measures model
error rather than differencing error, and no family needs to expose an
analytic gradient. Points without `+/- h` room inside the map domain are not
evaluated, exactly as the anchors required.

**A surrogate cannot beat the FEM truth's own reciprocity residual.** Those
floors are read from the anchors bundle and reported alongside every number:

| identity | FEM floor |
|---|---|
| `R_dq` | 5.367e-08 H |
| `R_fd` | 3.998e-06 H |
| `R_fd_naive` | 1.119e-02 H (must stay large) |

### Dry-run result

RMS residual across all 9 strategy-budget cells, in henries:

| family | `R_dq` | `R_fd` |
|---|---|---|
| `energy_gradient_net` | 8.9e-08 .. 7.4e-07 | 2.7e-06 .. 1.8e-05 |
| `compact_mlp` | 4.4e-05 .. 8.7e-05 | 3.6e-04 .. 1.3e-03 |
| `physics_polynomial` | 1.1e-05 .. 2.0e-04 | 5.5e-04 .. 2.3e-03 |
| `rbf_or_gp` | 1.6e-05 .. 3.8e-04 | 1.5e-03 .. 5.8e-03 |
| `tree_ensemble` | 9.5e-04 .. 2.9e-03 | 2.1e-02 .. 7.5e-02 |
| `pwa` | 3.4e-04 .. 4.9e-03 | 3.3e-03 .. 4.3e-02 |

The co-energy net sits at the measurement floor; every other family is two to
five orders of magnitude above it. **This is the discriminating axis the frozen
gates never had.** Torque RMSE spread the same 54 cells over a single order of
magnitude and passed all of them.

## 3. L_diff against the FD anchors

Surrogate Jacobian versus the measured Jacobian at the 8 anchor centres, per
component and as a relative Frobenius norm. The field row is compared to
`Lfd_terminal` / `Lfq_terminal` / `Lff_terminal`; using the raw sector row
reintroduces the factor-of-four bug the anchors exist to catch. A 2-output
model is scored on the stator block and the field row is marked unavailable
rather than zero-filled.

### Dry-run result, `tensor_grid | 256`

| family | off-diagonal mean rel RMSE | Frobenius rel RMSE |
|---|---|---|
| `energy_gradient_net` | 0.178 | 0.069 |
| `compact_mlp` | 0.444 | 0.091 |
| `rbf_or_gp` | 0.469 | 0.392 |
| `physics_polynomial` | 0.805 | 0.824 |
| `pwa` | 1.071 | 0.163 |
| `tree_ensemble` | 1.290 | 1.129 |

**The off-diagonal incremental inductances are every family's weak point**, by
a wide margin over the diagonal. That matters beyond this study: the LUT-free
online reference generators (Saren et al., arXiv 2607.08528) consume exactly
the incremental inductance matrix, so this is the number that prices their
method's input, and nobody has published it.

## 4. The zero-shot lambda_f ablation

Train the co-energy net on `(lambda_d, lambda_q)` only and read lambda_f off
the same potential as `dW'/dIf`.

**Identifiability.** Matching only the stator gradient determines W' up to an
additive function of the field current alone, so

```text
lambda_f_fit(x) = lambda_f_true(x) + g'(If)
```

Every id/iq dependence of the field flux linkage -- the armature-reaction part,
which is the part a controller needs -- is fully pinned by reciprocity and
needs no lambda_f truth at all. Only a **one-dimensional** gauge is missing.
`eesm/src/metrics/field_gauge.py` fits `g'(If)` as a cubic on **training rows
only**; the gauge is part of the model, not part of the evaluation.

**The control that makes the claim honest.** lambda_f correlates with If, so
the ablation reports a cubic fit of lambda_f on If alone. If the zero-shot
prediction did not beat that by a wide margin, the result would be about
correlation, not energy consistency.

### Dry-run result

| cell | gauge-fixed lambda_f RMSE | If-only control | ratio | gauge R^2 (out-of-sample) |
|---|---|---|---|---|
| `random \| 256` | 7.42e-03 Wb | 5.89e-01 Wb | 79x | 0.9981 |
| `tensor_grid \| 256` | 9.72e-03 Wb | 5.75e-01 Wb | 59x | 0.9970 |
| `tensor_grid \| 128` | 1.81e-02 Wb | 5.75e-01 Wb | 32x | 0.9860 |
| `latin_hypercube \| 64` | 2.19e-01 Wb | 5.82e-01 Wb | 2.7x | 0.7572 |

Selection-set lambda_f has sigma = 0.696 Wb, so the best cell recovers the
terminal field flux linkage to **1.07% of its standard deviation without ever
seeing a field-flux label**. The gauge R^2 rises 0.55 -> 0.99 with budget,
which is the identifiability prediction behaving exactly as derived: as the
stator fit tightens, the residual collapses onto a function of If alone.

At budget 64 the ablation is not yet in its asymptotic regime (R^2 = 0.55-0.84).
Report that, do not hide it.

## 5. Field supervision improves the stator map

The zero-shot arm uses the **same architecture, epochs and seed** as the
supervised arm, so toggling `field_supervision` is a controlled comparison.
Selection torque RMSE, N.m:

| cell | supervised (3 out) | unsupervised (2 out) | ratio |
|---|---|---|---|
| `tensor_grid \| 64` | 1.0432 | 3.7117 | 3.56 |
| `tensor_grid \| 128` | 0.5947 | 1.3756 | 2.31 |
| `tensor_grid \| 256` | 0.1774 | 0.3175 | 1.79 |
| `random \| 64` | 0.8205 | 1.9885 | 2.42 |
| `random \| 128` | 0.4951 | 0.9553 | 1.93 |
| `random \| 256` | 0.2475 | 0.1513 | 0.61 |
| `latin_hypercube \| 64` | 2.0983 | 3.6806 | 1.75 |
| `latin_hypercube \| 128` | 0.4204 | 0.7415 | 1.76 |
| `latin_hypercube \| 256` | 0.2833 | 0.4295 | 1.52 |

Eight of nine cells improve, by 1.5x to 3.6x. **The field-flux side channel was
already being collected for free on every campaign row and then discarded;
using it as a third output on a co-energy net makes the stator map better.**
One cell (`random | 256`) goes the other way, so state this as eight of nine,
not as universal.

## 6. Harness cross-check

`latin_hypercube | 256 | rbf_or_gp` scores torque RMSE **0.3669 N.m** here,
matching the promoted candidate in `out/eesm/phase1_close_20260813/` to four
decimal places. The training designs are therefore byte-identical to the frozen
study's -- this runner reuses `experiments.equal_budget._sample_training`,
`_derived_seed` and `_validate_manifest` rather than reimplementing them.

The best cell in this study, `tensor_grid | 256 | energy_gradient_net` at
**0.1774 N.m**, is 2.07x better than that promoted candidate. That is a
diagnostic observation, not a promotion: see below.

## 7. What this phase deliberately does not do

* **It does not retune, re-derive, or re-freeze the eight thresholds.** They are
  read from the manifest and applied unchanged.
* **Reciprocity and L_diff are diagnostics.** They carry no threshold and gate
  nothing. Promoting on them requires a new pre-registered phase with its own
  threshold freeze, per `EXPERIMENT_PROTOCOL.md` gate order step 2. The fact
  that the energy net now wins on every axis is exactly why the promotion must
  not be moved inside this phase -- that would be selecting a model after
  seeing the metric that favours it.
* **It runs no FEMM solve.** Every number derives from the finished campaign
  and the existing anchors.
* It writes only to a fresh output root, and refuses a non-empty one or any
  path near `task9_baseline` / the identity freeze.

## 8. Files

| Path | Role |
|---|---|
| `eesm/src/metrics/reciprocity.py` | identities, central-difference Jacobian, FEM floors |
| `eesm/src/metrics/ldiff.py` | incremental-inductance error vs the anchors |
| `eesm/src/metrics/field_gauge.py` | the 1-D gauge and the If-only control |
| `eesm/src/surrogates/energy_gradient.py` | 3-output co-energy net, `field_supervision` switch |
| `eesm/configs/eesm_experiment_manifest_v2_1.json` | Phase 1 science manifest (v2 untouched) |
| `eesm/run_phase1_science.py` | the study runner |
| `eesm/tests/test_phase1_metrics.py` | 28 tests, including wrong-convention tripwires |

`base.py`, `pwa.py` and `mlp.py` gained an `n_outputs` generalization that
defaults to 2, so every Phase 0 path behaves exactly as before.
