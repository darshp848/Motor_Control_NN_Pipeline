# Phase 2 — Paper-strengthening experiments

This is a new predeclared study. It does not revise Phase 0 identities,
thresholds, promotion, or result bundles. Phase 0 remains the frozen
single-realization comparison reported in the 2026-08-13 manuscript.

## Why this exists

The Phase 0 ledger correctly records EESM-002 as `inconclusive`: random and
Latin-hypercube designs were drawn once, and stochastic learners used one
model seed. The selection-set boundary threshold was untestable. Copper-loss
regret was 0 W by construction. There is no frozen `(rpm, T)` command set
and no map-wide independent 360-degree torque audit.

## What is frozen here

1. The Phase 0 256-point `selection` set and 256-point `scheduler_audit` set
   stay sealed against training. New training identities must not overlap
   either reserved role.
2. Design replicate `0` of every strategy/budget cell is the original Phase 0
   design seed. Replicates `1..5` are additional independent random and
   Latin-hypercube draws. Tensor grids are deterministic and are not
   replicated.
3. Model seed `0` is the original seed `1701`. Seeds `1..4` are derived and
   used only for `compact_mlp` and `tree_ensemble`.
4. All new comparisons evaluate on the identical Phase 0 selection set.
5. Controller-calibrated thresholds below are declared for Phase 2 scoring.
   They are not used to re-rank or rewrite Phase 0.

## Controller-calibrated Phase 2 thresholds

These are engineering declarations, not FEM-repeatability measurements.
A repeatability floor is still unmeasured.

| Gate | Quantity | Value | Basis |
|---|---|---|---|
| `data_qa` | failed-row fraction | 0 | unchanged |
| `torque` | identity-torque RMSE | 1.5915 N·m | 5% of rated 31.83 N·m |
| `voltage` | voltage RMSE | 4.618802153517006 V | 2% of 400/√3 V peak-phase |
| regional flux | max(λd, λq) RMSE | 0.01 Wb | declared engineering floor |
| `feasibility` | label error rate | 0.02 | unchanged |

The Phase 0 interpolant-derived thresholds remain in
`eesm_experiment_manifest.json` and are reported alongside Phase 2 scores
for comparability only.

## Sequenced work

1. **Seed replication (offline).** Refit MLP and random forest on the nine
   frozen Phase 0 designs at five model seeds. No new FEM.
2. **Design-replicate identities.** Freeze five new random and five new LHS
   designs per budget. Solve only the unique currents that are not already
   in the 1759-row campaign.
3. **Independent boundary set.** Freeze face-centered currents that the
   region rule labels `boundary`, disjoint from selection and audit.
4. **360-degree WST set.** Freeze 40 currents already present in the 90-degree
   campaign and re-solve them on the full machine. Do not start this campaign
   until the 90-degree design-replicate campaign is either running or complete.
5. **Scheduler commands.** Freeze 64 `(rpm, T)` commands. Re-optimize each
   existing candidate map, then FEM-evaluate the selected currents. Do not
   start that FEM campaign until the command freeze and offline schedules
   exist.

## Prohibited actions

- Do not overwrite `out/eesm/phase0_close_20260813/`,
  `out/eesm/femm_equal_budget_20260813/`, or Task 9.
- Do not change frozen Phase 0 thresholds.
- Do not train on `selection` or `scheduler_audit`.
- Do not treat mock FEMM output as physics evidence.
- Do not promote a Phase 2 winner from untestable empty-region gates.
