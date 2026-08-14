# Energy-gradient determinism (Paper 2)

**Status:** required for any Paper 2 number that uses `energy_gradient_net`.
**Does not:** retune Phase 0/1 gates, rewrite v2.1, or launch FEMM.

## Why

`torch.manual_seed` alone is not a reproducible energy-net fit. The potential
is trained with Adam through `autograd.grad` for 3000 epochs. Thread count
and fused/foreach Adam kernels can change the path. A reviewer who reruns
the headline family can get a different torque RMSE.

## Rule

Fits of `energy_gradient_net` and `compact_mlp` must call
`surrogates.torch_determinism.configure_torch_determinism`:

- device is CPU
- `torch.use_deterministic_algorithms(True)`
- one intra-op thread
- Adam `foreach=False`, `fused=False`

The executable contract is `eesm/configs/eesm_experiment_manifest_v2_2.json`.
v2.1 is unchanged so the Phase 1 science hash stays valid.

Paper 2 ranks energy-net cells on the **median** torque RMSE over 8 model
seeds and reports min / IQR / max. Seed 0 is the original `1701`.

## How to rerun

```text
.\.venv\Scripts\python.exe -m eesm.run_energy_seed_study `
  --manifest eesm/configs/eesm_experiment_manifest_v2_2.json `
  --campaign out/eesm/femm_equal_budget_20260813/femm_results.csv `
  --out out/eesm/energy_seed_study_20260813 `
  --seeds 8
```
