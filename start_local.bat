@echo off
title TrafficGuard - Local Development Stack
echo ================================================================
echo   TrafficGuard — Adaptive Traffic Management Platform
echo   Launching local development environment...
echo ================================================================
echo.

:: Check python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not found in PATH. Please install Python 3.11+.
    pause
    exit /b 1
)

:: Check node/npm
cmd /c npm --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js / npm is not found in PATH. Please install Node.js 18+.
    pause
    exit /b 1
)

:: Ensure frontend dependencies are installed
if not exist "dashboard\node_modules" (
    echo [SETUP] Installing dashboard frontend dependencies...
    cd dashboard && cmd /c npm install && cd ..
)

echo [START] Launching 3 Upstream Backends, API Gateway, and Vite Dashboard...
echo [INFO]  Frontend UI will be accessible at: http://localhost:5173
echo [INFO]  API Gateway will be accessible at:  http://localhost:8000
echo.

python run_local.py
pause
