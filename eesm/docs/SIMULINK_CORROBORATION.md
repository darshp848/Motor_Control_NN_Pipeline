# Simulink corroboration setup

Simulink is **corroboration of an already-exported scheduler LUT**. It is not
independent electromagnetic truth and cannot close EESM-005 or EESM-006.

## What is in this setup

| Path | Role |
|---|---|
| `eesm/src/export/simulink_export.py` | Fail-closed LUT export contract |
| `eesm/configs/simulink_scenarios.json` | Frozen command timelines |
| `eesm/matlab/import_eesm_lut.m` | Hash-checking MATLAB importer |
| `eesm/matlab/init_eesm_corroboration.m` | Workspace parameters |
| `eesm/matlab/build_eesm_corroboration_model.m` | Builds `eesm_corroboration.slx` |
| `eesm/matlab/run_eesm_scenarios.m` | Runs the frozen scenarios |
| `out/eesm/simulink_export_20260813/` | Exported LUT + metadata |

Libraries: built-in Simulink only (`.satk/reuse-libraries.json` has
`confirmedNone: true`). No custom library, no Motor Control Blockset
dependency for the first model.

## Plant meaning

The plant is a first-order current tracker plus a **declared linear** flux
model and the identity torque formula. It exists so the LUT, supervisor
mask, and scenario runner can be exercised. It does not replace FEMM.

## How to run

From the pipeline repo, after a LUT export exists:

```matlab
cd eesm/matlab
init_eesm_corroboration
build_eesm_corroboration_model
run_eesm_scenarios
```

Or from the OS:

```text
matlab -batch "addpath('eesm/matlab'); run_eesm_scenarios(pwd)"
```

## Supervisor and extrapolation

Lookup tables clip outside the frozen 8×8 `(rpm, T)` grid. A command such as
80 N·m at 9000 rpm therefore becomes the table-edge 31.83 N·m cell
(`saturated_to_boundary`), not a hard reject. A later supervisor can add an
explicit out-of-table mask if that behavior is required.

## Current export

The first LUT is the Phase 0 promoted candidate
`latin_hypercube|256|rbf_or_gp` scheduled on the 64 frozen `(rpm, T)`
commands. Those schedules are **offline map optimizations**. They are not a
prospective FEM audit.
