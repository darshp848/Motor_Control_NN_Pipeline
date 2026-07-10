# attach_existing_aedt_50052

Status: `user_action_required`
Risk: `medium`

## Reason
Attach is separate from launch and must use new_desktop=False.

## Commands
```powershell
$ErrorActionPreference = 'Stop'
$projectRoot = 'C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp'
Set-Location -LiteralPath $projectRoot
$pythonCandidates = @((Join-Path $projectRoot '..\..\.venv\Scripts\python.exe'), (Join-Path $projectRoot '..\.venv\Scripts\python.exe'), (Join-Path $projectRoot '.venv\Scripts\python.exe'))
$pythonExe = $pythonCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $pythonExe) { $pythonExe = 'python' }
$env:PYAEDT_USE_PRE_GRPC_ARGS = 'True'
$env:no_proxy = 'localhost,127.0.0.1'
$env:NO_PROXY = 'localhost,127.0.0.1'
& $pythonExe scripts\generated\attach_pyaedt_50052.py *> tmp\aedt_jobs\attach_pyaedt_50052_user_run.log
& $pythonExe scripts\generated\attach_scriptenv_50052.py *> tmp\aedt_jobs\attach_scriptenv_50052_user_run.log
```

## Expected Output
- Connected
- AEDT version text
- Project list or ScriptEnv desktop version

## Paste Back
- The PyAEDT attach log.
- The ScriptEnv attach log if generated.

## Log Paths
- tmp/aedt_jobs/attach_pyaedt_50052_user_run.log
- tmp/aedt_jobs/attach_scriptenv_50052_user_run.log

## Cleanup
- Do not start a second AEDT process for attach tests.
