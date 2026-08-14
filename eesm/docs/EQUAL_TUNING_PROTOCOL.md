# Equal-tuning-budget family comparison — pre-registration

**Status:** protocol declared 2026-08-14, **not yet run**. Nothing in this
document may be revised after the first authoritative run.
**Motivation:** `eesm/docs/TUNING_EFFORT_CONFOUND.md`.
**Manifest:** `eesm/configs/eesm_experiment_manifest_v3_0.json`.
**Runner:** `eesm/run_equal_tuning.py`.

## Why

Phase 0 equalised the *data* budget and not the *tuning* budget. The GP was run
with `optimizer=None`, so its kernel was never fitted; the compact MLP was run
for 300 epochs with no early stopping, on a curve that varies by more than 4x.
The two corrections move the ranking in opposite directions, so the frozen study
did not identify a family ordering. This protocol makes tuning effort an
explicit, equal, declared resource so that a family comparison means something.

The frozen Phase 0 and Phase 1 experiments are untouched. This is a new
experiment with its own manifest and its own output root.

## The rule

Every family receives **the same number of configuration evaluations**, drawn
from a **declared search space**, scored on an **inner split of the training
design only**. The `selection` set is never touched during tuning; it is used
exactly once per cell, after the configuration is chosen.

### 1. Design matrix

Unchanged from Phase 0: 3 sampling strategies x 3 budgets (64/128/256) x 6
families. Training designs are the frozen ones, regenerated from the same
`_derived_seed` / `_sample_training` path, so the training currents are
byte-identical to Phase 0's.

### 2. Tuning budget

`n_configs = 24` per (family, cell), sampled by seeded random search from that
family's declared space. Random search at equal budget is the fair comparator:
it needs no per-family tuning of the tuner.

A family whose space contains fewer than 24 distinct configurations evaluates
all of them and the runner records `n_configs_effective` and
`budget_shortfall = true`. `pwa` has no hyperparameters and will report
`n_configs_effective = 1`; that is a declared property of the family, not a
handicap imposed by the protocol, and it must be stated wherever `pwa` is
ranked.

### 3. Inner scoring

`k_inner = 3`-fold cross-validation **on the training design only**. Folds are
deterministic given the design and the split seed. A configuration's inner
score is the mean identity-torque RMSE across held-out inner folds, using the
same torque definition as Phase 0,
`T = 1.5 p (lambda_d i_q - lambda_q i_d)`.

Ties are broken by lower mean inner flux RMSE, then by the configuration's
index in the seeded draw. Promotion inside the tuner is therefore deterministic.

### 4. Refit and seed replication

The winning configuration is refitted on the **full** training design, then
replicated over `n_seeds = 5` model seeds. The cell's reported score is the
**median** across seeds, with the interquartile range reported alongside. No
single-seed number is reported as a headline.

Deterministic families (`physics_polynomial`, `rbf_or_gp`, `tree_ensemble` at
fixed seed, `pwa`) will show zero spread; that is recorded rather than assumed.

### 5. Outputs

Two outputs (`lambda_d_wb`, `lambda_q_wb`) so all six families are directly
comparable on the Phase 0 axes. The three-output comparison including terminal
`lambda_f` is a **separately declared variant**, not this experiment.

### 6. What is fixed before running

- the six families and their search spaces (below)
- `n_configs = 24`, `k_inner = 3`, `n_seeds = 5`
- inner metric = mean held-out identity-torque RMSE
- the tie-break order
- torch determinism pinned via `surrogates/torch_determinism.py`
- the eight Phase 0 thresholds, read unchanged and applied as admissibility
  floors; **this experiment does not re-derive or re-freeze any threshold**

### 7. What this experiment does not do

- It does not promote anything into any frozen bundle.
- It does not touch `scheduler_audit`.
- It does not change Phase 0 or Phase 1 results.
- It does not use reciprocity or L_diff as gates; those remain diagnostics.

## Declared search spaces

Sampled uniformly over the listed choices; `loguniform` is uniform in log10 over
the stated interval.

| Family | Hyperparameter | Space |
|---|---|---|
| `physics_polynomial` | `degree` | {2, 3, 4} |
| | `alpha` | loguniform [1e-9, 1e0] |
| `rbf_or_gp` | `optimizer` | fixed `fmin_l_bfgs_b` |
| | `n_restarts_optimizer` | {0, 3, 8} |
| | `length_scale` | {0.5, 1.0, 2.0} isotropic, or ARD `[l, l, l]` |
| | `ard` | {false, true} |
| | `noise_level` | loguniform [1e-9, 1e-2] |
| `tree_ensemble` | `n_estimators` | {100, 300, 600} |
| | `max_depth` | {null, 8, 16, 32} |
| | `min_samples_leaf` | {1, 2, 4} |
| `compact_mlp` | `hidden_width` | {16, 32, 64, 128} |
| | `learning_rate` | loguniform [1e-3, 3e-2] |
| | `epochs` | {300, 600, 1200, 2400, 4800} |
| `energy_gradient_net` | `hidden_width` | {16, 32, 64, 128} |
| | `learning_rate` | loguniform [1e-3, 3e-2] |
| | `epochs` | {300, 600, 1200, 2400} |
| | `field_supervision` | fixed `false` (two-output comparison) |
| `pwa` | — | none |

`epochs` is inside the search space deliberately. Phase 0 fixed it by hand at a
value that turned out to be the worst of every value tested; letting the inner
split choose it is what makes the MLP comparison fair. Early stopping on the
inner fold is the alternative and would be preferable, but it requires changing
the surrogate training loop; searching `epochs` achieves the same fairness
without touching the frozen family implementations.

## Cost

Inner fits: `24 configs x 3 folds x 9 cells x 6 families = 3888`, plus
`5 seeds x 9 cells x 6 families = 270` refits. The neural families dominate.
Estimated wall time on one CPU core is roughly 1-1.5 hours (measured: a reduced smoke run of 4 configs / 2 folds / 2 seeds took 4m55s). No FEMM solve is
required — the finished 1759-point campaign supplies all truth.

**Do not start this while the replicate-design FEMM campaign is running.** It
would contend for the same cores and slow the campaign.

## How to run

Smoke test first (reduced budget, scratch root, proves the plumbing without
producing an authoritative result):

```
python eesm/run_equal_tuning.py --manifest eesm/configs/eesm_experiment_manifest_v3_0.json \
  --campaign out/eesm/femm_equal_budget_20260813/femm_results.csv \
  --out out/eesm/equal_tuning_smoke --smoke
```

Authoritative run, on a clean commit:

```
python eesm/run_equal_tuning.py --manifest eesm/configs/eesm_experiment_manifest_v3_0.json \
  --campaign out/eesm/femm_equal_budget_20260813/femm_results.csv \
  --out out/eesm/equal_tuning_YYYYMMDD
```

The runner refuses a non-empty output root, refuses any path near
`task9_baseline` or the identity freeze, asserts train/selection disjointness
before any fit, and records `working_tree_may_be_dirty` in its bundle.

## How to read the result

The question this answers is **not** "which family is best". It is: *once every
family has had the same opportunity to be tuned, is any family reliably better,
and by how much relative to seed spread?*

Report a family as better in a cell only when its seed-median beats the other's
and the two interquartile ranges do not overlap. Where they overlap, report a
tie. If the ordering still changes with budget after equal tuning, that is a
real and reportable finding; if it stops changing, then the Phase 0 crossover
was a tuning artefact and should be reported as such.
