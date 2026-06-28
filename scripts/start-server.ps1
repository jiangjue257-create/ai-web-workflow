$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Log = Join-Path $ProjectRoot "uvicorn.log"
$ErrLog = Join-Path $ProjectRoot "uvicorn.err.log"

if (-not (Test-Path $Python)) {
    throw "Python was not found at $Python. Install project dependencies first."
}

$existing = @(Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)
if ($existing.Count -gt 0) {
    Write-Host "Port 8765 is already in use:"
    $existing | Select-Object OwningProcess, LocalAddress, LocalPort, State | Format-Table
    Write-Host "If the page is not using the latest code, stop the old process or restart Windows, then run this script again."
    exit 0
}

Start-Process `
    -FilePath $Python `
    -ArgumentList "-m uvicorn app.main:app --host 127.0.0.1 --port 8765" `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $Log `
    -RedirectStandardError $ErrLog `
    -WindowStyle Hidden

Start-Sleep -Seconds 2

try {
    $response = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8765/" -TimeoutSec 5
    Write-Host "Server started: http://127.0.0.1:8765"
    Write-Host "HTTP status: $($response.StatusCode)"
} catch {
    Write-Host "Start command ran, but home page check failed. See:"
    Write-Host $ErrLog
    throw
}

