param(
    [string]$RepositoryRoot = (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))
)

$ErrorActionPreference = 'Stop'
$exe = 'C:\Program Files\ANSYS Inc\ANSYS Student\v252\AnsysEM\ansysedtsv.exe'
$exporter = Join-Path $RepositoryRoot 'eesm\aedt\export_eesm_points.py'
$campaignRoot = Join-Path $RepositoryRoot 'out\eesm\task9_baseline'
$statusPath = Join-Path $campaignRoot 'raw\campaign_status.json'
$runnerStatusPath = Join-Path $campaignRoot 'background_runner_status.json'
$lockPath = Join-Path $RepositoryRoot 'aedt_mcp\tmp\aedt_projects\eesm_qual\eesm_qual.aedt.lock'

function Write-RunnerStatus {
    param([string]$State, [int]$Completed, [string]$Message, [int]$ProcessId = 0)
    [ordered]@{
        state = $State
        completed = $Completed
        total = 64
        message = $Message
        aedt_process_id = $ProcessId
        updated_at = (Get-Date).ToString('o')
    } | ConvertTo-Json | Set-Content -LiteralPath $runnerStatusPath -Encoding utf8
}

if (-not (Test-Path -LiteralPath $exe)) { throw "Missing AEDT executable: $exe" }
if (-not (Test-Path -LiteralPath $exporter)) { throw "Missing exporter: $exporter" }
if (-not (Test-Path -LiteralPath $statusPath)) { throw "Missing campaign status: $statusPath" }

try {
    while ($true) {
        $status = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
        $completed = @($status.completed).Count
        if ($status.status -eq 'failed') {
            throw "Campaign exporter reported failure after $completed qualifying rows"
        }
        if ($completed -ge 64 -or $status.status -eq 'complete') {
            Write-RunnerStatus -State 'complete' -Completed $completed -Message 'All frozen points completed'
            break
        }
        if (Get-Process -Name ansysedtsv -ErrorAction SilentlyContinue) {
            throw 'Refusing to start while another AEDT Student process is running'
        }
        if (Test-Path -LiteralPath $lockPath) {
            throw "Refusing to start while the qualified project lock exists: $lockPath"
        }

        $nextNumber = $completed + 1
        $logPath = Join-Path $campaignRoot ('background_point_{0:D2}.log' -f $nextNumber)
        $process = Start-Process -FilePath $exe -ArgumentList @(
            '-ng', '-Iconic', '-LogFile', ('"' + $logPath + '"'),
            '-RunScriptAndExit', ('"' + $exporter + '"')
        ) -WindowStyle Hidden -PassThru
        Write-RunnerStatus -State 'running' -Completed $completed -Message "Solving point $nextNumber" -ProcessId $process.Id
        Wait-Process -Id $process.Id

        for ($attempt = 0; $attempt -lt 20 -and (Test-Path -LiteralPath $lockPath); $attempt++) {
            Start-Sleep -Milliseconds 500
        }
        if (Test-Path -LiteralPath $lockPath) {
            throw "AEDT exited but the qualified project lock remains: $lockPath"
        }

        $updated = Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json
        $updatedCount = @($updated.completed).Count
        if ($updated.status -eq 'failed') {
            throw "Point $nextNumber failed; inspect $statusPath and $logPath"
        }
        if ($updatedCount -ne $nextNumber) {
            throw "Expected $nextNumber completed points after AEDT exit, found $updatedCount"
        }
        Write-RunnerStatus -State 'between_points' -Completed $updatedCount -Message "Point $nextNumber qualified"
    }
}
catch {
    $count = 0
    if (Test-Path -LiteralPath $statusPath) {
        $count = @((Get-Content -Raw -LiteralPath $statusPath | ConvertFrom-Json).completed).Count
    }
    Write-RunnerStatus -State 'failed' -Completed $count -Message $_.Exception.Message
    throw
}
