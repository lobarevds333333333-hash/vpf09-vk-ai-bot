param(
    [int]$Port = 8791,
    [int]$IntervalSeconds = 3600
)

$ErrorActionPreference = "Continue"
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
        & (Join-Path $PSScriptRoot "start_proxy.ps1") -Port $Port | Out-Null
        for ($Second = 0; $Second -lt $IntervalSeconds; $Second++) {
            if (Test-Path -LiteralPath $StopFile) {
                break
            }
            Start-Sleep -Seconds 1
        }
    }
}
finally {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
