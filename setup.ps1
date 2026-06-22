# Prism PDF 一键安装脚本
# 适用于 Windows PowerShell 5.0+

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Prism PDF 安装程序" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# ============================================================
# 1. 检查 Python 版本
# ============================================================
Write-Host "[1/6] 检查 Python 环境..." -ForegroundColor Yellow

try {
    $pythonVersion = python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "Python 未安装或未添加到 PATH"
    }
    Write-Host "    $pythonVersion" -ForegroundColor Green

    $versionMatch = [regex]::Match($pythonVersion, "Python (\d+)\.(\d+)\.(\d+)")
    $major = [int]$versionMatch.Groups[1].Value
    $minor = [int]$versionMatch.Groups[2].Value

    if ($major -ne 3 -or $minor -lt 10 -or $minor -gt 12) {
        Write-Host "    ⚠️  警告: 推荐使用 Python 3.10 ~ 3.12" -ForegroundColor Yellow
        Write-Host "    当前版本可能存在兼容性问题" -ForegroundColor Yellow
    }
}
catch {
    Write-Host "    ❌ 错误: 未找到 Python" -ForegroundColor Red
    Write-Host "    请从 https://www.python.org/downloads/ 下载安装 Python 3.10+" -ForegroundColor Red
    exit 1
}

# ============================================================
# 2. 创建虚拟环境
# ============================================================
Write-Host ""
Write-Host "[2/6] 创建 Python 虚拟环境..." -ForegroundColor Yellow

$venvDir = Join-Path $ScriptDir "venv"
if (Test-Path $venvDir) {
    Write-Host "    虚拟环境已存在，跳过创建" -ForegroundColor Green
}
else {
    Write-Host "    创建 venv/ 目录..."
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    ❌ 虚拟环境创建失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "    ✅ 虚拟环境创建成功" -ForegroundColor Green
}

# ============================================================
# 3. 激活虚拟环境并安装依赖
# ============================================================
Write-Host ""
Write-Host "[3/6] 安装 Python 依赖包..." -ForegroundColor Yellow

$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvPip = Join-Path $venvDir "Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "    ❌ 虚拟环境 Python 不存在" -ForegroundColor Red
    exit 1
}

Write-Host "    升级 pip..."
& $venvPython -m pip install --upgrade pip | Out-Null

Write-Host "    安装依赖（使用清华镜像加速）..."
$requirementsFile = Join-Path $ScriptDir "requirements.txt"
if (-not (Test-Path $requirementsFile)) {
    Write-Host "    ❌ 找不到 requirements.txt" -ForegroundColor Red
    exit 1
}

& $venvPip install -r $requirementsFile -i https://pypi.tuna.tsinghua.edu.cn/simple
if ($LASTEXITCODE -ne 0) {
    Write-Host "    ⚠️  清华镜像安装失败，尝试使用默认源..." -ForegroundColor Yellow
    & $venvPip install -r $requirementsFile
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    ❌ 依赖安装失败" -ForegroundColor Red
        exit 1
    }
}
Write-Host "    ✅ 依赖安装成功" -ForegroundColor Green

# ============================================================
# 4. 验证核心依赖
# ============================================================
Write-Host ""
Write-Host "[4/6] 验证核心依赖..." -ForegroundColor Yellow

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
        Write-Host "    ✅ $($dep.name)" -ForegroundColor Green
    }
    catch {
        Write-Host "    ❌ $($dep.name) 导入失败" -ForegroundColor Red
        $allOk = $false
    }
}

# 检查 CUDA 支持
Write-Host ""
Write-Host "    检查 GPU/CUDA 支持..."
try {
    $cudaResult = & $venvPython -c "import torch; print('CUDA:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')" 2>&1
    Write-Host "    $cudaResult" -ForegroundColor Cyan
}
catch {
    Write-Host "    无法检测 GPU 状态（不影响 CPU 模式运行）" -ForegroundColor Yellow
}

if (-not $allOk) {
    Write-Host "    ⚠️  部分依赖验证失败，可能影响功能" -ForegroundColor Yellow
}

# ============================================================
# 5. 创建必要目录
# ============================================================
Write-Host ""
Write-Host "[5/6] 创建必要目录..." -ForegroundColor Yellow

$dirs = @("models", "tmp", "data")
foreach ($dir in $dirs) {
    $dirPath = Join-Path $ScriptDir $dir
    if (-not (Test-Path $dirPath)) {
        New-Item -ItemType Directory -Path $dirPath | Out-Null
        Write-Host "    ✅ 创建 $dir/" -ForegroundColor Green
    }
    else {
        Write-Host "    $dir/ 已存在" -ForegroundColor Gray
    }
}

# ============================================================
# 6. 完成并显示信息
# ============================================================
Write-Host ""
Write-Host "[6/6] 安装完成!" -ForegroundColor Yellow
Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  安装成功!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
Write-Host "使用方法:" -ForegroundColor Cyan
Write-Host "  1. 配置 OCR 服务（如需解析扫描件）:" -ForegroundColor White
Write-Host "     编辑 start_llama_server.bat，设置 llama.cpp 路径" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. 启动所有服务:" -ForegroundColor White
Write-Host "     .\start_all.bat" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. 或分开启动（推荐调试用）:" -ForegroundColor White
Write-Host "     终端1: .\start_llama_server.bat   # OCR服务" -ForegroundColor Gray
Write-Host "     终端2: venv\Scripts\activate" -ForegroundColor Gray
Write-Host "            python -m backend.main       # 主服务" -ForegroundColor Gray
Write-Host ""
Write-Host "  4. 打开浏览器访问:" -ForegroundColor White
Write-Host "     http://localhost:8000" -ForegroundColor Gray
Write-Host ""
Write-Host "详细配置请参考:" -ForegroundColor Cyan
Write-Host "  - README.md              快速入门" -ForegroundColor Gray
Write-Host "  - setup.md               详细配置" -ForegroundColor Gray
Write-Host "  - flow.md                解析流程" -ForegroundColor Gray
Write-Host "  - hardware_requirements.md 硬件需求" -ForegroundColor Gray
Write-Host ""
