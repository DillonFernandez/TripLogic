$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendRoot = Join-Path $projectRoot "backend"
$python = Join-Path $backendRoot ".venv\Scripts\python.exe"
$adb = Join-Path $env:LOCALAPPDATA "Android\Sdk\platform-tools\adb.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment was not found: $python"
}

if (-not (Test-Path $adb)) {
    throw "ADB was not found: $adb"
}

$backendRunning = Test-NetConnection `
    -ComputerName 127.0.0.1 `
    -Port 8000 `
    -InformationLevel Quiet `
    -WarningAction SilentlyContinue

if (-not $backendRunning) {
    Start-Process powershell.exe -ArgumentList @(
        "-NoExit",
        "-ExecutionPolicy", "Bypass",
        "-Command",
        "Set-Location '$backendRoot'; & '$python' -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level debug"
    )

    Write-Host "Waiting for FastAPI..." -ForegroundColor Cyan

    $backendReady = $false

    for ($attempt = 1; $attempt -le 30; $attempt++) {
        Start-Sleep -Seconds 1

        $backendReady = Test-NetConnection `
            -ComputerName 127.0.0.1 `
            -Port 8000 `
            -InformationLevel Quiet `
            -WarningAction SilentlyContinue

        if ($backendReady) {
            break
        }
    }

    if (-not $backendReady) {
        throw "FastAPI did not start on port 8000."
    }
}

& $adb reverse tcp:8000 tcp:8000

if ($LASTEXITCODE -ne 0) {
    throw "ADB port forwarding failed. Confirm that the phone is connected."
}

Set-Location $projectRoot

flutter run --dart-define=API_BASE_URL=http://127.0.0.1:8000

