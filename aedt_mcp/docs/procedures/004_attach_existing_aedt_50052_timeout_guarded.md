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
$aedtConn = Get-NetTCPConnection -LocalPort 50052 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $aedtConn) { throw 'No AEDT listener found on port 50052.' }
$env:AEDT_ATTACH_PID = [string]$aedtConn.OwningProcess
$env:PYAEDT_USE_PRE_GRPC_ARGS = 'True'
$env:PYAEDT_DESKTOP_PORT = '50052'
$env:no_proxy = 'localhost,127.0.0.1'
$env:NO_PROXY = 'localhost,127.0.0.1'
$pyaedt = Start-Process -FilePath $pythonExe -ArgumentList @('scripts\generated\attach_pyaedt_50052.py') -RedirectStandardOutput tmp\aedt_jobs\attach_pyaedt_50052_user_run.log -RedirectStandardError tmp\aedt_jobs\attach_pyaedt_50052_user_run.err.log -NoNewWindow -PassThru
$null = Wait-Process -Id $pyaedt.Id -Timeout 45 -ErrorAction SilentlyContinue
if (-not $pyaedt.HasExited) { Stop-Process -Id $pyaedt.Id -Force; 'PyAEDT attach timed out after 45s and was stopped by the user-run procedure.' | Add-Content tmp\aedt_jobs\attach_pyaedt_50052_user_run.err.log }
$scriptenv = Start-Process -FilePath $pythonExe -ArgumentList @('scripts\generated\attach_scriptenv_50052.py') -RedirectStandardOutput tmp\aedt_jobs\attach_scriptenv_50052_user_run.log -RedirectStandardError tmp\aedt_jobs\attach_scriptenv_50052_user_run.err.log -NoNewWindow -PassThru
$null = Wait-Process -Id $scriptenv.Id -Timeout 45 -ErrorAction SilentlyContinue
if (-not $scriptenv.HasExited) { Stop-Process -Id $scriptenv.Id -Force; 'ScriptEnv attach timed out after 45s and was stopped by the user-run procedure.' | Add-Content tmp\aedt_jobs\attach_scriptenv_50052_user_run.err.log }
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
