[CmdletBinding()]
param(
    [ValidateSet("register", "status", "unregister")]
    [string]$Action = "status",
    [string]$TaskName = "Jaycode PostgreSQL Daily Backup"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$backupScript = Join-Path $repoRoot "scripts\backup_postgres.ps1"

switch ($Action) {
    "register" {
        $scheduledAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$backupScript`""
        $trigger = New-ScheduledTaskTrigger -Daily -At 3:15AM
        $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $scheduledAction -Trigger $trigger -Principal $principal -Description "Creates and verifies a protected Jaycode PostgreSQL backup." -Force | Out-Null
        Write-Output "Registered '$TaskName'."
    }
    "status" { Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }
    "unregister" { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
}
