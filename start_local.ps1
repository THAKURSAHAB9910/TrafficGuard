# TrafficGuard PowerShell Local Launcher
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  TrafficGuard — Adaptive Traffic Management Platform" -ForegroundColor Cyan
Write-Host "  Starting local development environment..." -ForegroundColor Cyan
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Verify Python
try {
    $pyVer = python --version
    Write-Host "[OK] Python detected: $pyVer" -ForegroundColor Green
} catch {
    Write-Error "[ERROR] Python is not installed or not in PATH."
    exit 1
}

# Verify npm
try {
    $npmVer = cmd /c npm --version
    Write-Host "[OK] npm detected: $npmVer" -ForegroundColor Green
} catch {
    Write-Error "[ERROR] Node.js / npm is not installed or not in PATH."
    exit 1
}

# Ensure dashboard dependencies
if (-not (Test-Path "dashboard\node_modules")) {
    Write-Host "[SETUP] Installing dashboard node_modules..." -ForegroundColor Yellow
    Push-Location dashboard
    cmd /c npm install
    Pop-Location
}

Write-Host "`nStarting all services: Backends, Gateway, and Vite UI..." -ForegroundColor Cyan
python run_local.py
