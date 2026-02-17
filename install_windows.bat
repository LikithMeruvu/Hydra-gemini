@echo off
setlocal
cd /d "%~dp0"

echo ╔═══════════════════════════════════════════════╗
echo ║         ⚡ Hydra One-Click Installer          ║
echo ╚═══════════════════════════════════════════════╝

:: 1. Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python is not installed or not in PATH.
    echo     Please install Python 3.10+ and check "Add to PATH".
    pause
    exit /b 1
)

:: 2. Install Hydra Dependencies
echo.
echo [*] Installing Hydra dependencies...
pip install -e .
if %errorlevel% neq 0 (
    echo [!] Failed to install dependencies.
    pause
    exit /b 1
)

:: 3. Check/Install Redis
echo.
echo [*] Checking for Redis...
tasklist /FI "IMAGENAME eq redis-server.exe" 2>NUL | find /I /N "redis-server.exe">NUL
if "%ERRORLEVEL%"=="0" (
    echo [+] Redis is already running.
) else (
    if exist "redis\redis-server.exe" (
        echo [*] Starting bundled Redis...
        start /min "Hydra Redis" redis\redis-server.exe
    ) else (
        echo [!] Redis not found. Downloading Portable Redis...
        powershell -Command "Invoke-WebRequest -Uri 'https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip' -OutFile 'redis.zip'"
        powershell -Command "Expand-Archive -Path 'redis.zip' -DestinationPath 'redis' -Force"
        del redis.zip
        echo [+] Redis installed to ./redis
        echo [*] Starting Redis...
        start /min "Hydra Redis" redis\redis-server.exe
    )
    :: Wait for Redis to start
    timeout /t 3 >nul
)

:: 4. Run Hydra Setup
echo.
echo [*] Launching Hydra Setup...
python -m hydra setup --file keys.json

echo.
echo [!] Setup Complete!
echo     To start the server, run: start.bat
pause
