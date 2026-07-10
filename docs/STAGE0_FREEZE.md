# Stage 0 freeze — IPM pipeline template

**Branch:** `stage0/repair-freeze-ipm-pipeline`  
**Purpose:** Trusted, rerunnable IPM workflow before EESM 3D adaptation.

## Status

| Label | Meaning |
|-------|---------|
| **offline-frozen and audit-ready** | **Current Stage 0 status** |
| fully FEM-audited and deployment-ready | **Not claimed** |

This is a clean IPM template for EESM work: domain-aware validation, locked units/seeds, one-command offline rerun, and a prospective LUT audit protocol. It is **not** a flash-ready FOC table and **not** FEM-closed until `out/audit/lut_audit_fem_results.csv` exists and `compare_lut_audit.py` joins cleanly.

Machine-readable twin: `configs/ipm_experiment_manifest.json` → `freeze_status`, `fem_lut_audit`.

## Official offline reference (no skip flags)

From the branch root:

```pwsh
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python run_offline_pipeline.py --config configs/ipm_experiment_manifest.json
```

The **official Stage 0 offline reference** is the `out/run_manifest.json` produced by that full command. It must list:

```text
stages: train, compare, promote, mtpa, audit
```

Dev-only faster path (reuses models; **not** the official reference):

```pwsh
.\.venv\Scripts\python run_offline_pipeline.py --skip-train
```

After promote, MTPA must run in the same full chain so `out/mtpa` matches `inference_flux_map.py`.

## Fixed artifacts

| Item | Location |
|------|----------|
| Experiment manifest | `configs/ipm_experiment_manifest.json` |
| Clean motor params | `data/motor_params_clean.json` |
| Training map | `data/flux_map_fem.csv` |
| Off-grid truth | `data/off_grid_fem_results.csv` |
| Domain-labeled off-grid | `data/off_grid_fem_results_labeled.csv` (written by compare) |
| **Official run metadata** | `out/run_manifest.json` |
| Stratified ranking | `out/validation/off_grid_ranking.json` |
| LUT audit commands | `out/audit/lut_audit_commands.csv` |
| Shared physics/domain | `pipeline/` |
| Units | `docs/UNITS_AND_CONVENTIONS.md` |
| Limitations | `docs/KNOWN_LIMITATIONS.md` |
| Final verification report | `docs/STAGE0_FINAL_VERIFICATION.md` |
| Manual FEM LUT audit runbook | `docs/AEDT_LUT_AUDIT_RUNBOOK.md` |

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

On historical off-grid CSV (mixed Id domain): in-domain ranking prefers strong interpolators (e.g. `mlp_small` / GP), while **mixed** ranking (including Id>0) preferred `random_forest`. Full offline run rebuilds MTPA after promote so the LUT matches the deployed artifact.

Other policy values: `off_grid_all`, `in_grid` (see `run_offline_pipeline.select_inference_model`).

## Optional AEDT stages (FEM-closed path)

Only after the offline chain is green:

1. Full map: `aedt_mcp/.../gui_full_magnetostatic_export.py` (already frozen CSV in `data/`)
2. In-domain off-grid: `validate_off_grid_fem.py` with `POINT_SET_MODE = "interpolation"`
3. Explicit extrap set: same script with `POINT_SET_MODE = "extrapolation"`
4. LUT FEM audit:
   - `validate_lut_audit_fem.py` in AEDT → FEM fluxes
   - copy to `out/audit/lut_audit_fem_results.csv`
   - `compare_lut_audit.py` → join / torque errors

## Exit gate checklist

- [x] Domain-stratified off-grid metrics
- [x] LUT prospective audit command list (surrogate-side)
- [x] Machine-readable units / params
- [x] Seeded, orchestrated offline path
- [x] Regression tests for physics, domain, seeds, schema
- [x] Full offline `train → compare → promote → mtpa → audit` reference run (`out/run_manifest.json`)
- [ ] FEM LUT audit results: `out/audit/lut_audit_fem_results.csv` + non-pending join

## Pre-Stage-0 historical numbers (2026-07-09)

See `out/pipeline_results_summary.json`: in-grid GP, mixed off-grid RF, flux_scale ≈ 11.861, LUT 3000 rows. Prefer the latest full-run `out/run_manifest.json` for the official offline reference.
