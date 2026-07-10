# MCP Tool Policy

## Tier 0: Safe Automatic

- Read workspace files.
- Write workspace files.
- Parse logs under `tmp/aedt_jobs`.
- Parse copied config files.
- Generate scripts and docs.
- Run unit tests that do not launch AEDT.
- Inspect Python package versions.

## Tier 1: Cautious Workspace-Only

- Create `tmp/aedt_temp`, `tmp/aedt_projects`, `tmp/aedt_jobs`.
- Run dry-run diagnostics.
- Run wrapper tests that do not launch AEDT.
- Write generated procedures under `docs/procedures`.
- Write generated attach scripts under `scripts/generated`.

## Tier 2: User-Run Native PowerShell Required

- Launch `ansysedt.exe`.
- Attach to live AEDT gRPC sessions.
- Kill AEDT processes.
- Modify AEDT config under OneDrive Documents.
- Modify Program Files.
- Modify Windows permissions.
- Check or modify firewall settings.
- Check license services.
- Test root-level paths such as `C:\temp`.
- Run commands that require elevation.

Tier 2 actions return `user_action_required` with commands, expected output, paste-back instructions, log paths, and cleanup notes.

ScriptEnv FEM export tools are safe at the MCP layer because they only generate scripts/procedures and parse workspace-local files. The actual AEDT attach, project open, solve, and export remain Tier 2 user-run native PowerShell actions.

## Tier 3: Manual AEDT GUI Required

- AEDT first-run initialization.
- Student license confirmation.
- GUI-only preference changes.
- Manual AEDT settings inspection.
- Manual project opening or export.
