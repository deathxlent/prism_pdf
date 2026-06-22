@echo off
REM ============================================================
REM Prism PDF - Start All Services
REM Starts llama.cpp OCR service and main service
REM ============================================================

setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================
echo   Prism PDF - Start All Services
echo ============================================
echo.

REM ============================================================
REM Check virtual environment
REM ============================================================

set "VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
set "VENV_ACTIVATE=%SCRIPT_DIR%venv\Scripts\activate.bat"

if not exist "%VENV_PYTHON%" (
    echo [ERROR] Python virtual environment not found
    echo.
    echo Please run setup first:
    echo   powershell -ExecutionPolicy Bypass -File .\setup.ps1
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM Check if OCR service is already running
REM ============================================================

echo [Check] Checking port usage...

netstat -ano | findstr ":8080" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] Port 8080 is in use, skipping OCR service start
    echo        If OCR service is not working properly, please check manually
    set "SKIP_OCR=1"
) else (
    set "SKIP_OCR=0"
)

netstat -ano | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [WARN] Port 8000 is in use, main service may already be running
)
echo.

REM ============================================================
REM Start OCR service
REM ============================================================

if "%SKIP_OCR%"=="0" (
    echo [1/2] Starting llama.cpp OCR service...
    start "Prism PDF - OCR Service" cmd /k "cd /d "%SCRIPT_DIR%" && start_llama_server.bat"
    echo       OCR service window started
    echo.
    echo       Waiting for OCR service to initialize (15 seconds)...
    timeout /t 15 /nobreak >nul
    echo.
) else (
    echo [1/2] Skipping OCR service start (port already in use)
    echo.
)

REM ============================================================
REM Start main service
REM ============================================================

echo [2/2] Starting Prism PDF main service...
echo.
echo       Service info:
echo         - Main service: http://localhost:8000
echo         - OCR service:  http://localhost:8080
echo         - Virtual env:  %SCRIPT_DIR%venv
echo.
echo       Press Ctrl+C to stop main service (OCR service must be closed manually)
echo.
echo ============================================
echo.

REM Activate virtual environment and start main service
if exist "%VENV_ACTIVATE%" (
    call "%VENV_ACTIVATE%"
)

"%VENV_PYTHON%" -m backend.main

echo.
echo ============================================
echo   Main service stopped
echo ============================================
echo.
echo NOTE: OCR service window may still be running, please close it manually
echo.
pause
endlocal
