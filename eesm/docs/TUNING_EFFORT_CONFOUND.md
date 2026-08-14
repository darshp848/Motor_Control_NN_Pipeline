# Family ranking is confounded by unequal tuning effort

**Status:** sensitivity analysis, 2026-08-14. Run on the exact frozen training
designs and the frozen 256-point selection set, using the repository's own
surrogate classes. **Changes nothing in any frozen experiment.** The Phase 0
bundle, its thresholds, and its promotion stand exactly as recorded.
**Artifacts:** `gp_probe.json`, `paired_probe.json`, `ann_sweep.json` (scripts
`gp_probe.py`, `paired_probe.py`, `ann_sweep.py`, `ann_checks.py`).

## Summary

Phase 0 compared four surrogate families at equal *data* budgets. It did not
equalise *tuning* budgets. Each family received whatever configuration happened
to be in the manifest, and those configurations differ enormously in how close
they are to that family's achievable performance. Two are demonstrably far off:

| Family | What Phase 0 used | Headroom left on the table |
|---|---|---|
| `rbf_or_gp` | `optimizer=None` — kernel hyperparameters never fitted | up to **67%** lower torque RMSE |
| `compact_mlp` | 300 epochs, no early stopping, one seed | up to **4.3x** lower torque RMSE |

Because the two corrections push in opposite directions, no ranking between
them was identified by the frozen study. This does **not** affect the paper's
gate-non-discrimination finding, which only gets stronger: every corrected
model clears the 9.655 N·m torque gate by a wider margin than before.

## 1. The GP never fitted its kernel

`eesm/src/surrogates/kernel.py` passes `optimizer=None`, `n_restarts_optimizer=0`.
scikit-learn's default is `fmin_l_bfgs_b`; with `None` the fitted `kernel_` is
returned byte-identical to the initial kernel. Verified directly: a control fit
left `1**2 * RBF(length_scale=1) + WhiteKernel(1e-06)` unchanged while the
default optimiser gained **13.7 nats** of log marginal likelihood. The Phase 0
"GP" is therefore a fixed-kernel RBF interpolant with a 1e-6 nugget.

Torque RMSE (N·m) on the frozen selection set. Variant A reproduces the Phase 0
bundle to four decimals, so the harness is faithful:

| cell | A frozen | B isotropic + LML | C ARD + LML |
|---|---|---|---|
| tensor_grid\|64 | 1.1236 | 0.6949 | 0.6986 |
| tensor_grid\|128 | 0.8509 | 0.8688 | **1.3209** |
| tensor_grid\|256 | 0.4649 | 0.4159 | **0.6682** |
| random\|64 | 1.6279 | 0.6868 | 0.6933 |
| random\|128 | 0.8158 | 0.5580 | 0.6012 |
| random\|256 | 0.4144 | 0.2271 | **0.2063** |
| latin_hypercube\|64 | 2.3163 | 0.7680 | 0.7861 |
| latin_hypercube\|128 | 0.6254 | 0.6644 | 0.6797 |
| latin_hypercube\|256 | 0.3669 | 0.2279 | 0.2280 |

Isotropic + marginal-likelihood optimisation improves **7 of 9** cells, by
38–67% at budget 64 — the scarce-data regime where the literature predicts
hyperparameter choice matters most. **ARD is not a free win**: it is 44% and 55%
*worse* on two tensor-grid cells, the documented failure mode where ARD overfits
the model-selection criterion. Isotropic + L-BFGS is the safe default; ARD needs
its own justification.

## 2. The MLP was undertrained

Epoch sweep, median of three seeds, same frozen designs:

| cell | 300 (Phase 0) | 600 | 1200 | 2400 | 4800 |
|---|---|---|---|---|---|
| tensor_grid\|64 | 0.5581 | 0.3118 | **0.2338** | 0.3013 | 0.2370 |
| random\|256 | 0.4722 | 0.2132 | 0.1929 | **0.1095** | 0.2890 |
| latin_hypercube\|256 | 0.4429 | 0.2085 | 0.1373 | 0.1272 | **0.1158** |

The Phase 0 setting is the worst column everywhere. The curve is **not
monotone** — `random|256` improves to 0.1095 at 2400 epochs then degrades to
0.2890 at 4800 — so a fixed epoch count with no early stopping and no
validation-based selection lands on an arbitrary point of a curve that varies
by more than 4x. That is a tuning artefact, not an architecture property.

## 3. What this does to the comparison

