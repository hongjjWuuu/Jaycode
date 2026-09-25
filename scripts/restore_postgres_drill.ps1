[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [string]$BackupFile,
    [Parameter(Mandatory)]
    [string]$AdminUrl,
    [string]$ContainerName = "dev-agent-studio-pgvector"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LoopbackAdminUrl([string]$Value) {
    $uri = [Uri]$Value
    if ($uri.Scheme -notin @("postgresql", "postgres") -or $uri.Host -notin @("127.0.0.1", "localhost") -or $uri.Port -ne 5432 -or $uri.AbsolutePath.Trim("/") -ne "postgres") {
        throw "AdminUrl must target loopback PostgreSQL database 'postgres' on port 5432."
    }
}

if (-not (Test-Path -LiteralPath $BackupFile -PathType Leaf)) { throw "BackupFile does not exist." }
Assert-LoopbackAdminUrl $AdminUrl
$running = (& docker inspect --format '{{.State.Running}}' $ContainerName 2>$null).Trim()
if ($running -ne "true") { throw "PostgreSQL container '$ContainerName' is not running." }

$drillDatabase = "jaycode_restore_test_$([Guid]::NewGuid().ToString('N'))"
$containerBackup = "/tmp/$([IO.Path]::GetFileName($BackupFile))"
$created = $false
try {
    & docker cp $BackupFile "$ContainerName`:$containerBackup"
    if ($LASTEXITCODE -ne 0) { throw "Unable to copy backup into the PostgreSQL container." }
    & docker exec $ContainerName pg_restore --list $containerBackup | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Backup validation failed." }
    & docker exec $ContainerName createdb -U postgres $drillDatabase
    if ($LASTEXITCODE -ne 0) { throw "Unable to create isolated restore drill database." }
    $created = $true
    & docker exec $ContainerName pg_restore -U postgres --exit-on-error -d $drillDatabase $containerBackup
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed." }
    $tableCount = (& docker exec $ContainerName psql -U postgres -d $drillDatabase -Atqc "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public';").Trim()
    if ([int]$tableCount -lt 35) { throw "Restore drill found fewer than the expected application tables." }
    Write-Output (@{ database = $drillDatabase; tables = [int]$tableCount; status = "restore_drill_ok" } | ConvertTo-Json -Compress)
} finally {
    if ($created -and $drillDatabase -match '^jaycode_restore_test_[0-9a-f]{32}$') {
        & docker exec $ContainerName dropdb -U postgres --if-exists $drillDatabase 2>$null
    }
    & docker exec $ContainerName rm -f $containerBackup 2>$null
}
