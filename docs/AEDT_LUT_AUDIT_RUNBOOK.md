# AEDT LUT audit runbook (manual)

**Purpose:** Close the optional FEM half of the Stage 0 LUT audit.  
**Status:** Offline stages already freeze `out/audit/lut_audit_commands.csv`. This runbook is for when you want FEM torque closure.  
**Do not** launch AEDT from automation or MCP for this step unless you intentionally open the GUI.

## Prerequisites

1. Offline pipeline already green:

   ```pwsh
   .\.venv\Scripts\python -m pytest tests -q
   .\.venv\Scripts\python run_offline_pipeline.py --config configs/ipm_experiment_manifest.json
   ```

2. Confirm:

   - `out/audit/lut_audit_commands.csv` exists
   - `out/audit/lut_audit_fem_join.json` has `"status": "pending_fem"`
   - IPM project path in `validate_lut_audit_fem.py` matches your machine

3. AEDT Student/license available; project opens without script errors.

## Manual steps

### 1. Open the IPM project in AEDT

Default path expected by the script:

`aedt_mcp/tmp/aedt_projects/ipm_1_probe/ipm_1.aedt`

Design / setup (script defaults):

- Project: `ipm_1`
- Design: `Maxwell2DDesign4`
- Setup: `Setup_MagProbe`

### 2. Run the audit script from AEDT

In AEDT: **Automation → Run Script…** (or Tools → Run Script, depending on version).

Select:

```text
validate_lut_audit_fem.py
```

(repo root)

The script:

1. Reads `out/audit/lut_audit_commands.csv`
2. For each row with `needs_fem=true`, applies `(Id, Iq)`, analyzes, exports ABC flux, Parks to dq
3. Writes FEM results under the job dir (and/or a local CSV)

Typical outputs:

- `aedt_mcp/tmp/aedt_jobs/lut_scheduler_audit/lut_audit_fem_results.csv`
- `aedt_mcp/tmp/aedt_jobs/lut_scheduler_audit/lut_audit_fem.json`

### 3. Copy FEM results into the audit folder

```pwsh
Copy-Item `
  aedt_mcp\tmp\aedt_jobs\lut_scheduler_audit\lut_audit_fem_results.csv `
  out\audit\lut_audit_fem_results.csv
```

Required columns (minimum):

```text
Id, Iq, Phi_d, Phi_q, command_id
```

Fluxes must be **raw FEM** (same convention as `data/flux_map_fem.csv`).  
`compare_lut_audit.py` multiplies by `flux_scale` from the command row.

### 4. Join and report (offline)

```pwsh
.\.venv\Scripts\python compare_lut_audit.py `
  --commands out/audit/lut_audit_commands.csv `
  --fem out/audit/lut_audit_fem_results.csv `
  --out out/audit
```

Success criteria:

- `out/audit/lut_audit_fem_join.json` status is **not** `pending_fem`
- Per-command torque / voltage errors are recorded
- No silent row drops without a `missing_fem` status

## Command list (copy-paste)

```pwsh
# Offline only (already done for Stage 0 freeze)
.\.venv\Scripts\python audit_lut_scheduler.py --out out/audit
.\.venv\Scripts\python compare_lut_audit.py `
  --commands out/audit/lut_audit_commands.csv `
  --fem out/audit/lut_audit_fem_results.csv `
  --out out/audit

# After manual AEDT run of validate_lut_audit_fem.py:
Copy-Item aedt_mcp\tmp\aedt_jobs\lut_scheduler_audit\lut_audit_fem_results.csv `
  out\audit\lut_audit_fem_results.csv -Force
.\.venv\Scripts\python compare_lut_audit.py `
  --commands out/audit/lut_audit_commands.csv `
  --fem out/audit/lut_audit_fem_results.csv `
  --out out/audit
```

## What “done” means

| State | Meaning |
|-------|---------|
| `pending_fem` | Offline frozen; FEM not run (current Stage 0) |
| join complete | FEM-audited for the sampled LUT commands |
| flash-ready FOC | **Not claimed** even after FEM join |

Until FEM results exist, Stage 0 remains **offline-frozen and audit-ready**, not FEM-audited.
