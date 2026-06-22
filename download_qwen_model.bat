@echo off
REM ============================================================
REM Prism PDF - Qwen3.5-4B Model Download Script (Windows)
REM Downloads local LLM model for translation and image description
REM ============================================================

setlocal enabledelayedexpansion

echo.
echo ============================================
echo   Prism PDF - Qwen3.5-4B Model Download
echo ============================================
echo.

REM ============================================================
REM Configuration
REM ============================================================

REM Model repository
set "MODEL_REPO=Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF"

REM Quantization version
set "QUANT=Q4_K_M"

REM Model filename (auto-generated)
set "MODEL_FILE=Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-%QUANT%.gguf"

REM Download directory
set "DOWNLOAD_DIR=G:\llamacpp\models"

REM HuggingFace mirror (recommended for users in China)
set "HF_ENDPOINT=https://hf-mirror.com"

REM ============================================================
REM Check Python and huggingface_hub
REM ============================================================

echo [Check] Verifying dependencies...

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Python not found, please install Python 3.10+ first
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo [OK] Python installed

REM Check huggingface_hub
python -c "import huggingface_hub" >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing huggingface_hub...
    python -m pip install huggingface_hub -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo.
        echo [ERROR] Failed to install huggingface_hub
        echo.
        pause
        exit /b 1
    )
)

echo [OK] huggingface_hub installed
echo.

REM ============================================================
REM Create download directory
REM ============================================================

if not exist "%DOWNLOAD_DIR%" (
    echo [INFO] Creating download directory: %DOWNLOAD_DIR%
    mkdir "%DOWNLOAD_DIR%"
)

REM ============================================================
REM Start download
REM ============================================================

echo ============================================
echo   Download Configuration
echo ============================================
echo   Repository:   %MODEL_REPO%
echo   Quantization: %QUANT%
echo   Model file:   %MODEL_FILE%
echo   Download dir: %DOWNLOAD_DIR%
echo   Mirror:       %HF_ENDPOINT%
echo ============================================
echo.
echo [TIP] Download may take a few minutes, please be patient
echo [TIP] Model size is approximately 2.6-2.9 GB (Q4_K_M)
echo.

set "HF_HUB_DISABLE_TELEMETRY=1"

python -c "
import os
os.environ['HF_ENDPOINT'] = '%HF_ENDPOINT%'
from huggingface_hub import hf_hub_download
import sys

repo_id = '%MODEL_REPO%'
filename = '%MODEL_FILE%'
local_dir = r'%DOWNLOAD_DIR%'

print(f'Downloading: {filename}')
print(f'Repository: {repo_id}')
print()

try:
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=local_dir,
        local_dir_use_symlinks=False
    )
    print()
    print('Download complete!')
    print(f'File path: {path}')
except Exception as e:
    print(f'Download failed: {e}', file=sys.stderr)
    sys.exit(1)
"

if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo   Download Failed
    echo ============================================
    echo.
    echo Possible reasons:
    echo   1. Network connection issue
    echo   2. Incorrect model filename
    echo   3. Insufficient disk space
    echo.
    echo You can also download manually:
    echo   %HF_ENDPOINT%/%MODEL_REPO%/resolve/main/%MODEL_FILE%
    echo.
    echo Then place it in: %DOWNLOAD_DIR%\
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   Download Complete!
echo ============================================
echo.
echo Model file: %DOWNLOAD_DIR%\%MODEL_FILE%
echo.
echo Next steps:
echo   1. Update model path in start_llm_llama_server.bat
echo   2. Add local LlamaCPP config in Web UI "LLM Config"
echo      Base URL:    http://127.0.0.1:8081/v1
echo      Model name:   %MODEL_FILE%
echo.
pause
endlocal
