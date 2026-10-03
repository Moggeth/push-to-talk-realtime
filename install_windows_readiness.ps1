param(
    [string]$Python = (Get-Command pythonw.exe -ErrorAction Stop).Source
)
$ErrorActionPreference = 'Stop'
$taskName = 'PushToTalkRealtime Readiness'
$scriptPath = Join-Path $PSScriptRoot 'start_push_to_talk.py'
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw 'Python executable missing' }
if (-not (Test-Path -LiteralPath $scriptPath -PathType Leaf)) { throw 'Launcher missing' }
$backupDir = Join-Path $env:LOCALAPPDATA ('PushToTalkRealtime\startup-backups\' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) { Export-ScheduledTask -TaskName $taskName | Set-Content -LiteralPath (Join-Path $backupDir 'task.xml') }
$user = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$taskWrapper = Join-Path $PSScriptRoot 'readiness_task.ps1'
if (-not (Test-Path -LiteralPath $taskWrapper -PathType Leaf)) { throw 'Task wrapper missing' }
$windowlessPython = Join-Path (Split-Path -Parent $Python) 'pythonw.exe'
$windowlessWrapper = Join-Path $PSScriptRoot 'readiness_task.pyw'
if (-not (Test-Path -LiteralPath $windowlessPython -PathType Leaf)) { throw 'Windowless Python executable missing' }
if (-not (Test-Path -LiteralPath $windowlessWrapper -PathType Leaf)) { throw 'Windowless task wrapper missing' }
$action = New-ScheduledTaskAction -Execute $windowlessPython -Argument ('"' + $windowlessWrapper + '" --python "' + $Python + '"') -WorkingDirectory $PSScriptRoot
$logon = New-ScheduledTaskTrigger -AtLogOn -User $user
$retry = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($logon,$retry) -Settings $settings -Principal $principal -Description 'Keep push-to-talk ready in the signed-in desktop. Microphone opens only on demand. Disable this task before intentionally stopping the app.' -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State
Write-Output "Startup backup: $backupDir"
