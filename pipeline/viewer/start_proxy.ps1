param(
    [int]$Port = 8791
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Python = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
$HealthUrl = "http://127.0.0.1:$Port/health"

function Test-ProxyHealth {
    try {
        $Response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 2
        return $Response.ok -eq $true
    }
    catch {
        return $false
    }
}

if (Test-ProxyHealth) {
    Write-Output "Viewer proxy already healthy"
    exit 0
}

if ([string]::IsNullOrWhiteSpace($env:APIHOST_API_KEY)) {
    Write-Error "APIHOST_API_KEY is not set"
    exit 1
}

if ([string]::IsNullOrWhiteSpace($env:VIEWER_PROXY_TOKEN)) {
    Write-Error "VIEWER_PROXY_TOKEN is not set"
    exit 1
}

if (-not (Test-Path -LiteralPath $Python)) {
    Write-Error "Python environment not found: $Python"
    exit 1
}

$Arguments = @(
    "-m",
    "pipeline.viewer.apihost_responses_proxy",
    "--host",
    "127.0.0.1",
    "--port",
    "$Port"
)
Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $RepositoryRoot -WindowStyle Hidden | Out-Null

for ($Attempt = 0; $Attempt -lt 20; $Attempt++) {
    Start-Sleep -Milliseconds 500
    if (Test-ProxyHealth) {
        Write-Output "Viewer proxy started"
        exit 0
    }
}

Write-Error "Viewer proxy did not become healthy"
exit 1
