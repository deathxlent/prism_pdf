@echo off
REM ============================================================
REM Prism PDF - llama.cpp OCR 服务启动脚本
REM 用于启动 PaddleOCR-VL 多模态 OCR 服务
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Prism PDF - llama.cpp OCR 服务启动
echo ============================================
echo.

REM ============================================================
REM 配置区域 - 根据实际情况修改以下路径
REM ============================================================

REM llama.cpp 安装目录
set "LLAMACPP_DIR=G:\llamacpp"

REM 模型文件路径
set "MODEL_FILE=%LLAMACPP_DIR%\models\PaddleOCR-VL-1.6.Q4_K_M.gguf"
set "MMPROJ_FILE=%LLAMACPP_DIR%\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

REM 服务配置
set "HOST=127.0.0.1"
set "PORT=8080"

REM GPU 层数量: 99=全部GPU, 0=纯CPU
set "NGL=99"

REM CPU 线程数（建议设为物理核心数）
set "THREADS=8"

REM 上下文长度
set "CTX_LEN=4096"

REM 批处理大小
set "BATCH_SIZE=512"

REM ============================================================
REM 检查路径有效性
REM ============================================================

echo [检查] 验证配置...

if not exist "%LLAMACPP_DIR%\llama-server.exe" (
    echo.
    echo [错误] 找不到 llama-server.exe
    echo 路径: %LLAMACPP_DIR%\llama-server.exe
    echo.
    echo 请修改本脚本中的 LLAMACPP_DIR 变量
    echo llama.cpp 下载地址:
    echo   https://github.com/ggml-org/llama.cpp/releases
    echo.
    pause
    exit /b 1
)

if not exist "%MODEL_FILE%" (
    echo.
    echo [错误] 找不到模型文件: %MODEL_FILE%
    echo.
    echo 请从以下地址下载:
    echo   https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF
    echo.
    echo 需要下载两个文件:
    echo   1. PaddleOCR-VL-1.6.Q4_K_M.gguf (LLM主干, ~286MB)
    echo   2. PaddleOCR-VL-1.6-GGUF-mmproj.gguf (视觉编码器, ~841MB)
    echo.
    pause
    exit /b 1
)

if not exist "%MMPROJ_FILE%" (
    echo.
    echo [错误] 找不到视觉编码器文件: %MMPROJ_FILE%
    echo.
    echo 请从以下地址下载:
    echo   https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF
    echo.
    pause
    exit /b 1
)

echo [OK] 所有文件路径有效
echo.

REM ============================================================
REM 检测 GPU 可用性
REM ============================================================

echo [检测] GPU 状态...
where nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] 检测到 NVIDIA GPU
    for /f "tokens=*" %%i in ('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits') do (
        echo      %%i
    )
    echo      使用 GPU 层数量: %NGL%
) else (
    echo [警告] 未检测到 NVIDIA GPU，强制使用 CPU 模式
    set "NGL=0"
)
echo.

REM ============================================================
REM 设置 CPU 优化环境变量
REM ============================================================

if "%NGL%"=="0" (
    echo [信息] CPU 模式: 设置 OMP_NUM_THREADS=%THREADS%
    set "OMP_NUM_THREADS=%THREADS%"
)
echo.

REM ============================================================
REM 显示启动信息
REM ============================================================

echo ============================================
echo   启动配置
echo ============================================
echo   服务地址:     http://%HOST%:%PORT%
echo   模型文件:     %MODEL_FILE%
echo   视觉编码器:   %MMPROJ_FILE%
echo   GPU 层数:     %NGL%
echo   CPU 线程:     %THREADS%
echo   上下文长度:   %CTX_LEN%
echo ============================================
echo.
echo [提示] 首次加载模型可能需要较长时间
echo [提示] 看到 "HTTP server listening" 表示启动成功
echo [提示] 按 Ctrl+C 停止服务
echo.

REM ============================================================
REM 启动服务
REM ============================================================

cd /d "%LLAMACPP_DIR%"

"%LLAMACPP_DIR%\llama-server.exe" ^
  -m "%MODEL_FILE%" ^
  --mmproj "%MMPROJ_FILE%" ^
  --host %HOST% ^
  --port %PORT% ^
  -ngl %NGL% ^
  -c %CTX_LEN% ^
  -b %BATCH_SIZE% ^
  -t %THREADS% ^
  --no-display-prompt

echo.
echo ============================================
echo  服务已停止，退出代码: %ERRORLEVEL%
echo ============================================
echo.
pause
endlocal
