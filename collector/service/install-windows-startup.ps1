param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$Distribution,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+$')]
    [string]$LinuxUser,
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^/[A-Za-z0-9_./-]+$')]
    [string]$RepositoryPath
)

$ErrorActionPreference = 'Stop'
$taskName = 'Vid2Idea Collector'
$executable = Join-Path $env:WINDIR 'System32\wsl.exe'
# Validated arguments contain no whitespace or shell syntax. In this Windows
# task environment, quoting the distro name makes WSL look for a literal quote.
$arguments = '--distribution {0} --user {1} --exec /bin/sh {2}/collector/service/keep-wsl-running.sh' -f $Distribution, $LinuxUser, $RepositoryPath.TrimEnd('/')
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($existing) {
    if ($existing.Actions.Count -ne 1 -or $existing.Actions[0].Execute -ne $executable -or $existing.Actions[0].Arguments -ne $arguments) {
        throw 'A different Vid2Idea Collector task already exists. It was left unchanged.'
    }
} else {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $executable -Argument $arguments -WorkingDirectory $env:USERPROFILE
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
    $principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Runs the local read-only Discord idea collector while signed into Windows.' | Out-Null
}

if ((Get-ScheduledTask -TaskName $taskName).State -ne 'Running') {
    Start-ScheduledTask -TaskName $taskName
}
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State | ConvertTo-Json -Compress
