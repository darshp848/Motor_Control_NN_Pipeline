# Pilot EESM flux-extraction exporter runner.
#
# PILOT_EXECUTION_PLAN.md Phase 4.1 runner. Creates a DISPOSABLE copy of the
# Phase-1 project (ParallelBranchesNum=4 applied, per Phase 1.2), launches
# AEDT Student headless against it with Run Script AndExit, and records a
# non-fatal results manifest -- the same one-use, hash-guarded, disposable
# pattern as run_flux_convention_diagnostic.ps1.
#
# The exporter (eesm/aedt/export_eesm_points.py) is one-point-per-session:
# re-invoke this runner until the pilot status JSON reports `complete`. The
# exporter's progress-CSV resume path refuses to re-solve a converged point.
#
# PRECONDITIONS (operator; NOT done by this script):
#   1. PILOT_EXECUTION_PLAN.md Phase 1.1: a disposable copy of the working
#      RMxprt-derived project exists at -SourceProjectPath (default
#      aedt_mcp\tmp\aedt_projects\eesm_pilot_source_01\eesm_pilot_source_01.aedt).
#   2. Phase 1.2: that copy has ParallelBranchesNum = 4 on PhaseA/B/C and
#      =1 on Field (the exporter PREFLIGHT aborts otherwise).
#   3. The pilot block is frozen (eesm/aedt/freeze_pilot_block.py has been
#      run; out\eesm\pilot_20260721\frozen_points.csv + .sha256 exist).
#
# The exporter's PB=4 preflight is the real guard; the source-hash guard
# here only prevents silent source drift between runs. Because the source
# project is user-edited (PB=4 applied via GUI), its hash is NOT pinned in
# this script. Pass -ExpectedSha256 after recording it once (recommended)
# to make re-runs reproducible; omit on the first run after editing.

param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [string]$SourceProjectPath = (Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_pilot_source_01\eesm_pilot_source_01.aedt'),
    [string]$ExpectedSha256 = '',
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'

$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'

$script   = Join-Path $RepositoryRoot 'eesm\aedt\export_eesm_points.py'
$pilotDir = Join-Path $RepositoryRoot 'out\eesm\pilot_20260721'
$frozenCsv    = Join-Path $pilotDir 'frozen_points.csv'
$frozenSha256 = Join-Path $pilotDir 'frozen_points.sha256'

# The disposable copy created here. PROJECT_NAME in the exporter must equal
# the leaf name of this directory.
$targetName    = 'eesm_pilot_01'
$targetDir      = Join-Path $RepositoryRoot (Join-Path 'aedt_mcp\tmp\aedt_projects' $targetName)
$target         = Join-Path $targetDir ($targetName + '.aedt')
$targetResults  = Join-Path $targetDir ($targetName + '.aedtresults')

$rawDir   = Join-Path $pilotDir 'raw'
$statusJson = Join-Path $rawDir 'pilot_status.json'
$runner     = Join-Path $pilotDir 'pilot_runner.json'
$manifest   = Join-Path $pilotDir 'pilot_results_manifest.json'
$log        = Join-Path $pilotDir 'pilot_export.log'

# ---- preflight guards -------------------------------------------------------

if (-not (Test-Path -LiteralPath $exe))               { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $script))            { throw "Missing exporter script: $script" }
if (-not (Test-Path -LiteralPath $SourceProjectPath)) { throw "Missing source project: $SourceProjectPath. Complete PILOT_EXECUTION_PLAN.md Phase 1.1/1.2 first." }
if (-not (Test-Path -LiteralPath $frozenCsv))        { throw "Missing frozen pilot CSV: $frozenCsv. Run eesm\aedt\freeze_pilot_block.py first." }
if (-not (Test-Path -LiteralPath $frozenSha256))     { throw "Missing frozen pilot SHA-256: $frozenSha256. Run eesm\aedt\freeze_pilot_block.py first." }

if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running (single student licence).'
}

$sourceHash = (Get-FileHash -LiteralPath $SourceProjectPath -Algorithm SHA256).Hash
if ($ExpectedSha256 -ne '') {
    if ($sourceHash -ne $ExpectedSha256) {
        throw "Source project hash drift.`n  expected $ExpectedSha256`n  actual   $sourceHash`nRecord the current source hash and pass -ExpectedSha256, or omit it on the first run after editing (Phase 1.2)."
    }
}

