param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'
$source = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_requal_r3_gui_recovery_20260716_01\eesm_requal_r3_gui_working_20260716_01.aedt'
$targetName = 'eesm_requal_generated_r9_03_nominal_01'
$targetDir = Join-Path $RepositoryRoot (Join-Path 'aedt_mcp\tmp\aedt_projects' $targetName)
$target = Join-Path $targetDir ($targetName + '.aedt')
$targetResults = Join-Path $targetDir ($targetName + '.aedtresults')
$script = Join-Path $RepositoryRoot 'eesm\aedt\solve_generated_geometry_r9_03.py'
$outDir = Join-Path $RepositoryRoot 'out\eesm\task9_requalification_r9'
$preflight = Join-Path $outDir 'generated_geometry_preflight_attempt1.json'
$startedEvidence = Join-Path $outDir 'generated_geometry_solve_started_attempt1.json'
$result = Join-Path $outDir 'generated_geometry_solve_result_attempt1.json'
$runnerResult = Join-Path $outDir 'generated_geometry_runner_attempt1.json'
$manifest = Join-Path $outDir 'generated_geometry_results_manifest_attempt1.json'
$log = Join-Path $outDir 'generated_geometry_solve_attempt1.log'
$expectedHash = 'E99D4ABA12AC4DC139E8797482BB54C2240A1134D277EF74EE7FCB4F19AA57A9'

if (-not (Test-Path -LiteralPath $exe)) { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $source)) { throw "Missing corrected generated source: $source" }
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Corrected generated source hash drifted'
}
if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running'
}
foreach ($path in @($targetDir, $preflight, $startedEvidence, $result, $runnerResult, $manifest, $log)) {
    if (Test-Path -LiteralPath $path) { throw "One-use generated-geometry diagnostic already exists: $path" }
}

New-Item -ItemType Directory -Path $targetDir | Out-Null
Copy-Item -LiteralPath $source -Destination $target
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Disposable generated-geometry copy hash does not match source'
}

$startedAt = Get-Date
$process = Start-Process -FilePath $exe -ArgumentList @(
    '-ng', '-Iconic', '-LogFile', ('"' + $log + '"'),
    '-RunScriptAndExit', ('"' + $script + '"')
) -WindowStyle Hidden -PassThru
$timedOut = $false
try {
    Wait-Process -Id $process.Id -Timeout 1200 -ErrorAction Stop
}
catch {
    $timedOut = $true
    Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
    Wait-Process -Id $process.Id -ErrorAction SilentlyContinue
}
$process.Refresh()

[ordered]@{
    status = if ($timedOut) { 'timeout' } elseif (Test-Path -LiteralPath $result) { 'completed' } else { 'missing_result' }
    process_id = $process.Id
    exit_code = if ($timedOut) { $null } else { $process.ExitCode }
    elapsed_seconds = ((Get-Date) - $startedAt).TotalSeconds
    source_sha256 = $expectedHash.ToLowerInvariant()
    disposable_project = $target
    preflight_exists = Test-Path -LiteralPath $preflight
    solve_started_exists = Test-Path -LiteralPath $startedEvidence
    result_exists = Test-Path -LiteralPath $result
    training_authorized = $false
    task_10_authorized = $false
} | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runnerResult -Encoding utf8

# The results manifest is bookkeeping, not evidence. A failure here must
# never discard a completed AEDT run, so it is best-effort.
#
# NOTE: [IO.Path]::GetRelativePath is .NET Core / .NET 5+ only and does not
# exist in Windows PowerShell 5.1 (.NET Framework). Use a substring instead.
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
        root = $targetResults
        file_count = $files.Count
        files = $files
        collected_after_aedt_exit = $true
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $manifest -Encoding utf8
} catch {
    Write-Warning "results manifest generation failed (non-fatal): $($_.Exception.Message)"
}

if (-not (Test-Path -LiteralPath $result)) {
    throw "AEDT exited without a generated-geometry solve result; inspect $runnerResult and $log"
}
$payload = Get-Content -Raw -LiteralPath $result | ConvertFrom-Json
$payload | ConvertTo-Json -Depth 8
if ($payload.status -ne 'solve_completed') {
    throw "Generated-geometry diagnostic returned status $($payload.status); inspect $result and $log"
}
