param(
    [string]$ReportPath
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtualenv Python was not found."
}

$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("jaycode-test-sqlite-" + [guid]::NewGuid().ToString("N"))
$ownerFile = "$tempRoot.owner"
$ownerToken = [guid]::NewGuid().ToString("N")
$sqlitePath = Join-Path $tempRoot "test.db"
$report = Join-Path $repoRoot $ReportPath
$oldSqlitePath = $env:JAYCODE_TEST_SQLITE_PATH
$oldPgTestUrl = $env:JAYCODE_TEST_DATABASE_URL
$isolatedEnvNames = @("DATABASE_URL", "PGVECTOR_DATABASE_URL", "JAYCODE_PERSISTENCE_STORE", "JAYCODE_RAG_STORE", "JAYCODE_TEST_MODE", "JAYCODE_TEST_SQLITE_OWNER_TOKEN")
$oldIsolatedEnv = @{}
foreach ($name in $isolatedEnvNames) { $oldIsolatedEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process") }
$ruffStatus = "not_run"
$pytestStatus = "not_run"
$ruffOutput = ""
$scriptRuffOutput = ""
$pytestOutput = ""
$pytestCode = $null

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    [System.IO.File]::WriteAllText($ownerFile, $ownerToken, [System.Text.Encoding]::ASCII)
    $env:JAYCODE_TEST_SQLITE_PATH = $sqlitePath
    $env:JAYCODE_TEST_SQLITE_OWNER_TOKEN = $ownerToken
    $env:JAYCODE_TEST_MODE = "1"
    # Keep this baseline SQLite-only even if the caller has a separate PG test URL.
    Remove-Item Env:JAYCODE_TEST_DATABASE_URL -ErrorAction SilentlyContinue
    $env:DATABASE_URL = ""
    $env:PGVECTOR_DATABASE_URL = ""
    $env:JAYCODE_PERSISTENCE_STORE = "sqlite"
    $env:JAYCODE_RAG_STORE = "sqlite"

    Push-Location $repoRoot
    try {
        $ruffOutput = (& $python -m ruff check app tests 2>&1 | Out-String).Trim()
        $ruffCode = $LASTEXITCODE
        $scriptRuffOutput = (& $python -m ruff check scripts/sqlite_schema_report.py scripts/run_postgres_contracts.py 2>&1 | Out-String).Trim()
        $scriptRuffCode = $LASTEXITCODE
        $ruffStatus = if ($ruffCode -eq 0 -and $scriptRuffCode -eq 0) { "pass" } else { "fail (app/tests=$ruffCode, scripts=$scriptRuffCode)" }

        if ($ruffCode -eq 0 -and $scriptRuffCode -eq 0) {
            $pytestOutput = (& $python -m pytest -q tests 2>&1 | Out-String).Trim()
            $pytestCode = $LASTEXITCODE
            $pytestStatus = if ($pytestCode -eq 0) { "pass" } else { "fail (exit $pytestCode)" }
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    if ($null -ne $oldSqlitePath) { $env:JAYCODE_TEST_SQLITE_PATH = $oldSqlitePath }
    else { Remove-Item Env:JAYCODE_TEST_SQLITE_PATH -ErrorAction SilentlyContinue }
    if ($null -ne $oldPgTestUrl) { $env:JAYCODE_TEST_DATABASE_URL = $oldPgTestUrl }
    else { Remove-Item Env:JAYCODE_TEST_DATABASE_URL -ErrorAction SilentlyContinue }
    foreach ($name in $isolatedEnvNames) {
        if ($null -ne $oldIsolatedEnv[$name]) { [Environment]::SetEnvironmentVariable($name, $oldIsolatedEnv[$name], "Process") }
        else { [Environment]::SetEnvironmentVariable($name, $null, "Process") }
    }

    $resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
    $resolvedSystemTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
    if ($resolvedTemp.StartsWith("$resolvedSystemTemp\", [System.StringComparison]::OrdinalIgnoreCase) -and
        (Split-Path -Leaf $resolvedTemp).StartsWith("jaycode-test-sqlite-", [System.StringComparison]::Ordinal) -and
        (Test-Path -LiteralPath $ownerFile -PathType Leaf) -and
        ([System.IO.File]::ReadAllText($ownerFile) -ceq $ownerToken)) {
        try {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force -ErrorAction Stop
            Remove-Item -LiteralPath $ownerFile -Force -ErrorAction Stop
        }
        catch {
            Write-Warning "Could not clean this run's isolated SQLite directory; it was preserved: $resolvedTemp"
        }
    }
    else {
        Write-Warning "Temporary SQLite ownership check failed; directory was preserved."
    }

    if (-not $ReportPath) { $ReportPath = "docs/reports/p1-stage0-baseline-$(Get-Date -Format 'yyyyMMdd-HHmmss').md" }
    $report = Join-Path $repoRoot $ReportPath
    if (Test-Path -LiteralPath $report) { throw "Baseline report already exists; refusing to overwrite: $report" }
    $reportDirectory = Split-Path -Parent $report
    New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
    $pythonVersion = (& $python --version 2>&1 | Out-String).Trim()
    $pythonDetails = (& $python -c "import importlib.metadata as m,sys; print('Executable:',sys.executable); print('Version:',sys.version.split()[0]); names=['pytest','ruff','psycopg','fastapi']; [print(n+':',m.version(n)) for n in names]" 2>&1 | Out-String).Trim()
    $ruffOutput = $ruffOutput -replace '(?i)postgres(?:ql)?://\S+', '[REDACTED_POSTGRES_URL]' -replace '(?i)(password|token|secret|api[_-]?key)=([^\s&]+)', '$1=[REDACTED]'
    $scriptRuffOutput = $scriptRuffOutput -replace '(?i)postgres(?:ql)?://\S+', '[REDACTED_POSTGRES_URL]' -replace '(?i)(password|token|secret|api[_-]?key)=([^\s&]+)', '$1=[REDACTED]'
    $pytestOutput = $pytestOutput -replace '(?i)postgres(?:ql)?://\S+', '[REDACTED_POSTGRES_URL]' -replace '(?i)(password|token|secret|api[_-]?key)=([^\s&]+)', '$1=[REDACTED]'
    $lines = @(
        "# P1 Stage 0 Test Baseline",
        "",
        "- Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
        "- Python: $pythonVersion",
        "- Runtime and dependencies:",
        '```text',
        $pythonDetails,
        '```',
        "- Ruff: $ruffStatus",
        "- SQLite pytest: $pytestStatus",
        "- PostgreSQL integration: not run by this script; use scripts/run_postgres_contracts.py with a dedicated admin URL.",
        "- SQLite isolation: JAYCODE_TEST_SQLITE_PATH pointed to a newly created temporary database.",
        "- Application databases: not connected; .env unchanged.",
        "",
        "## Ruff output",
        "",
        '```text',
        $ruffOutput,
        '```',
        "",
        "## Ruff scripts output",
        "",
        '```text',
        $scriptRuffOutput,
        '```',
        "",
        "## pytest output",
        "",
        '```text',
        $pytestOutput,
        '```',
        ""
    )
    $stream = [System.IO.File]::Open($report, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::Write, [System.IO.FileShare]::None)
    try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        $writer.WriteLine(($lines -join [Environment]::NewLine))
        $writer.Dispose()
    }
    finally { $stream.Dispose() }
}

Write-Output "Ruff: $ruffStatus"
Write-Output "SQLite pytest: $pytestStatus"
Write-Output "Report: $report"
if ($ruffStatus -ne "pass" -or $pytestStatus -notlike "pass*") { exit 1 }