# A stale .aedt.lock (dead PID from a hard kill) blocks the open. Remove it
# if it sits next to the source and points at no live process.
$sourceDir = Split-Path -Parent $SourceProjectPath
$sourceLock = Join-Path $sourceDir ([IO.Path]::GetFileNameWithoutExtension($SourceProjectPath) + '.aedt.lock')
if (Test-Path -LiteralPath $sourceLock) {
    Write-Warning "Removing stale lock file next to source: $sourceLock"
    Remove-Item -LiteralPath $sourceLock -Force
}

if (Test-Path -LiteralPath $targetDir) {
    throw "Disposable pilot copy already exists: $targetDir`nMove or delete it (and its .aedtresults) to re-run. Do NOT reuse a solved disposable copy."
}

if (-not (Test-Path -LiteralPath $pilotDir)) {
    New-Item -ItemType Directory -Path $pilotDir | Out-Null
}

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
    status                   = if ($timedOut) { 'timeout' } elseif (Test-Path -LiteralPath $statusJson) { 'completed' } else { 'missing_status' }
    source_project           = $SourceProjectPath
    source_sha256            = $sourceHash.ToLowerInvariant()
    expected_sha256          = if ($ExpectedSha256 -ne '') { $ExpectedSha256.ToLowerInvariant() } else { $null }
    frozen_points_csv        = $frozenCsv
    frozen_points_sha256_file = $frozenSha256
    disposable_project       = $target
    process_id               = $process.Id
    exit_code                = if ($timedOut) { $null } else { $process.ExitCode }
    elapsed_seconds          = ((Get-Date) - $startedAt).TotalSeconds
    status_json_exists       = Test-Path -LiteralPath $statusJson
    campaign_authorized      = $false
    qualification_authorized = $false
    training_authorized      = $false
    task_10_authorized       = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runner -Encoding utf8

# The results manifest is bookkeeping, not evidence. A failure here must
# never discard a completed AEDT run, so it is best-effort (same pattern as
# run_flux_convention_diagnostic.ps1). Windows PowerShell 5.1 has no
# [IO.Path]::GetRelativePath; use a substring instead.
try {
    $files = @()
    if (Test-Path -LiteralPath $targetResults) {
        $prefix = (Resolve-Path -LiteralPath $targetResults).Path.TrimEnd('\') + '\'
        $files = @(Get-ChildItem -LiteralPath $targetResults -Recurse -Force -File | Sort-Object FullName | ForEach-Object {
            $full = $_.FullName
            $relative = if ($full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
                $full.Substring($prefix.Length)
            } else {
                $full
            }
            [ordered]@{
                path       = $relative
                size_bytes = $_.Length
                sha256     = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
            }
        })
    }
    [ordered]@{
        root                      = $targetResults
        file_count                = $files.Count
        files                     = $files
        collected_after_aedt_exit = $true
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding utf8
}
catch {
    Write-Warning "Results manifest could not be written (bookkeeping only, evidence is unaffected): $($_.Exception.Message)"
    [ordered]@{
        root                      = $targetResults
        file_count                = $null
        files                     = @()
        collected_after_aedt_exit = $true
        manifest_error            = $_.Exception.Message
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding utf8
}

if (-not (Test-Path -LiteralPath $statusJson)) {
    throw "AEDT exited without writing pilot status; inspect $runner and $log"
}

$payload = Get-Content -Raw -LiteralPath $statusJson | ConvertFrom-Json
Write-Host ''
Write-Host "Pilot status : $($payload.status)"
if ($payload.completed) {
    Write-Host ("  completed : {0} / {1}" -f $payload.completed.Count, $payload.points_sha256.Count)
}
if ($payload.failure) {
    Write-Host "  FAILURE at $($payload.failure.point) (or preflight): $($payload.failure.error)"
}
Write-Host ''
if ($payload.status -eq 'complete') {
    Write-Host 'Pilot complete. Next: run the offline batch invariant gates, then'
    Write-Host 'PILOT_EXECUTION_PLAN.md Phase 5 lock-in.'
} else {
    Write-Host 'Re-invoke this runner to continue (one point per session).'
    Write-Host "Status: $pilotDir\raw\pilot_status.json"
}