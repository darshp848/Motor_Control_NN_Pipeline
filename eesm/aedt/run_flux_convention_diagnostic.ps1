# Flux-extraction convention diagnostic.
#
# Follows the same one-use, hash-guarded, disposable-copy pattern as
# run_r9_solve_diagnostic.ps1. Collects evidence only: it solves four cheap
# probe points and exports three independent flux measurements per point.
# It applies no correction and authorises no campaign, qualification, or
# training step.
#
# Default source is the Task 8/9 campaign project `eesm_qual`, because that
# is the model whose exported flux failed the balanced-winding law. Pass
# -Source R3Working to diagnose the corrected r3 generated-geometry model
# instead (the one r9_03 solved in 7.56 s).

param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)),
    [ValidateSet('CampaignModel', 'R3Working')]
    [string]$Source = 'CampaignModel',
    [int]$TimeoutSeconds = 1800
)

$ErrorActionPreference = 'Stop'

$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'

# NOTE: do not name this '$source'. PowerShell variable names are
# case-insensitive, so assigning $source would rebind the [ValidateSet]
# parameter $Source and re-trigger its validation against a file path.
switch ($Source) {
    'CampaignModel' {
        $sourceProject = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_qual\eesm_qual.aedt'
        $expectedHash = '28AEDC7F1D55832D2239660638B0B2F91D0839367B836994D70D0E0FA1F386CC'
    }
    'R3Working' {
        $sourceProject = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_requal_r3_gui_recovery_20260716_01\eesm_requal_r3_gui_working_20260716_01.aedt'
        $expectedHash = 'E99D4ABA12AC4DC139E8797482BB54C2240A1134D277EF74EE7FCB4F19AA57A9'
    }
}

$targetName    = 'eesm_fluxdiag_01'
$targetDir     = Join-Path $RepositoryRoot (Join-Path 'aedt_mcp\tmp\aedt_projects' $targetName)
$target        = Join-Path $targetDir ($targetName + '.aedt')
$targetResults = Join-Path $targetDir ($targetName + '.aedtresults')

$script   = Join-Path $RepositoryRoot 'eesm\aedt\diagnose_flux_convention.py'
$outDir   = Join-Path $RepositoryRoot 'out\eesm\flux_convention_diagnostic'
$evidence = Join-Path $outDir 'flux_convention_evidence.json'
$runner   = Join-Path $outDir 'diagnostic_runner.json'
$manifest = Join-Path $outDir 'diagnostic_results_manifest.json'
$log      = Join-Path $outDir 'diagnostic.log'

# ---- preflight guards -------------------------------------------------------

if (-not (Test-Path -LiteralPath $exe))           { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $script))        { throw "Missing diagnostic script: $script" }
if (-not (Test-Path -LiteralPath $sourceProject)) { throw "Missing source project: $sourceProject" }

$actualHash = (Get-FileHash -LiteralPath $sourceProject -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw "Source project hash drifted for '$Source'.`n  expected $expectedHash`n  actual   $actualHash"
}

if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running (single student licence).'
}

foreach ($path in @($targetDir, $evidence, $runner, $manifest, $log)) {
    if (Test-Path -LiteralPath $path) {
        throw "One-use flux diagnostic artifact already exists: $path`nMove or delete it to re-run."
    }
}

if (-not (Test-Path -LiteralPath $outDir)) {
    New-Item -ItemType Directory -Path $outDir | Out-Null
}

# ---- disposable copy --------------------------------------------------------

New-Item -ItemType Directory -Path $targetDir | Out-Null
Copy-Item -LiteralPath $sourceProject -Destination $target
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Disposable copy hash does not match the immutable source'
}
Write-Host "Source     : $Source"
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

# ---- evidence ---------------------------------------------------------------

[ordered]@{
    status                  = if ($timedOut) { 'timeout' } elseif (Test-Path -LiteralPath $evidence) { 'completed' } else { 'missing_evidence' }
    source_selector         = $Source
    source_project          = $sourceProject
    source_sha256           = $expectedHash.ToLowerInvariant()
    disposable_project      = $target
    process_id              = $process.Id
    exit_code               = if ($timedOut) { $null } else { $process.ExitCode }
    elapsed_seconds         = ((Get-Date) - $startedAt).TotalSeconds
    evidence_exists         = Test-Path -LiteralPath $evidence
    campaign_authorized     = $false
    qualification_authorized = $false
    training_authorized     = $false
    task_10_authorized      = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runner -Encoding utf8

# The results manifest is bookkeeping, not evidence. A failure here must
# never discard a completed AEDT run, so it is best-effort.
#
# NOTE: [IO.Path]::GetRelativePath is .NET Core / .NET 5+ only and does not
# exist in Windows PowerShell 5.1 (.NET Framework). Use a substring instead.
# The same latent bug is present in the existing run_r9_*.ps1 runners; it has
# not surfaced there only because those runs produced empty results folders.
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

if (-not (Test-Path -LiteralPath $evidence)) {
    throw "AEDT exited without writing evidence; inspect $runner and $log"
}

$payload = Get-Content -Raw -LiteralPath $evidence | ConvertFrom-Json
Write-Host ''
Write-Host "Diagnostic status : $($payload.status)"
if ($payload.points) {
    foreach ($point in $payload.points) {
        $solved = if ($point.solve.ok) { 'solved' } else { 'FAILED' }
        Write-Host ("  {0,-20} {1,-8} {2:N1}s" -f $point.point, $solved, $point.solve_seconds)
    }
}
Write-Host ''
Write-Host 'Next: run the offline analyser'
Write-Host "  .\.venv\Scripts\python.exe eesm/aedt/analyze_flux_convention.py `"$evidence`" `"$(Join-Path $outDir 'verdict.json')`""

if ($payload.status -ne 'collected') {
    throw "Flux diagnostic returned status $($payload.status); inspect $evidence and $log"
}
