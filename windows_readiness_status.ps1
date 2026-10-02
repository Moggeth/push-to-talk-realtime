$ErrorActionPreference = 'Stop'
$taskName = 'PushToTalkRealtime Readiness'
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName,State | Format-List
Get-ScheduledTaskInfo -TaskName $taskName | Select-Object LastRunTime,LastTaskResult,NextRunTime,NumberOfMissedRuns | Format-List
$launcher = Join-Path $PSScriptRoot 'start_push_to_talk.py'
$app = Join-Path $PSScriptRoot 'push_to_talk_realtime.py'
Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and
    ($_.CommandLine.Contains($launcher) -or $_.CommandLine.Contains($app))
} | Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine | Format-List
$runtime = Join-Path $env:LOCALAPPDATA 'PushToTalkRealtime'
Get-Content -LiteralPath (Join-Path $runtime 'push_to_talk_supervisor.log') -Tail 12 -ErrorAction SilentlyContinue
# Exclude dictated text from diagnostics.
Select-String -LiteralPath (Join-Path $runtime 'push_to_talk_realtime.log') -Pattern 'Push-to-talk ready|\[Startup\]|\[Lifecycle\]|\[Input\]|\[Crash\]' |
    Select-Object -Last 12 | ForEach-Object { $_.Line }
