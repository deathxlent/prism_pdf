@echo off
REM ============================================================
REM Prism PDF - 一键启动脚本
REM 同时启动 llama.cpp OCR 服务和主服务
REM ============================================================

setlocal enabledelayedexpansion
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

echo.
echo ============================================
echo   Prism PDF - 一键启动
echo ============================================
echo.

REM ============================================================
REM 检查虚拟环境
REM ============================================================

set "VENV_PYTHON=%SCRIPT_DIR%venv\Scripts\python.exe"
set "VENV_ACTIVATE=%SCRIPT_DIR%venv\Scripts\activate.bat"

if not exist "%VENV_PYTHON%" (
    echo [错误] 未找到 Python 虚拟环境
    echo.
    echo 请先运行安装脚本:
    echo   powershell -ExecutionPolicy Bypass -File .\setup.ps1
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM 检查 OCR 服务是否已在运行
REM ============================================================

echo [检测] 检查端口占用...

netstat -ano | findstr ":8080" >nul 2>&1
if %errorlevel% equ 0 (
    echo [警告] 端口 8080 已被占用，跳过 OCR 服务启动
    echo        如果 OCR 服务未正常工作，请手动检查
    set "SKIP_OCR=1"
) else (
    set "SKIP_OCR=0"
)

netstat -ano | findstr ":8000" >nul 2>&1
if %errorlevel% equ 0 (
    echo [警告] 端口 8000 已被占用，主服务可能已在运行
)
echo.

REM ============================================================
REM 启动 OCR 服务
REM ============================================================

if "%SKIP_OCR%"=="0" (
    echo [1/2] 启动 llama.cpp OCR 服务...
    start "Prism PDF - OCR Service" cmd /k "cd /d "%SCRIPT_DIR%" && start_llama_server.bat"
    echo       OCR 服务窗口已启动
    echo.
    echo       等待 OCR 服务初始化 (15秒)...
    timeout /t 15 /nobreak >nul
    echo.
) else (
    echo [1/2] 跳过 OCR 服务启动 (端口已占用)
    echo.
)

REM ============================================================
REM 启动主服务
REM ============================================================

echo [2/2] 启动 Prism PDF 主服务...
echo.
echo       服务信息:
echo         - 主服务地址: http://localhost:8000
echo         - OCR 服务地址: http://localhost:8080
echo         - 虚拟环境: %SCRIPT_DIR%venv
echo.
echo       按 Ctrl+C 停止主服务 (OCR 服务需手动关闭)
echo.
echo ============================================
echo.

REM 激活虚拟环境并启动主服务
if exist "%VENV_ACTIVATE%" (
    call "%VENV_ACTIVATE%"
)

"%VENV_PYTHON%" -m backend.main

echo.
echo ============================================
echo   主服务已停止
echo ============================================
echo.
echo 注意: OCR 服务窗口可能仍在运行，请手动关闭
echo.
pause
endlocal
