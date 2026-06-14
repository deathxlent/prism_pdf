@echo off
echo ========================================
echo Prism PDF 一键启动脚本
echo ========================================
echo.

echo [1/2] 启动 llama.cpp OCR 服务...
start "llama-server" cmd /k "cd /d "%~dp0" && start_llama_server.bat"

echo 等待 llama-server 启动...
timeout /t 10

echo.
echo [2/2] 启动主服务...
echo 激活虚拟环境并启动 FastAPI...
cd /d "%~dp0"
call venv\Scripts\activate
python -m backend.main

echo.
echo 所有服务已停止。
pause
