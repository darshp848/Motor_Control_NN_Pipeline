param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'
$source = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_requal_direct_r9_02\eesm_requal_direct_r9_02.aedt'
$targetName = 'eesm_requal_direct_r9_02_meshdiag_02'
$targetDir = Join-Path $RepositoryRoot (Join-Path 'aedt_mcp\tmp\aedt_projects' $targetName)
$target = Join-Path $targetDir ($targetName + '.aedt')
$targetResults = Join-Path $targetDir ($targetName + '.aedtresults')
$script = Join-Path $RepositoryRoot 'eesm\aedt\generate_mesh_direct_eesm_r9_02.py'
$outDir = Join-Path $RepositoryRoot 'out\eesm\task9_requalification_r9'
$preflight = Join-Path $outDir 'mesh_generate_preflight_attempt2.json'
$result = Join-Path $outDir 'mesh_generate_result_attempt2.json'
$runnerResult = Join-Path $outDir 'mesh_generate_runner_attempt2.json'
$manifest = Join-Path $outDir 'mesh_generate_results_manifest_attempt2.json'
$log = Join-Path $outDir 'mesh_generate_attempt2.log'
$expectedHash = '7B7FBD31320AFC64C4F031FB8480EBCA89071B9B43E2945F47E8A6243CF60CB3'

if (-not (Test-Path -LiteralPath $exe)) { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $source)) { throw "Missing immutable r9_02 source: $source" }
if ((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Immutable r9_02 source hash drifted'
}
if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
    throw 'Refusing to start while another AEDT Student process is running'
}
foreach ($path in @($targetDir, $preflight, $result, $runnerResult, $manifest, $log)) {
    if (Test-Path -LiteralPath $path) { throw "One-use r9 mesh diagnostic already exists: $path" }
}

New-Item -ItemType Directory -Path $targetDir | Out-Null
Copy-Item -LiteralPath $source -Destination $target
if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Disposable r9_02 copy hash does not match immutable source'
}

$started = Get-Date
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

$runnerPayload = [ordered]@{
    status = if ($timedOut) { 'timeout' } elseif (Test-Path -LiteralPath $result) { 'completed' } else { 'missing_result' }
    process_id = $process.Id
    exit_code = if ($timedOut) { $null } else { $process.ExitCode }
    elapsed_seconds = ((Get-Date) - $started).TotalSeconds
    source_sha256 = $expectedHash.ToLowerInvariant()
    disposable_project = $target
    preflight_exists = Test-Path -LiteralPath $preflight
    result_exists = Test-Path -LiteralPath $result
    maxwell_solve_attempted = $false
    training_authorized = $false
    task_10_authorized = $false
}
$runnerPayload | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $runnerResult -Encoding utf8

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
    throw "AEDT exited without a mesh result; inspect $runnerResult and $log"
}
$payload = Get-Content -Raw -LiteralPath $result | ConvertFrom-Json
$payload | ConvertTo-Json -Depth 8
if ($payload.status -ne 'mesh_generated') {
    throw "r9 mesh diagnostic returned status $($payload.status); inspect $result and $log"
}
