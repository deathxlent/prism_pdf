@echo off
REM ============================================================
REM Prism PDF - llama.cpp LLM Service Start Script
REM Starts local LLM for translation and image description
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Prism PDF - llama.cpp LLM Service
echo ============================================
echo.

REM ============================================================
REM Configuration - Modify paths below as needed
REM ============================================================

REM llama.cpp installation directory
set "LLAMACPP_DIR=G:\llamacpp"

REM Model file path (Qwen3.5-4B)
set "MODEL_FILE=%LLAMACPP_DIR%\models\Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-Q4_K_M.gguf"

REM Service configuration
set "HOST=127.0.0.1"
set "PORT=8081"

REM GPU layers: 99=all GPU, 0=CPU only
set "NGL=99"

REM CPU threads (recommended: physical core count)
set "THREADS=8"

REM Context length
set "CTX_LEN=8192"

REM Batch size
set "BATCH_SIZE=512"

REM ============================================================
REM Verify paths
REM ============================================================

echo [Check] Validating configuration...

if not exist "%LLAMACPP_DIR%\llama-server.exe" (
    echo.
    echo [ERROR] llama-server.exe not found
    echo Path: %LLAMACPP_DIR%\llama-server.exe
    echo.
    echo Please update LLAMACPP_DIR in this script
    echo Download llama.cpp from:
    echo   https://github.com/ggml-org/llama.cpp/releases
    echo.
    pause
    exit /b 1
)

if not exist "%MODEL_FILE%" (
    echo.
    echo [ERROR] Model file not found: %MODEL_FILE%
    echo.
    echo Please run download_qwen_model.bat to download the model
    echo Or download manually from:
    echo   https://hf-mirror.com/Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF
    echo.
    echo Recommended: Q4_K_M quantization version (~2.7 GB)
    echo.
    pause
    exit /b 1
)

echo [OK] All file paths valid
echo.

REM ============================================================
REM Detect GPU availability
REM ============================================================

echo [Check] GPU status...
where nvidia-smi >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] NVIDIA GPU detected
    for /f "tokens=*" %%i in ('nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits') do (
        echo      %%i
    )
    echo      GPU layers: %NGL%
) else (
    echo [WARN] No NVIDIA GPU detected, forcing CPU mode
    set "NGL=0"
)
echo.

REM ============================================================
REM Set CPU optimization environment variables
REM ============================================================

if "%NGL%"=="0" (
    echo [INFO] CPU mode: Setting OMP_NUM_THREADS=%THREADS%
    set "OMP_NUM_THREADS=%THREADS%"
)
echo.

REM ============================================================
REM Display startup info
REM ============================================================

echo ============================================
echo   Startup Configuration
echo ============================================
echo   Service URL:    http://%HOST%:%PORT%
echo   API URL:        http://%HOST%:%PORT%/v1
echo   Model file:     %MODEL_FILE%
echo   GPU layers:     %NGL%
echo   CPU threads:    %THREADS%
echo   Context length: %CTX_LEN%
echo ============================================
echo.
echo [TIP] First model load may take a while
echo [TIP] "HTTP server listening" indicates successful start
echo [TIP] Press Ctrl+C to stop the service
echo.

REM ============================================================
REM Start service
REM ============================================================

cd /d "%LLAMACPP_DIR%"

"%LLAMACPP_DIR%\llama-server.exe" ^
  -m "%MODEL_FILE%" ^
  --host %HOST% ^
  --port %PORT% ^
  -ngl %NGL% ^
  -c %CTX_LEN% ^
  -b %BATCH_SIZE% ^
  -t %THREADS% ^
  --no-display-prompt

echo.
echo ============================================
echo  Service stopped, exit code: %ERRORLEVEL%
echo ============================================
echo.
pause
endlocal
