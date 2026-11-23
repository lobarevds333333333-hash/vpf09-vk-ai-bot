param(
    [int]$Port = 8791
)

$ErrorActionPreference = "Continue"
$IntervalSeconds = 30
$StopFile = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".codex\viewer-watchdog.stop"
$Mutex = New-Object System.Threading.Mutex($false, "Local\CodexApiHostProxyWatchdog")
if (-not $Mutex.WaitOne(0)) {
    exit 0
}

try {
    while ($true) {
        if (Test-Path -LiteralPath $StopFile) {
            Remove-Item -LiteralPath $StopFile -Force
            break
        }
        $Cycle = [System.Diagnostics.Stopwatch]::StartNew()
        & (Join-Path $PSScriptRoot "start_proxy.ps1") -Port $Port | Out-Null
        while ($Cycle.Elapsed.TotalSeconds -lt $IntervalSeconds) {
            if (Test-Path -LiteralPath $StopFile) {
                break
            }
            $Remaining = $IntervalSeconds - $Cycle.Elapsed.TotalSeconds
            $DelayMilliseconds = [int]([Math]::Max(50, [Math]::Min(1000, $Remaining * 1000)))
            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }
}
finally {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
