@echo off
setlocal
cd /d "%~dp0"
set retries=0

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
        
        :: Download with TLS 1.2 enforcement
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/tporadowski/redis/releases/download/v5.0.14.1/Redis-x64-5.0.14.1.zip' -OutFile 'redis.zip'"
        
        if not exist "redis.zip" (
            echo [!] Failed to download Redis! Check your internet connection.
            pause
            exit /b 1
        )

        echo [*] Extracting Redis...
        powershell -Command "Expand-Archive -Path 'redis.zip' -DestinationPath 'redis' -Force"
        
        if not exist "redis\redis-server.exe" (
            echo [!] Failed to extract Redis!
            pause
            exit /b 1
        )

        del redis.zip
        echo [+] Redis installed to ./redis
        echo [*] Starting Redis...
        start /min "Hydra Redis" redis\redis-server.exe
    )
    
    :: Wait and Check for Port 6379
    echo [*] Waiting for Redis to start...
    :wait_loop
    timeout /t 1 >nul
    netstat -an | find "6379" | find "LISTENING" >nul
    if %errorlevel% equ 0 goto redis_up
    set /a retries+=1
    if %retries% geq 10 goto redis_fail
    goto wait_loop

    :redis_fail
    echo [!] Redis failed to start!
    echo     Please check if 'redis\redis-server.exe' works manually.
    pause
    exit /b 1

    :redis_up
    echo [+] Redis is listening!
)

:: 4. Run Hydra Setup
echo.
echo [*] Launching Hydra Setup...
python -m hydra setup --file keys.json

echo.
echo [!] Setup Complete!
echo     To start the server, run: start.bat
pause
