# Operator Procedures

Generated procedures are numbered, copy-pasteable native PowerShell instructions for work Codex should not run directly.

Use this flow:

1. Call `aedt.generate_launch_procedure`.
2. Run the returned commands in native PowerShell.
3. Paste the requested log output back through `aedt.resume_from_user_output`.
4. If the launch log shows `GRPC server running on port: <port>`, call `aedt.generate_attach_test`.
5. Run the generated attach script from native PowerShell.
6. If PyAEDT reports that it will open a new AEDT session, treat that as a blocked `pyaedt_attach` failure.
7. If ScriptEnv returns a version such as `2025.2.0`, continue with ScriptEnv-backed automation.
8. Paste the attach logs back through `aedt.resume_from_user_output`.

Launch and attach are deliberately separate. Attach tests must use `new_desktop=False` and must never start a second AEDT instance.

## ScriptEnv FEM Export Workflow

Use this sequence for end-to-end FEM data generation:

1. `aedt.generate_launch_procedure`
2. Run the native PowerShell launch procedure.
3. `aedt.generate_scriptenv_probe`
4. Run the ScriptEnv probe procedure and paste logs to `aedt.resume_scriptenv_probe`.
5. `aedt.generate_project_probe_procedure` with the source `.aedt` project path.
6. Run the project probe procedure and paste logs to `aedt.resume_project_probe`.
7. Pick a Maxwell design, setup, and winding/phase names from the probe JSON.
8. `aedt.generate_fem_export_plan` with stage `smoke`, then `validation`, then `full`.
9. `aedt.generate_fem_export_procedure` using the copied project path from the probe result.
10. Run the export procedure and paste logs to `aedt.resume_fem_export`.
11. Check `aedt.fem_export_status`.

Current AEDT Student 2025 R2 limitation:

- RMxprt-to-Maxwell conversion can create a transient `Maxwell 2D` motor model.
- AEDT Student rejects solving that transient model with:
  `Ansys Electronics Desktop Student does not support Maxwell Transient solution`.
- Treat that message as a hard blocker for transient FEM export on Student. Do not keep retrying the same solve.
- Continue only with a non-Student AEDT license, a supported Magnetostatic/Eddy Current workflow, or a clearly labeled RMxprt analytical fallback.

The final CSV contract is:

```text
Id,Iq,Phi_d,Phi_q
```

Default export stages:

- `smoke`: `2 x 2`
- `validation`: `5 x 5`
- `full`: `40 x 40`
