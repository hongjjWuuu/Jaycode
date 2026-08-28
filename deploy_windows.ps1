param(
    [switch]$InstallOnly,
    [switch]$RunOnly
)

$ErrorActionPreference = "Stop"

function Assert-Python313 {
    $versionOutput = & py -3.13 -c "import sys; print(sys.version)"
    if (-not $versionOutput) {
        throw "Python 3.13 was not found. Please install Python 3.13 and make sure the `py` launcher can reach it."
    }
}

function Invoke-JaycodeInstall {
    Write-Host "Installing Jaycode..." -ForegroundColor Cyan
    & py -3.13 -m pip install -e . --no-build-isolation
}

function Invoke-JaycodeRun {
    Write-Host "Starting Jaycode..." -ForegroundColor Cyan
    & py -3.13 -m jaycode
}

Assert-Python313

if ($RunOnly) {
    Invoke-JaycodeRun
    exit 0
}

Invoke-JaycodeInstall

if (-not $InstallOnly) {
    Write-Host ""
    Invoke-JaycodeRun
}
