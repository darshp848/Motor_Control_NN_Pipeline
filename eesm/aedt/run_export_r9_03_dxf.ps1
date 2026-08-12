# DXF geometry export runner for the FEMM path.
#
# Creates a DISPOSABLE copy of the r9_03 source, launches AEDT Student headless,
# and runs eesm/aedt/export_r9_03_dxf.py. Geometry export only -- no mesh, no
# solve, no campaign binding. Same one-use, hash-guarded, 5.1-safe pattern as
# run_validate_mesh_torque.ps1.

param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$SourceProjectPath = (Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_requal_generated_r9_03_nominal_01\eesm_requal_generated_r9_03_nominal_01.aedt'),
    [string]$ExpectedSha256 = '',
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'

$script = Join-Path $RepositoryRoot 'eesm\aedt\export_r9_03_dxf.py'
$outDir = Join-Path $RepositoryRoot 'out\eesm\femm_geometry_r9_03'
$result = Join-Path $outDir 'dxf_export_result.json'
$runner = Join-Path $outDir 'dxf_export_runner.json'
$log    = Join-Path $outDir 'dxf_export.log'

$targetName    = 'eesm_r9_03_dxf_01'
$targetDir     = Join-Path $RepositoryRoot (Join-Path 'aedt_mcp\tmp\aedt_projects' $targetName)
$target        = Join-Path $targetDir ($targetName + '.aedt')

if (-not (Test-Path -LiteralPath $exe))               { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $script))            { throw "Missing export script: $script" }
if (-not (Test-Path -LiteralPath $SourceProjectPath)) { throw "Missing r9_03 source project: $SourceProjectPath" }

if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running (single student licence).'
}

$sourceHash = (Get-FileHash -LiteralPath $SourceProjectPath -Algorithm SHA256).Hash
if ($ExpectedSha256 -ne '' -and $sourceHash -ne $ExpectedSha256) {
    throw "Source project hash drift.`n  expected $ExpectedSha256`n  actual   $sourceHash"
}

$sourceDir = Split-Path -Parent $SourceProjectPath
$sourceLock = Join-Path $sourceDir ([IO.Path]::GetFileNameWithoutExtension($SourceProjectPath) + '.aedt.lock')
if (Test-Path -LiteralPath $sourceLock) {
    Write-Warning "Removing stale lock next to source: $sourceLock"
    Remove-Item -LiteralPath $sourceLock -Force
}

if (Test-Path -LiteralPath $targetDir) {
    throw "Disposable export copy already exists: $targetDir`nMove or delete it to re-run."
}
foreach ($p in @($result, $runner, $log)) {
    if (Test-Path -LiteralPath $p) { throw "One-use export artifact already exists: $p`nMove or delete it to re-run." }
}
if (-not (Test-Path -LiteralPath $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

New-Item -ItemType Directory -Path $targetDir | Out-Null
Copy-Item -LiteralPath $SourceProjectPath -Destination $target
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $sourceHash) {
    throw 'Disposable copy hash does not match the source'
}
Write-Host "Source     : $SourceProjectPath"
Write-Host "Source SHA : $sourceHash"
Write-Host "Disposable : $target"

$startedAt = Get-Date
$process = Start-Process -FilePath $exe -ArgumentList @(
    '-ng', '-Iconic', '-LogFile', ('"' + $log + '"'),
    '-RunScriptAndExit', ('"' + $script + '"')
) -WindowStyle Hidden -PassThru

$timedOut = $false
try {
    Wait-Process -Id $process.Id -Timeout $TimeoutSeconds -ErrorAction Stop
}
catch {
    $timedOut = $true
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $process.Id -ErrorAction SilentlyContinue
}
$process.Refresh()

[ordered]@{
    status              = if ($timedOut) { 'timeout' } elseif (Test-Path -LiteralPath $result) { 'completed' } else { 'missing_result' }
    source_project      = $SourceProjectPath
    source_sha256       = $sourceHash.ToLowerInvariant()
    disposable_project  = $target
    process_id          = $process.Id
    exit_code           = if ($timedOut) { $null } else { $process.ExitCode }
    elapsed_seconds     = ((Get-Date) - $startedAt).TotalSeconds
    result_exists       = Test-Path -LiteralPath $result
    solve_attempted     = $false
    campaign_authorized = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runner -Encoding utf8

if (-not (Test-Path -LiteralPath $result)) {
    throw "AEDT exited without writing a result; inspect $runner and $log"
}

$payload = Get-Content -Raw -LiteralPath $result | ConvertFrom-Json
Write-Host ''
Write-Host "Export status : $($payload.status)"
Write-Host "DXF exists    : $($payload.dxf_exists)"
Write-Host "DXF bytes     : $($payload.dxf_bytes)"
Write-Host "Objects       : $(@($payload.objects).Count)"
if ($payload.errors) { $payload.errors | ForEach-Object { Write-Warning $_ } }
