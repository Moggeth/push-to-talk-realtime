param(
    [Parameter(Mandatory=$true)][string]$Python,
    [string]$Launcher = '',
    [string]$DiagnosticsDirectory = (Join-Path $env:LOCALAPPDATA 'PushToTalkRealtime\diagnostics')
)
$ErrorActionPreference = 'Stop'
if (-not $Launcher) { $Launcher = Join-Path $PSScriptRoot 'start_push_to_talk.py' }
$runId = [guid]::NewGuid().ToString('N')
$clock = [Diagnostics.Stopwatch]::StartNew()
$phase = 'initializing'
function Write-TaskEvent([string]$Event, [hashtable]$Fields) {
    try {
        New-Item -ItemType Directory -Path $DiagnosticsDirectory -Force | Out-Null
        $log = Join-Path $DiagnosticsDirectory 'task.events.jsonl'
        if ((Test-Path -LiteralPath $log) -and (Get-Item -LiteralPath $log).Length -ge 4194304) {
            for ($index=3; $index -ge 1; $index--) {
                $old = "$log.$index"
                if (Test-Path -LiteralPath $old) { Move-Item -LiteralPath $old -Destination "$log.$($index+1)" -Force }
            }
            Move-Item -LiteralPath $log -Destination "$log.1" -Force
        }
        $record = @{schema=1;utc=[DateTime]::UtcNow.ToString('o');epoch=([DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0);elapsed_s=$clock.Elapsed.TotalSeconds;component='task';run_id=$runId;pid=$PID;event=$Event;phase=$phase}
        foreach ($key in @('child_pid','exit_code','exception_type','error_line','reason','launcher_present','python_present','launcher_sha256')) {
            if ($Fields.ContainsKey($key)) { $record[$key]=$Fields[$key] }
        }
        $record | ConvertTo-Json -Compress | Add-Content -LiteralPath $log -Encoding utf8
    } catch { [Console]::Error.WriteLine('Push-to-talk task diagnostics unavailable') }
}
try {
    $phase='validate_paths'
    $pythonPresent=Test-Path -LiteralPath $Python -PathType Leaf
    $launcherPresent=Test-Path -LiteralPath $Launcher -PathType Leaf
    Write-TaskEvent 'task_started' @{python_present=$pythonPresent;launcher_present=$launcherPresent}
    if (-not $pythonPresent -or -not $launcherPresent) {
        Write-TaskEvent 'cold_start_failed' @{reason='missing_executable_or_launcher'}
        exit 1
    }
    $phase='start_python'
    $hasher=[Security.Cryptography.SHA256]::Create()
    try { $launcherHash=[BitConverter]::ToString($hasher.ComputeHash([IO.File]::ReadAllBytes($Launcher))).Replace('-','').ToLowerInvariant() } finally { $hasher.Dispose() }
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName=$Python
    $info.Arguments='"'+$Launcher+'" --supervise --ptt-only --launch-source scheduled_task'
    $info.WorkingDirectory=$PSScriptRoot
    $info.UseShellExecute=$false
    $info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true
    $info.RedirectStandardError=$true
    $info.EnvironmentVariables['PUSH_TO_TALK_TASK_RUN_ID']=$runId
    $info.EnvironmentVariables['PUSH_TO_TALK_DIAGNOSTICS_DIR']=$DiagnosticsDirectory
    $process=[Diagnostics.Process]::Start($info)
    $stdoutDrain=$process.StandardOutput.BaseStream.CopyToAsync([IO.Stream]::Null)
    $stderrDrain=$process.StandardError.BaseStream.CopyToAsync([IO.Stream]::Null)
    Write-TaskEvent 'python_started' @{child_pid=$process.Id;launcher_sha256=$launcherHash}
    $phase='wait_python'
    $process.WaitForExit()
    $stdoutDrain.Wait()
    $stderrDrain.Wait()
    $code=$process.ExitCode
    Write-TaskEvent 'python_exited' @{child_pid=$process.Id;exit_code=$code}
    exit $code
} catch {
    Write-TaskEvent 'task_failed' @{exception_type=$_.Exception.GetType().FullName;error_line=$_.InvocationInfo.ScriptLineNumber}
    exit 1
}
