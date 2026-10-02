param([string]$Python = (Get-Command python.exe -ErrorAction Stop).Source, [string]$ManagerLog = '')
$ErrorActionPreference = 'Stop'
$report = @{schema=1;utc=[DateTime]::UtcNow.ToString('o');limits=@('No audio, transcript, clipboard, environment values, command lines or raw Windows event messages included','Listener thread alive is not proof that a physical key works','Health snapshots are not a safe-to-restart lease')}
$task=Get-ScheduledTask -TaskName 'PushToTalkRealtime Readiness' -ErrorAction SilentlyContinue
if ($task) {
    $info=Get-ScheduledTaskInfo -TaskName $task.TaskName
    $report.task=@{state=[string]$task.State;last_run=$info.LastRunTime.ToUniversalTime().ToString('o');last_result=$info.LastTaskResult;next_run=$info.NextRunTime.ToUniversalTime().ToString('o');missed_runs=$info.NumberOfMissedRuns;interactive=([string]$task.Principal.LogonType -eq 'Interactive');limited=([string]$task.Principal.RunLevel -eq 'Limited')}
}
$launcher=Join-Path $PSScriptRoot 'start_push_to_talk.py'
$report.processes=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains($launcher)} | ForEach-Object {@{pid=$_.ProcessId;ppid=$_.ParentProcessId;created_utc=$_.CreationDate.ToUniversalTime().ToString('o');role=$(if($_.CommandLine -match '--supervise'){'supervisor'}else{'app'})}})
$report.diagnostics=(& $Python (Join-Path $PSScriptRoot 'diagnostic_report.py') | Out-String | ConvertFrom-Json)
$eventEvidence=@()
foreach ($log in @('Application','System','Microsoft-Windows-TaskScheduler/Operational')) {
    try {
        $metadata=Get-WinEvent -ListLog $log -ErrorAction Stop
        $report[($log -replace '[^A-Za-z]','')+'_enabled']=$metadata.IsEnabled
        if (-not $metadata.IsEnabled) {continue}
        $ids=if($log -eq 'Application'){@(1000,1001)}elseif($log -eq 'System'){@(41,6005,6006,6008)}else{@(100,101,102,107,129,200,201,203,322)}
        Get-WinEvent -FilterHashtable @{LogName=$log;Id=$ids;StartTime=(Get-Date).AddDays(-7)} -MaxEvents 500 -ErrorAction SilentlyContinue | ForEach-Object {
            $xml=[xml]$_.ToXml()
            $data=@{}
            foreach($node in $xml.Event.EventData.Data){if($node.Name){$data[[string]$node.Name]=[string]$node.'#text'}}
            $include=($log -eq 'System') -or ($log -eq 'Application' -and $data.AppName -match '^pythonw?\.exe$') -or ($log -like '*TaskScheduler*' -and $data.TaskName -eq '\PushToTalkRealtime Readiness')
            if($include){
                $event=@{utc=$_.TimeCreated.ToUniversalTime().ToString('o');event_id=$_.Id;log=$log;record_id=$_.RecordId}
                foreach($key in @('ProcessId','ProcessID','ResultCode','ErrorValue','ExceptionCode')){if($data[$key] -match '^(0x)?[0-9a-fA-F]{1,16}$'){$event[$key]=$data[$key]}}
                $eventEvidence+=$event
            }
        }
    } catch {$report[($log -replace '[^A-Za-z]','')+'_unavailable']=$true}
}
$report.windows_events=$eventEvidence
if (-not $ManagerLog) { $ManagerLog=Join-Path (Split-Path $PSScriptRoot) 'personal_startup_manager\personal_package_manager\logs\push_to_talk.log' }
$managerEvents=@()
if(Test-Path -LiteralPath $ManagerLog){
    Get-Content -LiteralPath $ManagerLog -Tail 2000 | ForEach-Object {
        if($_ -match '^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] (Status ->|Exited|Clean exit|Launch requested|Launch skipped|Start failed|Start exception|Stopped|Dependency check failed)'){
            $record=@{local_time=$Matches[1];event_kind=$Matches[2].Trim();component='legacy_manager'}
            if($_ -match '(?:code |code=)(-?\d+)'){$record.exit_code=[long]$Matches[1]}
            if($_ -match 'PID (\d+)'){$record.pid=[long]$Matches[1]}
            $managerEvents+=$record
        }
    }
}
$report.manager_events=@($managerEvents | Select-Object -Last 25)
$report | ConvertTo-Json -Depth 12