Paired comparison, LML-optimised GP against the seed-median compact MLP over
eight seeds, both at the Phase 0 epoch count:

| budget | best optimised GP | best seed-median MLP (300 ep) | winner |
|---|---|---|---|
| 64 | random 0.6868 | tensor_grid 0.5322 | MLP |
| 128 | random 0.5580 | random 0.4162 | MLP |
| 256 | random **0.2271** | tensor_grid 0.3914 | GP |

But once the MLP is also trained to a sensible budget, its 256-point results
(0.1095–0.1373) beat the optimised GP (0.2271) by roughly a factor of two, and
the GP's apparent win at 256 disappears. **The ranking tracks tuning effort, not
architecture.**

The honest statement is therefore not "no family dominates" but: *with unequal
per-family tuning protocols, the family comparison is not identified.* The
sampling-strategy comparison inherits the same problem, since the strategy that
looks best depends on which family is best at that budget.

## 4. Architecture sweep, and two self-inflicted errors worth recording

Seven architectures, three seeds each, identical preprocessing via the
repository's `FluxSurrogate` base, 600 epochs except where noted. Median torque
RMSE across the nine cells:

| architecture | median | best cell |
|---|---|---|
| `mlp_300` (Phase 0) | 0.5316 | 0.4269 |
| `deep_ensemble` (5 x compact MLP, averaged) | **0.2476** | 0.1710 |
| `mlp_600` | 0.2959 | 0.1964 |
| `residual_mlp` | 0.3497 | **0.1368** |
| `siren` (sine activations) | 2.5238 | 0.8674 |
| `fourier_mlp` (RFF, scale 0.6) | 20.1660 | 15.0961 |
| `reciprocity_penalised_mlp` | 0.2959 | 0.1964 |

Two of those rows were **my errors, not findings**, and both illustrate the
paper's own thesis:

- **Fourier features did not fail.** At the bandwidth I first chose the model
  was worse than predicting zero. Sweeping it at `latin_hypercube|256`:
  scale 0.6 → 15.10, 0.3 → 5.20, 0.1 → 0.31, 0.03 → **0.1454**, 0.01 → 0.1892.
  Correctly scaled, a Fourier-feature MLP is among the best models tested. One
  badly chosen hyperparameter made a good architecture look 100x worse.
- **The reciprocity penalty was inert.** At weight 1 the penalty term is
  3.2e-9 against a data term of 1.5e-4 — a ratio of 2.1e-5. It contributed
  nothing, which is why those results are identical to `mlp_600` to four
  decimals. A comparable weight is ~4.8e4. The soft-constraint-versus-hard-
  constraint question is **untested**, not answered.

Both are the same class of error the frozen study made, produced in an
afternoon. That is the argument for a pre-registered tuning protocol, made
against ourselves.

## 5. What a defensible comparison requires

Equal *data* budget is not enough. A family comparison needs an equal **tuning**
budget, pre-registered:

1. A fixed number of hyperparameter evaluations per family (identical across
   families), selected on an **inner** split of the training data only.
2. Never on the `selection` set — that would leak the comparison set into model
   choice.
3. Early stopping on the inner split for the iterative learners, so epoch count
   stops being a free parameter chosen by hand.
4. Seed replication for every stochastic family, ranked on medians with spread
   reported.
5. The tuning search space declared per family before any fit.

Until that exists, report family results as *configuration-conditional* and do
not rank families.

## 6. Recommended dispositions

- **Phase 0 stands.** Do not retrofit. Report §1–§3 as a stated limitation plus
  this sensitivity analysis.
- **Paper 1**: the gate-non-discrimination finding is unaffected and
  strengthened. Weaken every family- and strategy-ranking claim to
  configuration-conditional.
- **Paper 2 / any future frozen phase**: adopt §5. Set the GP to
  `optimizer="fmin_l_bfgs_b"`, `n_restarts_optimizer>=5`, isotropic RBF, with
  ARD as a separately declared variant. Give iterative learners early stopping
  rather than a fixed epoch count.
- Promising architectures worth carrying forward under a proper protocol:
  **deep ensemble** (best median, and it supplies the predictive uncertainty the
  GP has and the plain MLP lacks — relevant to the Phase 3 acquisition work),
  **residual MLP** (best single cell), and **correctly scaled Fourier features**.
- Still untested and worth doing: the reciprocity-penalised MLP at a meaningful
  weight, as the soft-constraint control against the energy net's hard
  constraint.
