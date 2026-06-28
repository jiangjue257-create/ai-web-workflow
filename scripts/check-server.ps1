$ErrorActionPreference = "Stop"

$listeners = @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -eq 0) {
    Write-Host "No service is listening on 127.0.0.1:8765."
    Write-Host "Run: .\scripts\start-server.ps1"
    exit 1
}

Write-Host "Port listeners:"
$listeners | Select-Object OwningProcess, LocalAddress, LocalPort, State | Format-Table

try {
    $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8765/" -TimeoutSec 5
    Write-Host "Home HTTP status: $($response.StatusCode)"
    Write-Host "Contains AI Web Workflow: $($response.Content -match 'AI Web Workflow')"
} catch {
    Write-Host "Port exists, but home page check failed: $($_.Exception.Message)"
    exit 1
}

