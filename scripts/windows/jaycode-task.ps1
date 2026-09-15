param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('install', 'status', 'uninstall')]
    [string]$Action,
    [string]$TaskName = 'Jaycode API and Worker'
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

switch ($Action) {
    'install' {
        if (-not (Test-Path -LiteralPath $Python)) {
            throw "Project Python was not found: $Python"
        }
        $Arguments = '-m uvicorn app.main:app --host 127.0.0.1 --port 8100'
        $TaskAction = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $ProjectRoot
        $Trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
        $Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
        $Principal = New-ScheduledTaskPrincipal -UserId $env:USERDOMAIN\$env:USERNAME -LogonType Interactive -RunLevel Limited
        Register-ScheduledTask -TaskName $TaskName -Action $TaskAction -Trigger $Trigger -Settings $Settings -Principal $Principal -Description 'Starts Jaycode API; the API process supervises configured local task workers.' -Force | Out-Null
        Write-Output "Registered '$TaskName'. Configure JAYCODE_WORKER_SUPERVISOR_ENABLED=true in the project .env before starting it."
    }
    'status' {
        Get-ScheduledTask -TaskName $TaskName | Get-ScheduledTaskInfo
    }
    'uninstall' {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Unregistered '$TaskName'. Project files and databases were not changed."
    }
}
