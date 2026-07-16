param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'
$source = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_qual\eesm_qual.aedt'
$targetDir = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_requal_r2'
$target = Join-Path $targetDir 'eesm_requal_r2.aedt'
$script = Join-Path $RepositoryRoot 'eesm\aedt\diagnose_task9_torque.py'
$status = Join-Path $RepositoryRoot 'out\eesm\task9_requalification_r2\diagnostic_status.json'
$expectedHash = '28AEDC7F1D55832D2239660638B0B2F91D0839367B836994D70D0E0FA1F386CC'

if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running'
}
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Source project hash drifted; refusing corrective diagnosis'
}
if (Test-Path -LiteralPath $target) {
    throw "Corrective project already exists; refusing overwrite: $target"
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
Copy-Item -LiteralPath $source -Destination $target

$log = Join-Path $RepositoryRoot 'out\eesm\task9_requalification_r2\background_preflight.log'
$process = Start-Process -FilePath $exe -ArgumentList @(
    '-ng', '-Iconic', '-LogFile', ('"' + $log + '"'),
    '-RunScriptAndExit', ('"' + $script + '"')
) -WindowStyle Hidden -PassThru
Wait-Process -Id $process.Id
if (-not (Test-Path -LiteralPath $status)) { throw "Missing diagnostic status: $status" }
$payload = Get-Content -Raw -LiteralPath $status | ConvertFrom-Json
if ($payload.status -notin @('blocked_model_contract', 'complete')) {
    throw "Corrective diagnostic failed with status $($payload.status)"
}
$payload | ConvertTo-Json -Depth 8
