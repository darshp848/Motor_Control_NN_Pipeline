# launch_aedt_grpc_50052

Status: `user_action_required`
Risk: `medium`

## Reason

Launching `ansysedt.exe` is Tier 2: native user-run PowerShell required.

## Commands

```powershell
$ErrorActionPreference = 'Stop'
$projectRoot = 'C:\Users\darsh\TAMU\EMPE_Lab\Motor_Control_NN_Pipeline\aedt_mcp'
Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Force -Path 'tmp\aedt_temp','tmp\aedt_projects','tmp\aedt_jobs' | Out-Null
$env:TEMP = (Resolve-Path 'tmp\aedt_temp').Path
$env:TMP = (Resolve-Path 'tmp\aedt_temp').Path
$log = (Resolve-Path 'tmp\aedt_jobs').Path + '\\aedt_grpc_50052_user_run.log'
$roots = @($env:ANSYSEMSV_ROOT252, $env:ANSYSEM_ROOT252, 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM', 'C:\Program Files\ANSYS Inc\v252\AnsysEM') | Where-Object { $_ }
$candidateExe = foreach ($root in $roots) { Join-Path $root 'ansysedtsv.exe'; Join-Path $root 'ansysedt.exe'; Join-Path $root 'ansysedtng.exe'; Join-Path $root 'Win64\ansysedt.exe' }
$aedtExe = $candidateExe | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $aedtExe) { throw "Could not find AEDT executable. Paste back `$roots and `$candidateExe." }
& $aedtExe -ng -grpcsrv 50052 *> $log
```

## Expected Output

- `GRPC server running on port: 50052`
- An `ansysedt` or `ansysedtsv` process remains running.

## Paste Back

- The final 80 lines of the log.
- The PID and port if PowerShell reports them.

## Log Paths

- `tmp/aedt_jobs/aedt_grpc_50052_user_run.log`
- `batch.log`

## Cleanup

- Close AEDT manually only if the process hangs.
