# Threshold-freeze method

**Status:** method locked. Numbers copied into the manifest on
2026-08-13 (`gates.status = frozen`). Do not retune them after seeing
family fits.
**Date:** 2026-08-13
**Does not:** edit `eesm_experiment_manifest.json`, fit a competing family,
open `scheduler_audit`, or examine the 36-cell comparison.

## Why a method is required first

`validation.gates.evaluate_gates` is lower-is-better: a candidate passes a
gate iff `gate_values[g] <= threshold[g]`. The eight keys are produced by
`validation.controller_metrics.evaluate_controller_metrics`:

| Gate | `gate_values` meaning |
|---|---|
| `data_qa` | fraction of eval rows with `data_qa_passed == False` |
| `interior` | max(RMSE λd, RMSE λq) on that region (Wb) |
| `boundary` | same |
| `saturation` | same |
| `field_weakening` | same |
| `torque` | RMSE of identity torque `1.5 p (λd iq − λq id)` (N·m) |
| `voltage` | max over declared speeds of \|v\| RMSE (V_phase_peak) |
| `feasibility` | feasibility-label error rate |

The result-bundle schema requires **all eight** numbers together. Task 9
forbids setting region/torque/voltage/feasibility by staring at preferred
surrogates, and forbids using `scheduler_audit` for this decision.
`reference` is the role named for threshold methodology; the equal-budget
freeze has no `reference` rows, and the 256-point selection set has
**zero** `boundary` rows, so selection cannot host every regional gate.

## Roles

- **Allowed to set numbers:** campaign QA rows; `train` rows; the three
  frozen 64-point **training designs** (`tensor_grid_64`, `random_64`,
  `latin_hypercube_64`).
- **Forbidden:** `selection` (later comparison), `scheduler_audit`
  (sealed until after promotion), any of
  `{physics_polynomial, rbf_or_gp, tree_ensemble, compact_mlp}`.

## Threshold instrument (not a competitor)

Inverse-distance weighting, power 2, on currents normalized by the
manifest map box `id ∈ [−120, 0]`, `iq ∈ [0, 120]`, `If ∈ [0, 15]`.
Exact neighbour (distance 0) copies that neighbour. This interpolant is
**not** a surrogate family in the manifest.

For each 64-point design `D`:

1. Fit IDW on the design points that have FEMM truth (origin is excluded
   from the 90° campaign, so `tensor_grid_64` contributes 63).
2. Predict `λd, λq` on **holdout** = `train` points whose `point_id` is
   not in `D`.
3. Compute `gate_values` on that holdout with
   `speeds_rpm = [3000, 9000]`.
4. Feasibility label (one bit per row): at **3000 rpm**,
   `|v|_peak <= Vdc / √3` using the identity voltage law already in
   `stator_voltage_eesm`. Current-box membership is already true for
   every campaign row.

`data_qa_passed` is `True` iff the truth row is finite, `converged`, and
schema-valid. On the finished 1759-point campaign that rate is 0.

## Combining three 64-point instruments

```text
raw[g]       = max(instrument_D[g] for D in {tensor, random, LHS}_64)
threshold[g] = max(raw[g], floor[g])
```

Floors (solver / convention slack, predeclared, not tuned after seeing
family fits):

| Gate | Floor |
|---|---|
| `data_qa` | 0 |
| regional flux | 1e-3 Wb |
| `torque` | 0.5 N·m (scheduler `torque_tolerance_nm`) |
| `voltage` | 2.0 V |
| `feasibility` | 0.02 |

Using the **worst** of the three 64-point IDWs keeps a competent
64-budget map inside the gates. Tighter numbers from the 1247-point
union would kill the 64-budget cells and answer a different question.

## Empty-region rule

If a regional gate has `n = 0` on the evaluation set, `gate_values[g]`
is `0.0` (vacuous pass). Selection has no `boundary` rows, so the
boundary gate will not kill the 36-cell study. The boundary **number**
is still frozen from the train holdout, which does contain boundary
rows, and applies whenever a future eval set has boundary points.
A `NaN` from a missing computation still fails (`metric_unavailable`).

## Executable pin

```text
python -m eesm.run_threshold_proposal
```

writes `out/eesm/threshold_proposal_20260813.json` and does **not**
touch the manifest. Tests:
`eesm/tests/test_threshold_method.py`.

## Manifest freeze (2026-08-13)

The proposal numbers are now the live `gates.thresholds` in
`eesm/configs/eesm_experiment_manifest.json`. Fitting may start.
Do not edit these eight values to admit a preferred family.
