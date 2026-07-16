# Motor Control NN Pipeline

Public pipeline for building a **flux-map surrogate** for an IPM motor and turning it into an **MTPA / field-weakening lookup table**.

**Stage 0 status: offline-frozen and audit-ready** (not FEM-closed / not deployment-ready).  
Branch `stage0/repair-freeze-ipm-pipeline` locks domain-aware validation, units, seeds, and a one-command offline path before EESM work. See [`docs/STAGE0_FREEZE.md`](docs/STAGE0_FREEZE.md) and the verification report [`docs/STAGE0_FINAL_VERIFICATION.md`](docs/STAGE0_FINAL_VERIFICATION.md).

**Stage 1 (EESM):** the foundry now covers frozen roles, equal-budget surrogate studies, controller-aware gates, deterministic promotion policy, constrained scheduling, a prospective LUT-audit boundary, and a verified Maxwell qualification adapter. The 2026-07-15 seven-point energized pilot passes the Task 8 qualification report and unblocks the Task 9 software/campaign start. Promotion remains blocked until the separate baseline-derived numerical thresholds are frozen. See [`docs/EESM_PIPELINE_ARCHITECTURE.md`](docs/EESM_PIPELINE_ARCHITECTURE.md).

**Task 9 offline status:** all **64/64** frozen Maxwell rows converged with complete raw evidence and no adaptive non-convergence warning; the maximum measured mesh was 1,826 elements. Canonical normalization completed, but `campaign_report.json` is intentionally `fail`: 59/64 rows exceed the frozen 1.1 N.m torque-closure limit, all 13 field-weakening rows fail it, and the maximum residual is 42.474642129016004 N.m. Direct AEDT diagnostics confirmed that `Torque_FEM` and `TorqueRotor.Torque` agree, so this is not an exporter readback error. No promoted surrogate, controller-ready LUT, released map, numerical-threshold update, or Task 10 result is claimed. Raw evidence remains local under `out/eesm/task9_baseline/raw/`; earlier non-converged attempts remain preserved under `out/eesm/task9_baseline/failed_runs/`.

**Corrective requalification status:** a write-once ten-point `r2` diagnostic
freeze is preserved under `out/eesm/task9_requalification_r2/`. Its preflight
blocks solves because the saved Task 8/9 model is not the frozen academic
machine: it has 77.0793 mm model depth, 144 stator series turns per phase,
20 field turns per pole, and a damper cage. A corrected `r3` project was later
configured and validated, but its first displaced co-energy solve exposed that
rotating an already clipped quarter sector invalidates its periodic topology.
A separate full-machine direct-geometry `r4` project passed independent
inventory and AEDT design validation with the frozen 120 mm depth, 36 turns per
phase, 80 field turns per pole, and no damper cage. Its first field-only solve
then stopped at the AEDT Student mesh-size limit. Both failures and their
project hashes are preserved. A smaller anti-periodic sector is a prospective
new revision, not an accepted FEM result; no Task 10 authorization is claimed.

```
AEDT FEM (dq flux map)
    → train classical + NN surrogates
    → off-grid FEM re-rank (interpolation vs extrapolation separated)
    → motor parameter / flux_scale
    → MTPA + FW reference LUT
    → prospective LUT audit command list
```

Personal write-ups, PDFs, notebooks, and the Obsidian vault live next door in:

`../Motor_Control_Learning_Research/`

## Layout

| Path | Purpose |
|------|---------|
| `data/` | Canonical inputs: FEM flux map, off-grid truth, clean motor params |
| `configs/` | Frozen experiment manifest (seeds, domains, paths) |
| `pipeline/` | Shared physics, domain labels, manifests, data QA |
| `out/` | Pipeline outputs: models, metrics, validation, MTPA LUT, audit |
| `docs/` | Units, known limitations, Stage 0 freeze + verification, AEDT LUT audit runbook |
| `tests/` | Regression tests (physics, domain, seeds, schema) |
| `eesm/` | Stage 1 EESM foundry contract, canonical experiment roles, baseline sampling designs, legacy synthetic harness, scheduler, and tests |
| `aedt_mcp/` | Optional Ansys AEDT MCP tooling + FEM job helpers |
| `*.py` | End-to-end Python stages (see below) |
| `.venv/` | Local Python environment (not required to read results) |

## Quick start (offline, Stage 0)

From this directory, with the venv activated:

```pwsh
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest tests -q

# Official offline reference (no skip flags): train → compare → promote → MTPA → audit prep
.\.venv\Scripts\python run_offline_pipeline.py --config configs/ipm_experiment_manifest.json

# Dev-only: reuse existing models (not the official freeze reference)
.\.venv\Scripts\python run_offline_pipeline.py --skip-train
```

