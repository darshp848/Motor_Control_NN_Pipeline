# Motor Control NN Pipeline

Public pipeline for building a **flux-map surrogate** for an IPM motor and turning it into an **MTPA / field-weakening lookup table**.

**Stage 0 status: offline-frozen and audit-ready** (not FEM-closed / not deployment-ready).  
Branch `stage0/repair-freeze-ipm-pipeline` locks domain-aware validation, units, seeds, and a one-command offline path before EESM work. See [`docs/STAGE0_FREEZE.md`](docs/STAGE0_FREEZE.md).

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
| `docs/` | Units, known limitations, Stage 0 freeze protocol |
| `tests/` | Regression tests (physics, domain, seeds, schema) |
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
- See [`docs/UNITS_AND_CONVENTIONS.md`](docs/UNITS_AND_CONVENTIONS.md) and [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).

## Learning notes

For literature PDFs and the Obsidian vault, see `Motor_Control_Learning_Research`.
