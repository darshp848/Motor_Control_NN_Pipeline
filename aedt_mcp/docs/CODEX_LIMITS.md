# Codex AEDT Limits

Codex can safely inspect and edit this repository, but it cannot reliably perform every Windows or AEDT operation.

Known limits:

- AEDT Student target: `2025.2SV`.
- `C:\temp` is not available to Codex.
- Project-local temp is `tmp/aedt_temp`.
- Project-local AEDT projects are under `tmp/aedt_projects`.
- Project-local job logs are under `tmp/aedt_jobs`.
- AEDT launch and PyAEDT attach from Codex are unreliable.
- PyAEDT attach is confirmed to miss the active AEDT gRPC listener on port `50052` and attempt a new launch.
- Raw ScriptEnv attach is confirmed working and returned AEDT version `2025.2.0`.
- Native Windows actions such as process cleanup, firewall checks, Program Files edits, OneDrive Ansoft config edits, permissions, and license-service checks are user-run only.

The MCP server therefore acts as an orchestration layer. It performs safe workspace-local work automatically and generates exact native PowerShell procedures for unsafe or unreliable actions.
