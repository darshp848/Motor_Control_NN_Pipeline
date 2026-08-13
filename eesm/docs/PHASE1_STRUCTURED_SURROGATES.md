# Phase 1 — physics-structured surrogates

**Status:** families registered. v1 manifest is unchanged.
**Manifest:** `eesm/configs/eesm_experiment_manifest_v2.json`
**Gates:** identical to the Phase 0 freeze. Do not retune.

## Families

- `energy_gradient_net` — W′(id, iq, If) MLP; `λd, λq = (2/3) ∂W′/∂(id, iq)`
  per `eesm/docs/DQ_CONVENTIONS.md`.
- `pwa` — 3-D Delaunay + affine least squares per simplex (outside hull:
  nearest training vertex).

Phase 0 families stay in the v2 matrix so the comparison is
structured vs unstructured at the same budgets.

## Run

```text
python eesm/run_equal_budget_study.py `
  --config eesm/configs/eesm_experiment_manifest_v2.json `
  --out out/eesm/equal_budget_femm_v2_20260813 `
  --truth-csv out/eesm/femm_equal_budget_20260813/femm_results.csv
```
