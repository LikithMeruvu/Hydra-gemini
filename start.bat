@echo off
cd /d "%~dp0"

:: Check for bundled Redis and start if not running
tasklist /FI "IMAGENAME eq redis-server.exe" 2>NUL | find /I /N "redis-server.exe">NUL
if "%ERRORLEVEL%"=="1" (
    if exist "redis\redis-server.exe" (
        echo [*] Starting bundled Redis...
        start /min "Hydra Redis" redis\redis-server.exe
        timeout /t 2 >nul
    )
)

echo [*] Starting Hydra Gateway...
python -m hydra gateway
