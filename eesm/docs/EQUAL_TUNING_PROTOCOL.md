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

Running beside a FEMM campaign is fine **provided the study is pinned off the
cores the campaign uses** — see below. Unpinned, it would contend for the same
cores and slow the campaign.

`--workers N` parallelises the inner cross-validation across processes. The
inner fits are independent and individually seeded, so this changes wall time
only: a 2-worker smoke run reproduces the serial run's medians and selected
configurations exactly.

### Running beside a FEMM campaign

FEMM 4.2 is single-threaded, so a campaign occupies one core and leaves the rest
idle. `--cpu-affinity` places this study on a chosen set of logical CPUs and
`--priority below-normal` makes it yield, so the two can share a machine.

The workstation used here is an **Intel Core Ultra 7 255HX: 8 P-cores + 12
E-cores, 20 threads, no hyper-threading**. With no SMT there is one logical CPU
per core.

**Do not assume P-cores come first.** Measured on this machine 2026-08-14, the
fast cores are **0-1, 6-9, 18-19** and the efficient cores are **2-5, 10-17** —
interleaved, not contiguous. The 8/12 split matches the datasheet, but the
ordering does not match the conventional "P first, then E" layout at all, and a
mask derived from that assumption would have placed the study on four P-cores
while leaving four E-cores idle. Enumeration order is a firmware choice. Measure
it:

```
python eesm/studies/cpu_topology.py
```

which times a fixed workload pinned to each logical CPU and clusters the
results. It refuses to guess when the split is not cleanly bimodal. Reading
per-CPU maximum frequency does **not** work for this on Windows: psutil reports
the same advertised maximum for every CPU.

Then, to leave all eight P-cores to FEMM and run the study entirely on the
twelve E-cores:

```
python eesm/run_equal_tuning.py --manifest eesm/configs/eesm_experiment_manifest_v3_0.json \
  --campaign out/eesm/femm_equal_budget_20260813/femm_results.csv \
  --out out/eesm/equal_tuning_YYYYMMDD --workers 12 --cpu-affinity 2-5,10-17 \
  --priority below-normal
```

Equivalent without the `psutil` dependency, applied at process creation so every
child inherits it:

```
start /affinity 3FC3C /belownormal python eesm\run_equal_tuning.py ...
```

Measured here, the E-cores run at about 55% of P-core throughput. That does not
matter: the work is 3888 independent fits, so aggregate throughput is what counts,
and twelve E-cores comfortably beat one P-core. Expect roughly 10-20 minutes
rather than the 1-1.5 hours a single core needs.

Placement is a scheduling concern only. Each fit is single-threaded — the
determinism pin sets `num_threads=1` — and independently seeded, so which core
runs it cannot change a result; a pinned 2-worker smoke run reproduces the
unpinned serial run exactly. The effective CPU set and priority are recorded
under `cpu_placement` in the study JSON, because they are part of the compute
environment even though they are not part of the result.

### Why this runs on CPU and not on a GPU

Measured, not assumed:

- **Four of the six families have no GPU path at all.** `physics_polynomial`,
  `rbf_or_gp` and `tree_ensemble` are scikit-learn; `pwa` is SciPy Delaunay plus
  least squares. Only `compact_mlp` and `energy_gradient_net` are Torch.
- **The models are tiny.** The largest config is 17,282 parameters on a 256x3
  input, full batch. A step costs 526-1742 us on one CPU thread here. GPU
  kernel-launch overhead is a large fraction of that for tensors this small, and
  occupancy would be a few percent.
- **The pipeline is float64.** Consumer NVIDIA parts run FP64 at roughly 1/32 to
  1/64 of their FP32 rate, so the usual GPU advantage largely evaporates.
  Dropping to float32 would change every number and is not acceptable in a study
  whose subject is reproducibility.
- **It would break the determinism pin.** `surrogates/torch_determinism.py` is
  CPU-only by construction and reports `cuda_used: false`. CUDA numerics differ
  from CPU, which would reintroduce exactly the cross-environment divergence
  (up to 153% at fixed seed) that the pin was written to eliminate, and would
  make these results incomparable with the CPU-pinned Phase 1 numbers.

The available speedup is process parallelism over the 3888 independent inner
fits, which is what `--workers` provides and which changes no number.

A GPU would become worth revisiting if the workload changes shape: much larger
networks, a far larger truth set, or batched training of many small networks at
once via `torch.vmap`. That last one is a genuine GPU play, but it requires
rewriting the training loop and would alter numerics, so it belongs in its own
declared variant rather than in this comparison.

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
  --out out/eesm/equal_tuning_YYYYMMDD --workers 6
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
