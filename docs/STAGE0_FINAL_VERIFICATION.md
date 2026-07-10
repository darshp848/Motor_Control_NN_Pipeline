# Stage 0 final verification — IPM offline freeze

**Conclusion: offline-frozen and audit-ready** (not FEM-audited).

| Field | Value |
|-------|--------|
| **Verification time (UTC)** | 2026-07-10T08:05:27Z (`out/run_manifest.json` `created_utc`) |
| **Branch** | `stage0/repair-freeze-ipm-pipeline` |
| **Commit at verification** | use `git rev-parse HEAD` on this branch after merge |
| **Python** | 3.11.9 (project `.venv`) |
| **Status claim** | **offline-frozen and audit-ready** |
| **Not claimed** | fully FEM-audited; deployment-ready FOC tables |

## Commands run

```pwsh
.\.venv\Scripts\python -m pytest tests -q
.\.venv\Scripts\python run_offline_pipeline.py --config configs/ipm_experiment_manifest.json
```

> Use the **project venv**. Bare system Python without `scikit-learn` / `torch` trains only classical models and is **not** the official Stage 0 reference.

## Pytest result

```text
20 passed
```

## Full offline pipeline result

```text
stages = train, compare, promote, mtpa, audit
exit code = 0
```

Official proof artifact: `out/run_manifest.json`.

### Environment recorded in run manifest

| Item | Recorded |
|------|----------|
| Python | 3.11.9 |
| numpy / pandas / scipy | 2.4.6 / 3.0.3 / 1.17.1 |
| sklearn / torch / matplotlib | 1.9.0 / 2.11.0+cu128 / 3.11.0 |
| Seeds | split=0, torch=0, off_grid=7, lut_audit=11 |
| File hashes | train CSV, off-grid CSV, motor params, metrics, ranking, LUT, audit commands, inference module + artifact |
| Config | full `configs/ipm_experiment_manifest.json` embedded |

## Model promotion

| Item | Value |
|------|--------|
| Manifest policy | `inference_selection = off_grid_in_domain` |
| **Selected inference model** | **`mlp_small`** |
| Artifact | `out/models/mlp_small.pt` |
| Deployed API | `inference_flux_map.py` → `predict(Id, Iq)` |

### Off-grid domain labels (historical 20-point set)

| Label | Count |
|-------|------:|
| `in_domain_interpolation` | 10 |
| `boundary` | 0 |
| `extrapolation` | 10 |

Interpolation and extrapolation metrics are reported **separately** in:

- `out/validation/off_grid_ranking.json`
- `out/validation/off_grid_by_domain.json`
- console leaderboards from `compare_off_grid_predictions.py`

### Winners

| Ranking | Winner | Notes |
|---------|--------|--------|
| **In-domain off-grid (primary)** | **`mlp_small`** | RMSE mean ≈ 3.37e-4 (n=10) — **promotion source** |
| **Mixed all-points (historical)** | **`random_forest`** | RMSE mean ≈ 1.22e-2 (n=20) |
| **Extrapolation-only (secondary)** | **`random_forest`** | RMSE mean ≈ 1.71e-2 (n=10) |
| In-grid test (reference) | `gaussian_process` | Not used for promotion under current policy |

### Extrapolation warning

The frozen historical off-grid CSV used `ID_RANGE=(-300, 300)` while training Id is `[-300, 0]`. Half of the points are **Id > 0 extrapolation**. Mixed off-grid RMSE is **not** pure in-domain generalization. Primary ranking is `off_grid_in_domain_rmse_mean`.

## MTPA / FW LUT

| Item | Value |
|------|--------|
| File | `out/mtpa/reference_lookup.csv` |
| Total rows | 3000 |
| Params | `out/mtpa/motor_params_used.json` (`flux_scale` ≈ 11.861) |

### Status counts

| Status | Count |
|--------|------:|
| `mtpa` | 700 |
| `fw` | 12 |
| `fw_search_failed` | 132 |
| `infeasible` | 2156 |

High `infeasible` share is a documented machine/limit envelope effect (see `docs/KNOWN_LIMITATIONS.md`), not a pipeline crash.

## LUT audit (surrogate-side)

| Item | Value |
|------|--------|
| Commands | `out/audit/lut_audit_commands.csv` — **14** rows (seed 11) |
| Surrogate check | `out/audit/lut_audit_surrogate.csv` |
| Report | `out/audit/lut_audit_report.json` (`status: ok`) |
| FEM join | `out/audit/lut_audit_fem_join.json` — **`pending_fem`** |
| FEM results CSV | **not present** (optional) |

Manual FEM path: [`docs/AEDT_LUT_AUDIT_RUNBOOK.md`](AEDT_LUT_AUDIT_RUNBOOK.md).

## Required outputs verified

| Path | Present after full run |
|------|------------------------|
| `out/run_manifest.json` | yes |
| `out/validation/off_grid_ranking.json` | yes |
| `out/validation/off_grid_by_domain.json` | yes |
| `out/validation/off_grid_predictions.csv` | yes |
| `out/mtpa/reference_lookup.csv` | yes |
| `out/mtpa/motor_params_used.json` | yes |
| `out/audit/lut_audit_commands.csv` | yes |
| `out/audit/lut_audit_surrogate.csv` | yes |
| `out/audit/lut_audit_report.json` | yes |
| `out/audit/lut_audit_fem_join.json` | yes (`pending_fem`) |

## Internal consistency checks

- Promotion policy matches manifest: `off_grid_in_domain` → `mlp_small`.
- `inference_flux_map.py` loads `out/models/mlp_small.pt`.
- MTPA uses that inference module; `motor_params_used.json` records inference path + params hash.
- Audit commands are drawn from the same `reference_lookup.csv` (seed 11).
- Run manifest records stages, seeds, package versions, and file hashes for inputs/outputs.

## Remaining known limitations

See [`docs/KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md). Highlights:

1. Coarse AEDT Student mesh (proof-of-concept FEM, not design signoff).
2. Training current box much wider than control currents (~6 A peak).
3. Training Id ≤ 0 only; positive Id is extrapolation.
4. Historical mixed off-grid set contaminates “generalization” if not stratified.
5. LUT is surrogate-selected until FEM audit is run.
6. Many LUT rows infeasible at high speed/torque on this envelope.
7. Large `flux_scale` absorbs 2D depth/turn conventions.
8. No lab measurement validation yet.

## Conclusion

**Stage 0 IPM pipeline is offline-frozen and audit-ready.**

It is a trusted, rerunnable template (train → domain-aware off-grid re-rank → promote → MTPA/FW → audit command list) with locked units, seeds, and manifests.

It is **not** FEM-audited and **not** flash-ready FOC until:

1. `out/audit/lut_audit_fem_results.csv` exists from a manual AEDT run, and  
2. `compare_lut_audit.py` produces a non-pending join report.

Next research track: Stage 1 synthetic EESM harness under `eesm/` (no real Maxwell until synthetic gates pass).
