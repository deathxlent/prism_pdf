# Prism PDF - Qwen3.5-4B Model Download Script (PowerShell)
# Downloads local LLM model for translation and image description

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Prism PDF - Qwen3.5-4B Model Download" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# Configuration
# ============================================================

# Model repository
$ModelRepo = "Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF"

# Quantization version
$Quant = "Q4_K_M"

# Model filename (auto-generated)
$ModelFile = "Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-$Quant.gguf"

# Download directory
$DownloadDir = "G:\llamacpp\models"

# HuggingFace mirror (recommended for users in China)
$HF_ENDPOINT = "https://hf-mirror.com"

# ============================================================
# Check Python and huggingface_hub
# ============================================================

Write-Host "[Check] Verifying dependencies..." -ForegroundColor Yellow

try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not installed"
    }
    Write-Host "    $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "[ERROR] Python not found, please install Python 3.10+ first" -ForegroundColor Red
    Write-Host "   Download: https://www.python.org/downloads/" -ForegroundColor Red
    Write-Host ""
    exit 1
}

# Check huggingface_hub
try {
    python -c "import huggingface_hub" 2>&1 | Out-Null
    Write-Host "    huggingface_hub installed" -ForegroundColor Green
} catch {
    Write-Host "    Installing huggingface_hub..."
    python -m pip install huggingface_hub -i https://pypi.tuna.tsinghua.edu.cn/simple
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "[ERROR] Failed to install huggingface_hub" -ForegroundColor Red
        Write-Host ""
        exit 1
    }
    Write-Host "    huggingface_hub installed" -ForegroundColor Green
}

Write-Host ""

# ============================================================
# Create download directory
# ============================================================

if (-not (Test-Path $DownloadDir)) {
    Write-Host "[INFO] Creating download directory: $DownloadDir" -ForegroundColor Cyan
    New-Item -ItemType Directory -Path $DownloadDir -Force | Out-Null
}

# ============================================================
# Start download
# ============================================================

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Download Configuration" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Repository:   $ModelRepo"
Write-Host "  Quantization: $Quant"
Write-Host "  Model file:   $ModelFile"
Write-Host "  Download dir: $DownloadDir"
Write-Host "  Mirror:       $HF_ENDPOINT"
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[TIP] Download may take a few minutes, please be patient" -ForegroundColor Yellow
Write-Host "[TIP] Model size is approximately 2.6-2.9 GB (Q4_K_M)" -ForegroundColor Yellow
Write-Host ""

$env:HF_ENDPOINT = $HF_ENDPOINT
$env:HF_HUB_DISABLE_TELEMETRY = "1"

$pythonCode = @"
import os
import sys

repo_id = "$ModelRepo"
filename = "$ModelFile"
local_dir = r"$DownloadDir"

print(f"Downloading: {filename}")
print(f"Repository: {repo_id}")
print()

try:
    from huggingface_hub import hf_hub_download
    path = hf_hub_download(
        repo_id=repo_id,
        filename=filename,
        local_dir=local_dir,
        local_dir_use_symlinks=False
    )
    print()
    print("Download complete!")
    print(f"File path: {path}")
except ImportError:
    print("Error: huggingface_hub not installed", file=sys.stderr)
    sys.exit(1)
except Exception as e:
    print(f"Download failed: {e}", file=sys.stderr)
    sys.exit(1)
"@

try {
    python -c $pythonCode
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed"
    }
} catch {
    Write-Host ""
    Write-Host "============================================" -ForegroundColor Red
    Write-Host "  Download Failed" -ForegroundColor Red
    Write-Host "============================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible reasons:"
    Write-Host "  1. Network connection issue"
    Write-Host "  2. Incorrect model filename"
    Write-Host "  3. Insufficient disk space"
    Write-Host ""
    Write-Host "You can also download manually:"
    Write-Host "  $HF_ENDPOINT/$ModelRepo/resolve/main/$ModelFile"
    Write-Host ""
    Write-Host "Then place it in: $DownloadDir\"
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Download Complete!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "Model file: $DownloadDir\$ModelFile"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Update model path in start_llm_llama_server.bat"
Write-Host "  2. Add local LlamaCPP config in Web UI 'LLM Config'"
Write-Host "     Base URL:   http://127.0.0.1:8081/v1"
Write-Host "     Model name: $ModelFile"
Write-Host ""