### Stage-by-stage (same as orchestrator)

```pwsh
.\.venv\Scripts\python train_flux_map_comparison.py --csv data/flux_map_fem.csv --out out --seed 0
.\.venv\Scripts\python compare_off_grid_predictions.py --truth data/off_grid_fem_results.csv --out out
.\.venv\Scripts\python mtpa_field_weakening.py --params-json data/motor_params_clean.json --out out/mtpa
.\.venv\Scripts\python audit_lut_scheduler.py --out out/audit
```

Inference API after promotion:

```python
from inference_flux_map import predict, predict_batch

phi_d, phi_q = predict(Id=-50.0, Iq=100.0)
```

## Pipeline stages

| Stage | Script | Input | Output |
|-------|--------|-------|--------|
| Train surrogates | `train_flux_map_comparison.py` | `data/flux_map_fem.csv` | `out/models/`, `out/logs/` |
| Off-grid FEM (AEDT) | `validate_off_grid_fem.py` | open AEDT project | labeled truth CSV |
| Off-grid re-rank | `compare_off_grid_predictions.py` | `data/off_grid_fem_results.csv` | `out/validation/` (by domain) |
| Motor params (AEDT) | `pull_motor_params.py` | open AEDT project | raw → clean via manifest helpers |
| MTPA / FW LUT | `mtpa_field_weakening.py` | inference + clean params | `out/mtpa/` |
| LUT audit (offline) | `audit_lut_scheduler.py` | reference_lookup | `out/audit/` |
| LUT FEM audit (AEDT) | `validate_lut_audit_fem.py` | commands CSV | FEM fluxes for join |
| Orchestrator | `run_offline_pipeline.py` | manifest | all offline + `out/run_manifest.json` |

## Data files

- `data/flux_map_fem.csv` — columns `Id,Iq,Phi_d,Phi_q` (training grid; Id ≤ 0)
- `data/off_grid_fem_results.csv` — held-out FEM points (may include historical Id > 0)
- `data/motor_params_clean.json` — **preferred** poles, rs, flux_scale, units metadata
- `data/motor_params.json` — raw AEDT pull (provenance; noisy)
- `configs/ipm_experiment_manifest.json` — seeds, domains, inference policy

## Environment

Python **3.11** recommended:

```pwsh
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

AEDT Student is only required to **regenerate** FEM data, motor params, or FEM LUT audit. Offline stages run from CSVs in `data/`.

## Stage 0 notes

- **Label:** offline-frozen + audit-ready; FEM LUT audit (`lut_audit_fem_results.csv`) is still optional/pending.
- Domain labels: `in_domain_interpolation` / `boundary` / `extrapolation` — metrics reported **separately**.
- Inference model is **promoted** by policy `off_grid_in_domain` (no manual RF edit); full pipeline rebuilds MTPA after promote.
- Official offline proof: `out/run_manifest.json` with stages `train, compare, promote, mtpa, audit`.
- FEM LUT audit is optional: [`docs/AEDT_LUT_AUDIT_RUNBOOK.md`](docs/AEDT_LUT_AUDIT_RUNBOOK.md).
- See [`docs/UNITS_AND_CONVENTIONS.md`](docs/UNITS_AND_CONVENTIONS.md) and [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

## Stage 1 EESM foundry

The source of truth for domains, roles, budgets, gates, seeds, schemas, and paths is `eesm/configs/eesm_experiment_manifest.json`. Disjoint `train`, `selection`, `scheduler_audit`, and optional `reference` roles are frozen. Sequential sampling remains disabled.

```pwsh
.\.venv\Scripts\python -m pytest eesm/tests -q
.\.venv\Scripts\python eesm/run_synthetic_stage1.py
.\.venv\Scripts\python eesm/run_equal_budget_study.py
```

These runners do **not** launch AEDT. Generated artifacts land under `out/eesm/`. Task 8's seven-point qualification is complete. Task 9 collected all 64 frozen rows under the stricter adaptive-convergence contract, but its final physics report fails the frozen 1.1 N.m torque-closure gate with a 42.474642129016004 N.m maximum residual. Numerical thresholds therefore remain `baseline_required`; no controller-ready or Simulink-ready claim is made.

Safe offline inspection (does not launch AEDT):

```pwsh
Get-Content out/eesm/task9_baseline/campaign_freeze.json
Get-Content out/eesm/task9_baseline/raw/campaign_status.json
```

Task 9 normalization and reporting have run. Inspect `out/eesm/task9_baseline/campaign_report.json`; do not promote or begin Task 10 while its `campaign_status` is `fail`.

## Learning notes

For literature PDFs and the Obsidian vault, see `Motor_Control_Learning_Research`.
