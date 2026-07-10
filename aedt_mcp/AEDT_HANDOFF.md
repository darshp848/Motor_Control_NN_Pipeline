# AEDT MCP Handoff

## Current State

The combined server is now operator-guided. It keeps the existing PyAEDT tool surface but blocks live AEDT operations from Codex by default. Unsafe calls return structured `user_action_required` responses.

Known environment facts are stored in:

```text
src/aedt_mcp/state/capabilities.json
```

Preferred workspace-local paths:

- `tmp/aedt_temp`
- `tmp/aedt_projects`
- `tmp/aedt_jobs`

## AEDT Status

- Target AEDT Student version: `2025.2SV`.
- AEDT can start far enough to log `GRPC server running on port: 50051`.
- AEDT was launched non-graphically on port `50052` and listened as PID `40544`.
- PyAEDT attach is confirmed unsafe for this install: it does not recognize the active gRPC listener and tries to launch a new AEDT session.
- The generated PyAEDT attach script now blocks that launch path intentionally.
- Raw ScriptEnv attach succeeded against port `50052` and returned `2025.2.0`.
- RMxprt `ipm_1` conversion to Maxwell succeeded through the GUI-run ScriptEnv script:
  `RMxprtDesign1` + `Setup1` produced `Maxwell2DDesign3` with geometry, `Setup1`, and winding groups
  `PhaseA`, `PhaseB`, `PhaseC`.
- Hard license blocker found on July 8, 2026: AEDT Student reports
  `Ansys Electronics Desktop Student does not support Maxwell Transient solution` when solving
  `Maxwell2DDesign3`. The converted FEM model is transient, so the end-to-end FEM solve/export pipeline
  cannot complete under the installed Student edition.
- Student-compatible Magnetostatic path confirmed on July 8, 2026:
  `Maxwell2DDesign3` was copied to `Maxwell2DDesign4`, converted with `SetSolutionType("Magnetostatic", "XY")`,
  assigned `Setup_MagProbe`, validated, and solved successfully.
- Report export path confirmed:
  `ReportSetup.ExportToFile(report_name, csv_path)` exported `Winding Table1`, and a generated report
  `MCP_FluxLinkage_ABC` exported phase flux linkage values for `PhaseA`, `PhaseB`, and `PhaseC`.
  Example exported row:
  `fractions=4`, `FluxLinkage(PhaseA)=0.0155609380613968 Wb`,
  `FluxLinkage(PhaseB)=0.0509523868830839 Wb`,
  `FluxLinkage(PhaseC)=-0.0486271433364105 Wb`.
- Unsafe broad report probing script was disabled after it crashed AEDT. Do not use broad loops over report
  contexts/creation. Use narrow known-good operations only.
- Graphical AEDT launch should not be attempted by Codex.
- `C:\temp` and OneDrive Ansoft config write dependencies must not be assumed.

## Next Manual Procedure

Proceed through ScriptEnv-backed AEDT automation. Treat PyAEDT as a blocked attach layer unless its session discovery behavior changes in a future PyAEDT/AEDT version.

The MCP server now exposes the ScriptEnv-first FEM data-generation workflow:

- `aedt.generate_scriptenv_probe`
- `aedt.resume_scriptenv_probe`
- `aedt.generate_project_probe_procedure`
- `aedt.resume_project_probe`
- `aedt.generate_fem_export_plan`
- `aedt.generate_fem_export_procedure`
- `aedt.resume_fem_export`
- `aedt.fem_export_status`

Run `smoke` (`2 x 2`) first, then `validation` (`5 x 5`), then `full` (`40 x 40`) after CSV status is finite and complete.

For the current Student install, do not attempt `Maxwell2DDesign3` transient solves again. Viable next paths are:

- Use a non-Student AEDT license that supports Maxwell Transient, then rerun the smoke exporter.
- Continue the supported Maxwell 2D Magnetostatic data-generation workflow using
  `tmp/aedt_projects/ipm_1_probe/gui_fem_export_smoke_magnetostatic.py`.
- Use RMxprt analytical outputs as a non-FEM fallback dataset, clearly labeled as not FEM.
