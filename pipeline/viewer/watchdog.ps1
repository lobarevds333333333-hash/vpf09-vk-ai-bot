param(
    [int]$Port = 8791,
    [int]$IntervalSeconds = 30
)

$ErrorActionPreference = "Continue"
$Mutex = New-Object System.Threading.Mutex($false, "Local\CodexApiHostProxyWatchdog")
if (-not $Mutex.WaitOne(0)) {
    exit 0
}

try {
    while ($true) {
        & (Join-Path $PSScriptRoot "start_proxy.ps1") -Port $Port | Out-Null
        Start-Sleep -Seconds $IntervalSeconds
    }
}
finally {
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}
