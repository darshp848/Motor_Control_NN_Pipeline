# Motor Control NN Pipeline

Public pipeline for building a **flux-map surrogate** for an IPM motor and turning it into an **MTPA / field-weakening lookup table**.

```
AEDT FEM (dq flux map)
    → train classical + NN surrogates
    → off-grid FEM re-rank
    → motor parameter / flux_scale
    → MTPA + FW reference LUT
```

Personal write-ups, PDFs, notebooks, and the Obsidian vault live next door in:

`../Motor_Control_Learning_Research/`

## Layout

| Path | Purpose |
|------|---------|
| `data/` | Canonical inputs: FEM flux map, off-grid truth, motor params |
| `out/` | Pipeline outputs: models, metrics, validation, MTPA LUT |
| `aedt_mcp/` | Optional Ansys AEDT MCP tooling + FEM job helpers |
| `*.py` | End-to-end Python stages (see below) |
| `.venv/` | Local Python environment (not required to read results) |

## Quick start (post-FEM)

From this directory, with the venv activated:

```pwsh
# 1) Train and compare surrogates
.\.venv\Scripts\python train_flux_map_comparison.py --csv data/flux_map_fem.csv --out out

# 2) Re-rank models on off-grid FEM truth
.\.venv\Scripts\python compare_off_grid_predictions.py --truth data/off_grid_fem_results.csv --out out

# 3) Build MTPA / field-weakening LUT (uses data/motor_params.json if present)
.\.venv\Scripts\python mtpa_field_weakening.py --out out/mtpa
```

Inference API after training:

```python
from inference_flux_map import predict, predict_batch

phi_d, phi_q = predict(Id=-50.0, Iq=100.0)
```

## Pipeline stages

| Stage | Script | Input | Output |
|-------|--------|-------|--------|
| Train surrogates | `train_flux_map_comparison.py` | `data/flux_map_fem.csv` | `out/models/`, `out/logs/`, `inference_flux_map.py` |
| Off-grid FEM (AEDT) | `validate_off_grid_fem.py` | open AEDT project | `aedt_mcp/tmp/...` → copy to `data/off_grid_fem_results.csv` |
| Off-grid re-rank | `compare_off_grid_predictions.py` | `data/off_grid_fem_results.csv` | `out/validation/` |
| Motor params (AEDT) | `pull_motor_params.py` | open AEDT project | `aedt_mcp/out/motor_params.json` → `data/motor_params.json` |
| MTPA / FW LUT | `mtpa_field_weakening.py` | inference + params | `out/mtpa/` |

## Data files

- `data/flux_map_fem.csv` — columns `Id,Iq,Phi_d,Phi_q` (full training grid)
- `data/off_grid_fem_results.csv` — held-out FEM points for generalization ranking
- `data/motor_params.json` — poles, `rs`, rated torque/current, `flux_scale`, etc.

## Environment

Python 3.11 recommended. Example install into a venv:

```pwsh
python -m venv .venv
.\.venv\Scripts\python -m pip install -U pip
.\.venv\Scripts\python -m pip install -r requirements.txt
```

AEDT Student is only required to **regenerate** FEM data or motor params. All surrogate training, comparison, and LUT generation run offline from CSVs in `data/`.

## Notes

- Results under `out/` are from a completed run (Student-edition mesh; proof-of-concept fidelity).
- Deployed inference model is typically `out/models/random_forest.pkl` (off-grid winner), not the pure in-grid GP winner.
- For learning notes, literature PDFs, and the Obsidian vault, see `Motor_Control_Learning_Research`.
