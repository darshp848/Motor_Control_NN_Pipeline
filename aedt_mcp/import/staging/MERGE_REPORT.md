# Merge Report

## Imported Sources

- Existing Codex AEDT MCP project: `aedt_mcp`.
- Prior GLM 5.2 project-local AEDT MCP reference: `../glm5.2_work_july-7-26/aedt_mcp`.
- Upstream inspected Codex AEDT MCP reference: `../tmp/ansys-aedt-mcp-inspect`.

## Overlap

- `server.py`: both projects exposed MCP tools. The richer `aedt_mcp/src/aedt_mcp/server.py` was kept as the primary server.
- AEDT launch/attach behavior: prior implementations attempted PyAEDT launch or attach directly. The merged design blocks those paths and generates procedures.
- Tests: existing schema/server registration tests were preserved and extended.

## Resolution

- Kept the richer PyAEDT tool modules under `src/aedt_mcp/tools`.
- Added a formal execution policy in `src/aedt_mcp/execution_policy.py`.
- Added operator procedure generation in `src/aedt_mcp/procedures.py`.
- Added safe operator tools in `src/aedt_mcp/operator_tools.py`.
- Added state file at `src/aedt_mcp/state/capabilities.json`.
- Hardened `SESSION.launch()` so direct AEDT launch is policy-blocked.

## Unresolved

- Live AEDT gRPC attach remains manual/user-run until native PowerShell output confirms a stable attach path.
