# Flux-linkage METHOD COMPARISON runner.
#
# out/eesm/pilot_20260721/PILOT_FINDINGS.md recommended experiment. Creates a
# DISPOSABLE copy of the PB=4 pilot source, launches AEDT Student headless
# against it, and runs eesm/aedt/compare_flux_methods.py (single session, 5
# short points -- the flux-convention diagnostic proved a multi-point single
# session works on this licence).
#
# Same one-use, hash-guarded, disposable-copy, 5.1-safe, non-fatal-manifest
# pattern as run_flux_convention_diagnostic.ps1 and run_pilot_export.ps1.
#
# PRECONDITION: the PB=4 source exists at -SourceProjectPath (default is the
# same eesm_pilot_source_01 used by the pilot; PhaseA/B/C=4, Field=1). Record
# its hash once and pass -ExpectedSha256 to guard against source drift.

param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$SourceProjectPath = (Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_pilot_source_01\eesm_pilot_source_01.aedt'),
    [string]$ExpectedSha256 = '',
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'

$script  = Join-Path $RepositoryRoot 'eesm\aedt\compare_flux_methods.py'
$outDir  = Join-Path $RepositoryRoot 'out\eesm\flux_method_comparison'
$evidence = Join-Path $outDir 'flux_method_evidence.json'
$runner   = Join-Path $outDir 'compare_runner.json'
$manifest = Join-Path $outDir 'compare_results_manifest.json'
$log      = Join-Path $outDir 'compare.log'

# Disposable copy. The leaf name MUST equal PROJECT_NAME in compare_flux_methods.py.
$targetName    = 'eesm_fluxcmp_01'
$targetDir     = Join-Path $RepositoryRoot (Join-Path 'aedt_mcp\tmp\aedt_projects' $targetName)
$target        = Join-Path $targetDir ($targetName + '.aedt')
$targetResults = Join-Path $targetDir ($targetName + '.aedtresults')

# ---- preflight guards -------------------------------------------------------

if (-not (Test-Path -LiteralPath $exe))               { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $script))            { throw "Missing comparison script: $script" }
if (-not (Test-Path -LiteralPath $SourceProjectPath)) { throw "Missing PB=4 source project: $SourceProjectPath" }

if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running (single student licence).'
}

$sourceHash = (Get-FileHash -LiteralPath $SourceProjectPath -Algorithm SHA256).Hash
if ($ExpectedSha256 -ne '' -and $sourceHash -ne $ExpectedSha256) {
    throw "Source project hash drift.`n  expected $ExpectedSha256`n  actual   $sourceHash"
}

# Remove a stale lock next to the source (dead PID from a hard kill).
$sourceDir = Split-Path -Parent $SourceProjectPath
$sourceLock = Join-Path $sourceDir ([IO.Path]::GetFileNameWithoutExtension($SourceProjectPath) + '.aedt.lock')
if (Test-Path -LiteralPath $sourceLock) {
    Write-Warning "Removing stale lock next to source: $sourceLock"
    Remove-Item -LiteralPath $sourceLock -Force
}

if (Test-Path -LiteralPath $targetDir) {
    throw "Disposable comparison copy already exists: $targetDir`nMove or delete it (and its .aedtresults) to re-run."
}
foreach ($p in @($evidence, $runner, $manifest, $log)) {
    if (Test-Path -LiteralPath $p) {
        throw "One-use comparison artifact already exists: $p`nMove or delete it to re-run."
    }
}
if (-not (Test-Path -LiteralPath $outDir)) { New-Item -ItemType Directory -Path $outDir | Out-Null }

# ---- disposable copy --------------------------------------------------------

New-Item -ItemType Directory -Path $targetDir | Out-Null
Copy-Item -LiteralPath $SourceProjectPath -Destination $target
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $sourceHash) {
    throw 'Disposable copy hash does not match the source'
}
Write-Host "Source     : $SourceProjectPath"
Write-Host "Source SHA : $sourceHash"
Write-Host "Disposable : $target"

# ---- run --------------------------------------------------------------------

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

# ---- runner record ----------------------------------------------------------

[ordered]@{
    status              = if ($timedOut) { 'timeout' } elseif (Test-Path -LiteralPath $evidence) { 'completed' } else { 'missing_evidence' }
    source_project      = $SourceProjectPath
    source_sha256       = $sourceHash.ToLowerInvariant()
    disposable_project  = $target
    process_id          = $process.Id
    exit_code           = if ($timedOut) { $null } else { $process.ExitCode }
    elapsed_seconds     = ((Get-Date) - $startedAt).TotalSeconds
    evidence_exists     = Test-Path -LiteralPath $evidence
    campaign_authorized = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runner -Encoding utf8

# Results manifest is bookkeeping, not evidence: best-effort. Windows
# PowerShell 5.1 has no [IO.Path]::GetRelativePath -- use a substring.
try {
    $files = @()
    if (Test-Path -LiteralPath $targetResults) {
        $prefix = (Resolve-Path -LiteralPath $targetResults).Path.TrimEnd('\') + '\'
        $files = @(Get-ChildItem -LiteralPath $targetResults -Recurse -Force -File | Sort-Object FullName | ForEach-Object {
            $full = $_.FullName
            $relative = if ($full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) { $full.Substring($prefix.Length) } else { $full }
            [ordered]@{ path = $relative; size_bytes = $_.Length; sha256 = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant() }
        })
    }
    [ordered]@{ root = $targetResults; file_count = $files.Count; files = $files; collected_after_aedt_exit = $true } |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding utf8
}
catch {
    Write-Warning "Results manifest could not be written (bookkeeping only): $($_.Exception.Message)"
    [ordered]@{ root = $targetResults; file_count = $null; files = @(); manifest_error = $_.Exception.Message } |
        ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding utf8
}

if (-not (Test-Path -LiteralPath $evidence)) {
    throw "AEDT exited without writing evidence; inspect $runner and $log"
}

$payload = Get-Content -Raw -LiteralPath $evidence | ConvertFrom-Json
Write-Host ''
Write-Host "Comparison status : $($payload.status)"
if ($payload.points) {
    foreach ($pt in $payload.points) {
        $nz = if ($pt.native.ok) { '{0:N3}' -f $pt.native.torque_residual } else { 'n/a' }
        $cz = if ($pt.route_c.ok) { '{0:N3}' -f $pt.route_c.torque_residual } else { 'n/a' }
        Write-Host ("  {0,-16} T_resid  native={1,7}  routeC={2,7}" -f $pt.point, $nz, $cz)
    }
}
Write-Host ''
Write-Host 'Next: run the offline analyzer'
Write-Host "  .\.venv\Scripts\python.exe eesm\aedt\analyze_flux_methods.py"
if ($payload.status -ne 'collected') {
    throw "Comparison returned status $($payload.status); inspect $evidence and $log"
}
