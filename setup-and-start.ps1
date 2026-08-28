$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $Root ".env"
$EnvExample = Join-Path $Root ".env.example"
$PythonDir = Join-Path $Root ".python"
$PythonExe = Join-Path $PythonDir "tools\python.exe"
$VenvDir = Join-Path $Root ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$InstallerDir = Join-Path $Root ".cache"
$NugetZip = Join-Path $InstallerDir "python-3.13.5-nuget.zip"
$PythonUrl = "https://www.nuget.org/api/v2/package/python/3.13.5"
$RequiredEnvKeys = @(
    "APP_NAME",
    "APP_ENV",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "JAYCODE_AGENT_LLM",
    "JAYCODE_MEMORY_EXTRACTOR",
    "JAYCODE_RAG_STORE",
    "JAYCODE_MCP_PROVIDER",
    "JAYCODE_SKILL_SANDBOX"
)

Write-Host "== Jaycode setup =="
Write-Host "Project: $Root"

if (!(Test-Path $EnvFile)) {
    if (!(Test-Path $EnvExample)) {
        throw "Missing environment template: $EnvExample"
    }
    Copy-Item -LiteralPath $EnvExample -Destination $EnvFile
    Write-Host "Created .env from .env.example. Set OPENAI_API_KEY before LLM operations."
}

function Get-EnvValue([string]$Path, [string]$Key) {
    if (!(Test-Path $Path)) { return $null }
    $line = Get-Content -LiteralPath $Path | Where-Object { $_ -match "^\s*$([regex]::Escape($Key))\s*=" } | Select-Object -First 1
    if (-not $line) { return $null }
    return ($line -replace "^\s*[^=]+\s*=\s*", "").Trim()
}

$MissingEnv = @()
foreach ($key in $RequiredEnvKeys) {
    $value = Get-EnvValue -Path $EnvFile -Key $key
    if ([string]::IsNullOrWhiteSpace($value)) {
        $MissingEnv += $key
    }
}
if ($MissingEnv.Count -gt 0) {
    Write-Host "Missing or empty required .env values:"
    $MissingEnv | ForEach-Object { Write-Host " - $_" }
    if ($MissingEnv -contains "OPENAI_API_KEY") {
        Write-Host "Use sk-XXX as the placeholder or your real API key."
    }
    throw "Please complete the required .env values before starting Jaycode."
}

if (!(Test-Path $PythonExe)) {
    Write-Host "Installing portable Python 3.13.5 into project..."
    New-Item -ItemType Directory -Force -Path $InstallerDir | Out-Null
    if (Test-Path $PythonDir) {
        Remove-Item -LiteralPath $PythonDir -Recurse -Force
    }
    if (!(Test-Path $NugetZip)) {
        Write-Host "Downloading Python NuGet package..."
        Invoke-WebRequest -Uri $PythonUrl -OutFile $NugetZip
    }
    New-Item -ItemType Directory -Force -Path $PythonDir | Out-Null
    Expand-Archive -LiteralPath $NugetZip -DestinationPath $PythonDir -Force
}

if (!(Test-Path $PythonExe)) {
    throw "Portable Python install failed: $PythonExe not found"
}

Write-Host "Python:"
& $PythonExe -V

if (Test-Path $VenvDir) {
    Write-Host "Removing broken .venv..."
    Remove-Item -LiteralPath $VenvDir -Recurse -Force
}

Write-Host "Creating .venv..."
& $PythonExe -m venv $VenvDir

Write-Host "Installing Python dependencies..."
& $VenvPython -m pip install --upgrade pip setuptools wheel
& $VenvPython -m pip install -e .

Write-Host "Building frontend..."
Push-Location (Join-Path $Root "web")
try {
    if (!(Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js is required to build the frontend. Install Node.js 18+ and rerun this script."
    }
    if (!(Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm is required to build the frontend. Install Node.js 18+ and rerun this script."
    }
    if (Test-Path "package-lock.json") {
        npm ci --no-audit --no-fund
    } else {
        npm install --no-audit --no-fund
    }
    npm run build
    $WebIndex = Join-Path (Get-Location) "dist\index.html"
    if (!(Test-Path -LiteralPath $WebIndex)) {
        throw "Frontend build completed without web\dist\index.html. Backend startup was blocked."
    }
} finally {
    Pop-Location
}

Write-Host "Writing start-all.cmd..."
$StartCmd = @"
@echo off
cd /d "%~dp0"
echo Starting Jaycode at http://127.0.0.1:8100/
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8100
"@
Set-Content -Path (Join-Path $Root "start-all.cmd") -Value $StartCmd -Encoding ASCII

Write-Host "Writing start-web.cmd..."
$WebStartCmd = @"
@echo off
cd /d "%~dp0web"
where npm >nul 2>nul
if errorlevel 1 (
  echo npm was not found. Install Node.js 18+ first.
  exit /b 1
)
npm run dev -- --host 127.0.0.1 --port 5173
"@
Set-Content -Path (Join-Path $Root "start-web.cmd") -Value $WebStartCmd -Encoding ASCII

Write-Host "Starting backend..."
Start-Process -FilePath (Join-Path $Root "start-all.cmd") -WorkingDirectory $Root
Write-Host "Done. Open http://127.0.0.1:8100/"
