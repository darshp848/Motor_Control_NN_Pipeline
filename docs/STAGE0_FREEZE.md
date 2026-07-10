# Stage 0 freeze — IPM pipeline template

**Branch:** `stage0/repair-freeze-ipm-pipeline`  
**Purpose:** Trusted, rerunnable IPM workflow before EESM 3D adaptation.

## One-command offline path

```pwsh
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python run_offline_pipeline.py --config configs/ipm_experiment_manifest.json
```

Skip long retrain (reuse `out/models`):

```pwsh
.\.venv\Scripts\python run_offline_pipeline.py --skip-train
```

## Fixed artifacts

| Item | Location |
|------|----------|
| Experiment manifest | `configs/ipm_experiment_manifest.json` |
| Clean motor params | `data/motor_params_clean.json` |
| Training map | `data/flux_map_fem.csv` |
| Off-grid truth | `data/off_grid_fem_results.csv` |
| Domain-labeled off-grid | `data/off_grid_fem_results_labeled.csv` (written by compare) |
| Run metadata | `out/run_manifest.json` |
| Stratified ranking | `out/validation/off_grid_ranking.json` |
| LUT audit commands | `out/audit/lut_audit_commands.csv` |
| Shared physics/domain | `pipeline/` |
| Units | `docs/UNITS_AND_CONVENTIONS.md` |
| Limitations | `docs/KNOWN_LIMITATIONS.md` |

## Seeds (frozen defaults)

| Seed | Value | Use |
|------|------:|-----|
| train/val/test split | 0 | `train_flux_map_comparison.py --seed` |
| torch | 0 | model init |
| off-grid points | 7 | AEDT off-grid generator |
| LUT audit selection | 11 | `audit_lut_scheduler.py` |

## Inference promotion policy

`inference_selection: off_grid_in_domain`  
→ after compare, rewrite `inference_flux_map.py` to the best **in-domain** off-grid model (not manual RF edit).

On the frozen 2026-07-09 models + historical off-grid CSV, in-domain ranking prefers strong interpolators (e.g. `mlp_small` / GP), while **mixed** ranking (including Id>0) preferred `random_forest`. Always re-run MTPA after promote so `out/mtpa` matches the deployed artifact.

Other policy values: `off_grid_all`, `in_grid` (see `run_offline_pipeline.select_inference_model`).

## Optional AEDT stages

1. Full map: `aedt_mcp/.../gui_full_magnetostatic_export.py`
2. In-domain off-grid: `validate_off_grid_fem.py` with `POINT_SET_MODE = "interpolation"`
3. Explicit extrap set: same script with `POINT_SET_MODE = "extrapolation"`
4. LUT FEM audit: `validate_lut_audit_fem.py` then `compare_lut_audit.py`

## Exit gate checklist

- [x] Domain-stratified off-grid metrics
- [x] LUT prospective audit command list (surrogate-side)
- [x] Machine-readable units / params
- [x] Seeded, orchestrated offline rerun
- [x] Regression tests for physics, domain, seeds, schema
- [ ] Optional: FEM audit results filled under `out/audit/lut_audit_fem_results.csv`

## Pre-freeze reference numbers (2026-07-09)

See `out/pipeline_results_summary.json`: in-grid GP, mixed off-grid RF, flux_scale ≈ 11.861, LUT 3000 rows.
