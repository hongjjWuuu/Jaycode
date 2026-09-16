param(
    [string]$ReportPath,
    [string]$GitHubRunId
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Project virtualenv Python was not found."
}

if (-not $ReportPath) {
    $ReportPath = "artifacts/quality-gates/stage5-$(Get-Date -Format 'yyyyMMdd-HHmmss').md"
}
$report = Join-Path $repoRoot $ReportPath
if (Test-Path -LiteralPath $report) {
    throw "Report already exists; refusing to overwrite: $report"
}
$sqliteReport = Join-Path $repoRoot ("artifacts/quality-gates/stage5-sqlite-$(Get-Date -Format 'yyyyMMdd-HHmmss').md")
$results = [System.Collections.Generic.List[object]]::new()

function Redact-Output([string]$Text) {
    $value = $Text -replace '(?i)postgres(?:ql)?://[^\s''"]+', '[REDACTED_POSTGRES_URL]'
    return $value -replace '(?i)(password|pwd|token|secret|api[_-]?key)=([^\s&]+)', '$1=[REDACTED]'
}

function Invoke-Gate([string]$Name, [scriptblock]$Action) {
    $raw = ""
    $code = 1
    $previousErrorAction = $ErrorActionPreference
    try {
        # npm emits informational notices on stderr.  Capture them as gate output
        # instead of allowing PowerShell to stop before the actual failure appears.
        $ErrorActionPreference = "Continue"
        $raw = (& $Action 2>&1 | Out-String).Trim()
        $code = $LASTEXITCODE
        if ($null -eq $code) { $code = 0 }
    }
    catch {
        $raw = "$raw`n$($_.Exception.Message)".Trim()
        $code = 1
    }
    finally {
        $ErrorActionPreference = $previousErrorAction
    }
    $status = if ($code -ne 0) { "fail" } elseif ($raw -match '(?im)\b\d+\s+skipped\b|\bSKIPPED\b') { "skip" } else { "pass" }
    $results.Add([pscustomobject]@{ Name = $Name; Status = $status; ExitCode = $code; Output = (Redact-Output $raw) })
}

Push-Location $repoRoot
try {
    Invoke-Gate "SQLite Ruff and pytest isolation" {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repoRoot "scripts\run_isolated_baseline.ps1") -ReportPath $sqliteReport
    }
    Invoke-Gate "PostgreSQL Store, E2E and migration rehearsal" {
        & $python (Join-Path $repoRoot "scripts\run_postgres_contracts.py")
    }
    Invoke-Gate "P0 security and legacy marker regression" {
        & $python -m pytest -q tests/test_p0_security.py tests/test_cleanup_regressions.py
    }
    Invoke-Gate "RAG Gold Set baseline" {
        $goldResult = Join-Path $repoRoot "artifacts\quality-gates\rag-gold-stage5.json"
        & $python -m app.benchmark_runner --type rag-gold --output $goldResult
        if ($LASTEXITCODE -eq 0) { & $python scripts/check_rag_gold_baseline.py $goldResult }
    }
    Invoke-Gate "Worker 100 tasks / 2 workers" {
        & $python scripts/worker_load_test.py --tasks 100 --workers 2
    }
    Invoke-Gate "Frontend TypeScript and Vite build" {
        Push-Location (Join-Path $repoRoot "web")
        try {
            & npm ci
            if ($LASTEXITCODE -eq 0) { & npm run build }
        }
        finally { Pop-Location }
    }
    Invoke-Gate "Python dependency audit" { & $python -m pip_audit }
    Invoke-Gate "Frontend dependency audit" {
        Push-Location (Join-Path $repoRoot "web")
        try { & npm audit --omit=dev --audit-level=high }
        finally { Pop-Location }
    }
    Invoke-Gate "GitHub Actions quality and PostgreSQL jobs" {
        if (-not $GitHubRunId) { throw "GitHubRunId is required; local checks alone cannot approve stage six." }
        $run = (& gh run view $GitHubRunId --json status,conclusion,jobs | ConvertFrom-Json)
        $required = @("quality", "postgres-store")
        $completed = $run.status -eq "completed" -and $run.conclusion -eq "success"
        $jobs = @($run.jobs | Where-Object { $_.name -in $required })
        if (-not $completed -or $jobs.Count -ne $required.Count -or ($jobs | Where-Object { $_.conclusion -ne "success" })) {
            throw "GitHub run does not contain successful quality and postgres-store jobs."
        }
        "GitHub workflow run $GitHubRunId passed required jobs."
    }
}
finally {
    Pop-Location
}

$revision = "unavailable"
try { $revision = (& git -C $repoRoot rev-parse HEAD 2>$null | Out-String).Trim() } catch {}
$lines = @(
    "# Jaycode P1 Stage 5 Quality Gates",
    "",
    "- Timestamp: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
    "- Revision: $revision",
    "- SQLite baseline report: $sqliteReport",
    '- PostgreSQL tests use only a runner-created `jaycode_test_*` database.',
    "- Any fail, skip, or not-run gate blocks stage six.",
    ""
)
foreach ($result in $results) {
    $lines += "## $($result.Name) — $($result.Status) (exit $($result.ExitCode))"
    $lines += ""
    $lines += '```text'
    $lines += $result.Output
    $lines += '```'
    $lines += ""
}
$reportDirectory = Split-Path -Parent $report
New-Item -ItemType Directory -Path $reportDirectory -Force | Out-Null
[System.IO.File]::WriteAllText($report, ($lines -join [Environment]::NewLine), [System.Text.UTF8Encoding]::new($false))
Write-Output "Stage 5 report: $report"
if ($results | Where-Object { $_.Status -ne "pass" }) { exit 1 }
