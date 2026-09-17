[CmdletBinding()]
param(
    [ValidateSet("Preflight", "Execute", "VerifyRuntime", "Commit")]
    [string]$Action = "Preflight",
    [switch]$ConfirmMaintenanceWindow,
    [switch]$ConfirmPostgresCommit,
    [int]$ApiPort = 8100
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
$source = Join-Path $repoRoot "data\dev_agent_studio.db"
$backupDirectory = Join-Path $repoRoot "data\backups"
$reportDirectory = Join-Path $repoRoot "artifacts\cutover"
$targetName = "jayagent_studio"

function Invoke-ProjectPython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python cutover command failed with exit code $LASTEXITCODE."
    }
}

function Assert-CutoverEnvironment {
    foreach ($name in @("JAYCODE_CUTOVER_ADMIN_URL", "JAYCODE_CUTOVER_DATABASE_URL")) {
        if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($name, "Process"))) {
            throw "Set $name in this PowerShell session before running the cutover script."
        }
    }
    if (-not (Test-Path -LiteralPath $python)) { throw "Project virtual environment Python is unavailable." }
    if (-not (Test-Path -LiteralPath $source)) { throw "Migration source SQLite database is unavailable." }
}

function Assert-WritersStopped {
    $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $ApiPort -ErrorAction SilentlyContinue)
    if ($listeners.Count -gt 0) {
        throw "API port $ApiPort is listening. Stop uvicorn/API before executing a cutover."
    }
    $writers = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -match "app\.harness\.worker|uvicorn.*app\.main|app\.main.*uvicorn" }
    )
    if ($writers.Count -gt 0) {
        throw "Jaycode Worker, Supervisor, or API process is still running. Stop it before executing a cutover."
    }
}

function Backup-DotEnv {
    param([string]$Timestamp)
    $envPath = Join-Path $repoRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath)) { throw ".env is missing; refusing to create a new configuration file during cutover." }
    $backupPath = Join-Path $backupDirectory ".env.pre-postgres-$Timestamp.bak"
    Copy-Item -LiteralPath $envPath -Destination $backupPath -ErrorAction Stop
    return $backupPath
}

function Set-DotEnvValue {
    param([string]$Path, [string]$Name, [string]$Value)
    $lines = @()
    if (Test-Path -LiteralPath $Path) { $lines = @(Get-Content -LiteralPath $Path) }
    $expression = "^" + [regex]::Escape($Name) + "="
    $found = $false
    $updated = foreach ($line in $lines) {
        if ($line -match $expression) {
            $found = $true
            "$Name=$Value"
        } else {
            $line
        }
    }
    if (-not $found) { $updated += "$Name=$Value" }
    $temporary = "$Path.cutover-tmp"
    [System.IO.File]::WriteAllLines($temporary, [string[]]$updated, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Invoke-RuntimeReadiness {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/health" -TimeoutSec 10
    $ready = Invoke-RestMethod -Uri "http://127.0.0.1:$ApiPort/ready" -TimeoutSec 10
    if ($health.status -ne "ok" -or $ready.status -ne "ready") {
        throw "API health/readiness check did not return ready."
    }
    return @{ health = $health.status; ready = $ready.status }
}

Set-Location $repoRoot
Assert-CutoverEnvironment

if ($Action -eq "Preflight") {
    Assert-WritersStopped
    Invoke-ProjectPython -m app.persistence.cutover --preflight
    Write-Host "Preflight passed. No database, SQLite file, or .env file was changed."
    exit 0
}

if ($Action -eq "VerifyRuntime") {
    $result = Invoke-RuntimeReadiness
    Write-Host ("PostgreSQL runtime readiness passed: health={0}, ready={1}" -f $result.health, $result.ready)
    Write-Host "No cutover commit write was performed. Use the post-cutover smoke procedure only after explicit commit confirmation."
    exit 0
}

if ($Action -eq "Commit") {
    if (-not $ConfirmPostgresCommit) {
        throw "Commit requires -ConfirmPostgresCommit. It performs the first confirmed PostgreSQL smoke writes."
    }
    $timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
    New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
    $commitReport = Join-Path $reportDirectory "stage6-commit-$timestamp.json"
    Invoke-ProjectPython (Join-Path $repoRoot "scripts\verify_postgres_cutover.py") --confirm-postgres-commit $targetName | Tee-Object -FilePath $commitReport
    Write-Host "PostgreSQL commit smoke passed. PostgreSQL is now the authoritative persistence backend; do not revert by changing .env alone."
    exit 0
}

if (-not $ConfirmMaintenanceWindow) {
    throw "Execute requires -ConfirmMaintenanceWindow. It creates jayagent_studio, imports real data, and updates .env."
}

Assert-WritersStopped
New-Item -ItemType Directory -Force -Path $backupDirectory | Out-Null
New-Item -ItemType Directory -Force -Path $reportDirectory | Out-Null
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$backup = Join-Path $backupDirectory "dev_agent_studio-pre-postgres-$timestamp.db"
$report = Join-Path $reportDirectory "stage6-import-$timestamp.json"
$verificationReport = Join-Path $reportDirectory "stage6-verify-$timestamp.json"
$envBackup = $null
$targetCreated = $false
$configurationChanged = $false

try {
    Invoke-ProjectPython -m app.persistence.migrate --backup-sqlite $backup --source-sqlite $source
    Invoke-ProjectPython -m app.persistence.cutover --create-target
    $targetCreated = $true
    Invoke-ProjectPython -m app.persistence.migrate --import-postgres --production-cutover --confirm-cutover-target $targetName --source-sqlite $backup --target-url-env JAYCODE_CUTOVER_DATABASE_URL --report $report
    Invoke-ProjectPython -m app.persistence.migrate --verify --production-cutover --confirm-cutover-target $targetName --source-sqlite $backup --target-url-env JAYCODE_CUTOVER_DATABASE_URL --report $verificationReport

    $envBackup = Backup-DotEnv -Timestamp $timestamp
    $envPath = Join-Path $repoRoot ".env"
    $targetUrl = [Environment]::GetEnvironmentVariable("JAYCODE_CUTOVER_DATABASE_URL", "Process")
    Set-DotEnvValue -Path $envPath -Name "JAYCODE_PERSISTENCE_STORE" -Value "postgres"
    Set-DotEnvValue -Path $envPath -Name "JAYCODE_RAG_STORE" -Value "pgvector"
    Set-DotEnvValue -Path $envPath -Name "DATABASE_URL" -Value $targetUrl
    Set-DotEnvValue -Path $envPath -Name "PGVECTOR_DATABASE_URL" -Value $targetUrl
    $configurationChanged = $true

    Write-Host "Import and verification passed. PostgreSQL configuration is staged, but no API or Worker was started."
    Write-Host "Start API and Worker manually, then run this script with -Action VerifyRuntime before the explicit post-cutover write commit."
}
catch {
    $failure = $_
    if ($configurationChanged -and $envBackup) {
        Copy-Item -LiteralPath $envBackup -Destination (Join-Path $repoRoot ".env") -Force
    }
    if ($targetCreated -and -not $configurationChanged) {
        try {
            Invoke-ProjectPython -m app.persistence.cutover --drop-created-target --confirm-drop "DROP_JAYAGENT_STUDIO_CREATED_THIS_RUN"
        } catch {
            Write-Warning "Import failed and the newly created target could not be removed. It was preserved for manual inspection."
        }
    }
    throw $failure
}
