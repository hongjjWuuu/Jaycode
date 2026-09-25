[CmdletBinding()]
param(
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "..\data\postgres-backups"),
    [ValidateRange(1, 365)]
    [int]$RetentionDays = 14,
    [string]$ContainerName = "dev-agent-studio-pgvector"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-ContainerRunning {
    $running = (& docker inspect --format '{{.State.Running}}' $ContainerName 2>$null).Trim()
    if ($running -ne "true") { throw "PostgreSQL container '$ContainerName' is not running." }
}

function Protect-BackupDirectory([string]$Path) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls $Path /inheritance:r /grant:r "$identity`:(OI)(CI)F" /grant:r "SYSTEM:(OI)(CI)F" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Unable to restrict backup directory permissions." }
}

Assert-ContainerRunning
Protect-BackupDirectory $BackupDirectory
$timestamp = [DateTime]::UtcNow.ToString("yyyyMMddTHHmmssZ")
$fileName = "jayagent_studio-$timestamp.dump"
$backupPath = Join-Path $BackupDirectory $fileName
$manifestPath = "$backupPath.manifest.json"
$containerPath = "/tmp/$fileName"

try {
    # The password remains inside Docker's PostgreSQL container and is never
    # passed as a process argument or written to the manifest.
    & docker exec $ContainerName pg_dump -U postgres -d jayagent_studio -Fc -f $containerPath
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed." }
    & docker exec $ContainerName pg_restore --list $containerPath | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pg_restore validation failed." }
    & docker cp "$ContainerName`:$containerPath" $backupPath
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $backupPath)) { throw "Unable to copy PostgreSQL backup to the protected directory." }
    $hash = (Get-FileHash -LiteralPath $backupPath -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest = [ordered]@{
        format = "jaycode-postgres-backup-v1"
        created_at = [DateTime]::UtcNow.ToString("o")
        database = "jayagent_studio"
        file = $fileName
        bytes = (Get-Item -LiteralPath $backupPath).Length
        sha256 = $hash
        verification = "pg_restore_list_ok"
    }
    $manifest | ConvertTo-Json | Set-Content -LiteralPath $manifestPath -Encoding utf8NoBOM

    $cutoff = [DateTime]::UtcNow.AddDays(-$RetentionDays)
    Get-ChildItem -LiteralPath $BackupDirectory -File -Filter "jayagent_studio-*.dump" | ForEach-Object {
        if ($_.Name -match '^jayagent_studio-(\d{8}T\d{6}Z)\.dump$') {
            $created = [DateTime]::ParseExact($Matches[1], "yyyyMMddTHHmmssZ", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal)
            if ($created -lt $cutoff) {
                Remove-Item -LiteralPath $_.FullName -Force
                Remove-Item -LiteralPath "$($_.FullName).manifest.json" -Force -ErrorAction SilentlyContinue
            }
        }
    }
    Write-Output (@{ backup = $fileName; manifest = (Split-Path -Leaf $manifestPath); sha256 = $hash; retention_days = $RetentionDays } | ConvertTo-Json -Compress)
} finally {
    & docker exec $ContainerName rm -f $containerPath 2>$null
}
