# Prism PDF Setup Script
# For Windows PowerShell 5.0+

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Prism PDF Setup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# 1. Check Python version
# ============================================================
Write-Host "[1/6] Checking Python environment..." -ForegroundColor Yellow

try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python not found"
    }
    Write-Host "    $pythonVersion" -ForegroundColor Green

    $versionMatch = [regex]::Match($pythonVersion, "Python (\d+)\.(\d+)\.(\d+)")
    $major = [int]$versionMatch.Groups[1].Value
    $minor = [int]$versionMatch.Groups[2].Value

    if ($major -ne 3 -or $minor -lt 10 -or $minor -gt 12) {
        Write-Host "    WARNING: Python 3.10 ~ 3.12 is recommended" -ForegroundColor Yellow
        Write-Host "    Current version may have compatibility issues" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "    ERROR: Python not found" -ForegroundColor Red
    Write-Host "    Please download Python 3.10+ from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

# ============================================================
# 2. Create virtual environment
# ============================================================
Write-Host ""
Write-Host "[2/6] Creating Python virtual environment..." -ForegroundColor Yellow

$venvDir = Join-Path $ScriptDir "venv"
if (Test-Path $venvDir) {
    Write-Host "    Virtual environment already exists, skipping" -ForegroundColor Green
}
else {
    Write-Host "    Creating venv/ directory..."
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    ERROR: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "    Virtual environment created successfully" -ForegroundColor Green
}

# ============================================================
# 3. Activate virtual environment and install dependencies
# ============================================================
Write-Host ""
Write-Host "[3/6] Installing Python dependencies..." -ForegroundColor Yellow

$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "    ERROR: Virtual environment Python not found" -ForegroundColor Red
    exit 1
}

Write-Host "    Upgrading pip..."
& $venvPython -m pip install --upgrade pip | Out-Null

Write-Host "    Installing dependencies (using Tsinghua mirror)..."
$requirementsFile = Join-Path $ScriptDir "requirements.txt"
if (-not (Test-Path $requirementsFile)) {
    Write-Host "    ERROR: requirements.txt not found" -ForegroundColor Red
    exit 1
}

& $venvPip install -r $requirementsFile -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    Write-Host "    WARNING: Tsinghua mirror failed, trying default source..." -ForegroundColor Yellow
    & $venvPip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    ERROR: Failed to install dependencies" -ForegroundColor Red
        exit 1
    }
}
Write-Host "    Dependencies installed successfully" -ForegroundColor Green

# ============================================================
# 4. Verify core dependencies
# ============================================================
Write-Host ""
Write-Host "[4/6] Verifying core dependencies..." -ForegroundColor Yellow

$checkDeps = @(
    @{name = "FastAPI"; module = "fastapi" },
    @{name = "PyMuPDF"; module = "fitz" },
    @{name = "Ultralytics"; module = "ultralytics" },
    @{name = "PyTorch"; module = "torch" },
    @{name = "Pillow"; module = "PIL" },
    @{name = "aiosqlite"; module = "aiosqlite" }
)

$allOk = $true
foreach ($dep in $checkDeps) {
    try {
        & $venvPython -c "import $($dep.module); print('OK')" | Out-Null
        Write-Host "    OK: $($dep.name)" -ForegroundColor Green
    }
    catch {
        Write-Host "    FAIL: $($dep.name) import error" -ForegroundColor Red
        $allOk = $false
    }
}

# Check CUDA support
Write-Host ""
Write-Host "    Checking GPU/CUDA support..."
try {
    $cudaResult = & $venvPython -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')" 2>&1
    Write-Host "    $cudaResult" -ForegroundColor Cyan
}
catch {
    Write-Host "    Cannot detect GPU status (does not affect CPU mode)" -ForegroundColor Yellow
}

if (-not $allOk) {
    Write-Host "    WARNING: Some dependencies failed verification, functionality may be affected" -ForegroundColor Yellow
}

# ============================================================
# 5. Create required directories
# ============================================================
Write-Host ""
Write-Host "[5/6] Creating required directories..." -ForegroundColor Yellow

$dirs = @("models", "tmp", "data")
foreach ($dir in $dirs) {
    $dirPath = Join-Path $ScriptDir $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath | Out-Null
        Write-Host "    Created $dir/" -ForegroundColor Green
    }
    else {
        Write-Host "    $dir/ already exists" -ForegroundColor Gray
    }
}

# ============================================================
# 6. Complete and show information
# ============================================================
Write-Host ""
Write-Host "[6/6] Setup complete!" -ForegroundColor Yellow
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Setup Successful!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: Before using Prism PDF, you MUST configure:" -ForegroundColor Cyan
Write-Host ""
Write-Host "  1. LLM Translation Model (REQUIRED)" -ForegroundColor White
Write-Host "     Without this: PDF text translation will NOT work." -ForegroundColor Gray
Write-Host "     Options:" -ForegroundColor Gray
Write-Host "       a) Cloud API: Add OpenAI/DeepSeek/Claude etc. with API key" -ForegroundColor Gray
Write-Host "       b) Local model: Run start_llm_llama_server.bat, then add LlamaCPP config" -ForegroundColor Gray
Write-Host "     Go to: http://localhost:8000 -> Settings -> LLM Config" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. PaddleVL OCR Model (REQUIRED for scanned PDFs)" -ForegroundColor White
Write-Host "     Without this: Scanned/image PDF text extraction will NOT work." -ForegroundColor Gray
Write-Host "     Steps:" -ForegroundColor Gray
Write-Host "       a) Run start_llama_server.bat to start PaddleOCR-VL service" -ForegroundColor Gray
Write-Host "       b) Go to: http://localhost:8000 -> Settings -> LLM Config -> PaddleVL" -ForegroundColor Gray
Write-Host "       c) Add PaddleVL service URL (e.g., http://localhost:8080/v1)" -ForegroundColor Gray
Write-Host ""
Write-Host "  NOTE: Insufficient VRAM may cause model loading failures." -ForegroundColor Yellow
Write-Host "  PaddleOCR-VL requires ~1.2GB VRAM (Q4 quantization)." -ForegroundColor Yellow
Write-Host "  If VRAM is insufficient, OCR may crash or run very slowly in CPU mode." -ForegroundColor Yellow
Write-Host ""
Write-Host "Usage:" -ForegroundColor Cyan
Write-Host "  1. Start all services:" -ForegroundColor White
Write-Host "     .\start_all.bat" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. Or start separately (for debugging):" -ForegroundColor White
Write-Host "     Terminal 1: .\start_llama_server.bat     (OCR service)" -ForegroundColor Gray
Write-Host "     Terminal 2: venv\Scripts\activate" -ForegroundColor Gray
Write-Host "                python -m backend.main          (Main service)" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Open browser:" -ForegroundColor White
Write-Host "     http://localhost:8000" -ForegroundColor Gray
Write-Host ""
Write-Host "For details, see:" -ForegroundColor Cyan
Write-Host "  - README.md                Quick start" -ForegroundColor Gray
Write-Host "  - setup.md                 Detailed config" -ForegroundColor Gray
Write-Host "  - flow.md                  Parsing flow" -ForegroundColor Gray
Write-Host "  - hardware_requirements.md Hardware requirements" -ForegroundColor Gray
Write-Host ""
