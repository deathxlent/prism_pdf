# Prism PDF 环境配置与启动指南

## 目录

1. [系统要求](#1-系统要求)
2. [Windows 平台配置](#2-windows-平台配置)
3. [Linux 平台配置](#3-linux-平台配置)
4. [macOS Apple Silicon 平台配置](#4-macos-apple-silicon-平台配置)
5. [llama.cpp OCR 服务配置（扫描件必需）](#5-llamacpp-ocr-服务配置扫描件必需)
6. [启动脚本说明](#6-启动脚本说明)
7. [常见问题排查](#7-常见问题排查)

---

## 1. 系统要求

### 支持的操作系统
| 系统 | 版本 | 说明 |
|------|------|------|
| **Windows** | 10/11 64 位 | 推荐，一键脚本支持最完善 |
| **Linux** | Ubuntu 20.04+ / Debian 11+ / CentOS 8+ | 服务器部署推荐 |
| **macOS** | 12+ (Monterey及以上) | **仅支持 Apple Silicon (M1/M2/M3/M4)**，不支持 Intel |

### 软件依赖
- Python 3.10 ~ 3.12（推荐 3.10）
- Git（可选，用于克隆项目）
- CUDA Toolkit 12+（Windows/Linux 仅 NVIDIA GPU 版本需要）
- Homebrew（macOS 推荐）

### 硬件要求
详见 [hardware_requirements.md](hardware_requirements.md)

---

## 2. Windows 平台配置

### 2.1 安装 Python

1. 下载 Python 3.10.x：https://www.python.org/downloads/release/python-31011/
2. 运行安装程序，**勾选 "Add Python to PATH"**
3. 安装完成后验证：

```powershell
python --version
# 输出: Python 3.10.x
```

### 2.2 一键安装（推荐）

在项目根目录下打开 PowerShell，运行：

```powershell
.\setup.ps1
```

脚本会自动完成虚拟环境创建、依赖安装、环境验证。

### 2.3 手动安装（进阶）

#### 2.3.1 创建虚拟环境

```powershell
cd "g:\ws\Prism PDF"
python -m venv venv
```

#### 2.3.2 激活虚拟环境

```powershell
venv\Scripts\activate
```

激活后命令行前缀会显示 `(venv)`。

> 💡 退出虚拟环境：`deactivate`

#### 2.3.3 安装 Python 依赖

确保已激活虚拟环境，然后执行：

```powershell
pip install -r requirements.txt
```

如果下载速度慢，可以使用国内镜像：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

#### 2.3.4 验证安装

```powershell
python -c "import fastapi, fitz, ultralytics; print('All dependencies OK')"
```

#### 2.3.5 配置模型下载镜像（国内用户必需）

项目已默认配置 HuggingFace 镜像，无需额外设置：

```python
# backend/config.py
HF_MIRROR_URL = "https://hf-mirror.com"
```

首次运行时会自动下载以下模型：
- **YOLO26m 布局检测模型**（~100MB）：`Armaggheddon/yolo26-document-layout`
- **Surya 阅读顺序模型**（~500MB）：`vikp/surya_order`

> 💡 模型会自动下载到 `models/` 目录下，只需下载一次。

#### 2.3.6 目录结构说明

首次运行后会自动创建以下目录：

```
Prism PDF/
├── models/          # AI 模型文件
├── tmp/             # 临时文件（上传的 PDF、处理结果）
└── data.db          # SQLite 数据库文件（自动创建）
```

---

## 3. Linux 平台配置

### 3.1 系统准备

#### Ubuntu / Debian

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git

# 如使用 NVIDIA GPU，安装 CUDA Toolkit 12+（可选但推荐）
# 参考: https://developer.nvidia.com/cuda-toolkit
```

#### CentOS / RHEL / Fedora

```bash
sudo dnf install -y python3 python3-pip git

# CentOS 7 可能需要启用 EPEL 源
```

验证 Python 版本：

```bash
python3 --version
# 确保输出为 3.10.x ~ 3.12.x
```

### 3.2 一键安装（推荐）

在项目根目录下执行：

```bash
cd "Prism PDF"
chmod +x setup.sh && ./setup.sh
```

### 3.3 手动安装（进阶）

#### 3.3.1 创建虚拟环境

```bash
cd "Prism PDF"
python3 -m venv venv
```

#### 3.3.2 激活虚拟环境

```bash
source venv/bin/activate
```

#### 3.3.3 安装 Python 依赖

```bash
# 使用清华镜像加速（国内推荐）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用默认源
pip install -r requirements.txt
```

> 💡 **NVIDIA GPU 用户注意**：如需要 CUDA 加速的 PyTorch，请先手动安装：
> ```bash
> pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
> ```

#### 3.3.4 验证安装

```bash
python -c "import fastapi, fitz, ultralytics; print('All dependencies OK')"

# 检查 CUDA 支持
python -c "import torch; print('CUDA available:', torch.cuda.is_available())"
```

#### 3.3.5 创建必要目录

```bash
mkdir -p models tmp data
```

---

## 4. macOS Apple Silicon 平台配置

> ⚠️ **重要**：本指南仅适用于 Apple Silicon (M1/M2/M3/M4) 芯片的 Mac。
> Intel 芯片的 Mac 请使用 Linux 虚拟机或 Windows 方案。

### 4.1 系统准备

#### 安装 Homebrew（如未安装）

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

#### 安装 Python

```bash
# 通过 Homebrew 安装 Python 3.11（推荐）
brew install python@3.11

# 验证
python3 --version
```

### 4.2 一键安装（推荐）

在项目根目录下执行：

```bash
cd "Prism PDF"
chmod +x setup_mac.sh && ./setup_mac.sh
```

> ✨ 脚本会自动检测 Apple Silicon 架构，配置 MPS (Metal) 加速。

### 4.3 手动安装（进阶）

#### 4.3.1 创建虚拟环境

```bash
cd "Prism PDF"
python3 -m venv venv
```

#### 4.3.2 激活虚拟环境

```bash
source venv/bin/activate
```

#### 4.3.3 安装 Python 依赖

```bash
# 使用清华镜像加速（国内推荐）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用默认源
pip install -r requirements.txt
```

> ✨ **Apple Silicon 特殊说明**：
> - PyTorch 原生支持 Apple Silicon，会自动使用 MPS (Metal Performance Shaders) 加速
> - YOLO 和 Surya 模型会自动检测并使用 MPS 设备
> - 无需额外安装 CUDA，使用 Apple 的 Unified Memory 架构

#### 4.3.4 验证安装

```bash
python -c "import fastapi, fitz, ultralytics; print('All dependencies OK')"

# 检查 MPS 支持（Apple Silicon 应为 True）
python -c "import torch; print('MPS available:', torch.backends.mps.is_available())"
python -c "import torch; print('MPS built:', torch.backends.mps.is_built())"
```

#### 4.3.5 创建必要目录

```bash
mkdir -p models tmp data
```

---

## 5. llama.cpp OCR 服务配置（扫描件必需）

如果需要解析**扫描版 PDF** 或包含**乱码**的 PDF，需要配置 llama.cpp OCR 服务。

### 5.1 方案选择

| 方案 | 适用场景 | 速度 | 显存/内存需求 |
|------|----------|------|---------------|
| **NVIDIA GPU** | Windows/Linux 有 NVIDIA 显卡 | 快 (~60 t/s) | 4GB+ 显存 |
| **Apple Metal** | macOS Apple Silicon | 中 (~30 t/s) | 2GB+ 统一内存 |
| **CPU** | 无显卡/纯 CPU 服务器 | 慢 (~5-10 t/s) | 2GB+ 内存 |

---

### 5.2 Windows 平台配置

#### 5.2.1 GPU 版本配置（推荐）

##### 准备 CUDA 环境

1. 检查显卡是否支持 CUDA：NVIDIA 显卡，计算能力 ≥ 5.0
2. 安装 CUDA Toolkit 12.x：https://developer.nvidia.com/cuda-toolkit
3. 安装 cuDNN（可选，推荐）
4. 验证安装：

```powershell
nvcc --version
nvidia-smi
```

##### 下载 llama.cpp 预编译包

1. 访问 https://github.com/ggml-org/llama.cpp/releases
2. 下载最新版本的 `llama-*-bin-win-cuda-x64.zip`
3. 解压到 `G:\llamacpp\` 目录

```
G:\llamacpp\
├── llama-cli.exe
├── llama-server.exe
├── llama-quantize.exe
├── ggml-cuda.dll
└── models/          # 创建此目录
```

##### 下载 PaddleOCR-VL 模型

**方式一：使用 huggingface-cli（推荐）**

```powershell
# 安装 huggingface_hub（如未安装）
pip install huggingface_hub

# 设置镜像
set HF_ENDPOINT=https://hf-mirror.com

# 下载 LLM 主干（Q4_K_M 量化版，推荐）
hf download PaddlePaddle/PaddleOCR-VL-1.6-GGUF PaddleOCR-VL-1.6.Q4_K_M.gguf --local-dir G:\llamacpp\models\

# 下载视觉编码器 mmproj
hf download PaddlePaddle/PaddleOCR-VL-1.6-GGUF PaddleOCR-VL-1.6-GGUF-mmproj.gguf --local-dir G:\llamacpp\models\
```

**方式二：手动下载**

访问 https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF 下载以下文件：
- `PaddleOCR-VL-1.6.Q4_K_M.gguf` (286MB)
- `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (841MB)

放到 `G:\llamacpp\models\` 目录。

##### 目录结构确认

```
G:\llamacpp\
├── llama-server.exe
├── ggml-cuda.dll
└── models\
    ├── PaddleOCR-VL-1.6.Q4_K_M.gguf
    └── PaddleOCR-VL-1.6-GGUF-mmproj.gguf
```

##### 测试 OCR 服务

```powershell
cd G:\llamacpp

# 启动测试服务器
llama-server.exe -m models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --host 127.0.0.1 --port 8080 -ngl 99 --temp 0 -c 4096
```

看到 `HTTP server listening on port 8080` 表示启动成功。

按 `Ctrl+C` 停止服务。

#### 5.2.2 CPU 版本配置

如果没有 NVIDIA 显卡，使用 CPU 版本。

##### 下载 llama.cpp CPU 版本

1. 访问 https://github.com/ggml-org/llama.cpp/releases
2. 下载最新版本的 `llama-*-bin-win-cpu-x64.zip`
3. 解压到 `C:\llamacpp-cpu\` 目录

```
C:\llamacpp-cpu\
├── llama-cli.exe
├── llama-server.exe
└── models\
```

##### 下载模型文件

与 GPU 版本相同，下载以下文件放到 `C:\llamacpp-cpu\models\`：
- `PaddleOCR-VL-1.6.Q4_K_M.gguf` (286MB)
- `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (841MB)

##### 测试 CPU 版本

```powershell
cd C:\llamacpp-cpu

# 启动 CPU 版服务器（-ngl 0 表示纯 CPU）
llama-server.exe -m models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --host 127.0.0.1 --port 8080 -ngl 0 -t 8 --temp 0 -c 4096
```

> 💡 `-t 8` 表示使用 8 个 CPU 线程，建议设置为物理核心数。
> 设置环境变量 `set OMP_NUM_THREADS=8` 可进一步加速。

#### 5.2.3 自行编译 llama.cpp（可选）

如果预编译包不适用，可以自行编译：

##### GPU 版编译

```powershell
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build
cd build

cmake .. -DGGML_CUDA=ON
cmake --build . --config Release

# 产物在 build\bin\Release\
```

##### CPU 版编译

```powershell
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build
cd build

cmake .. -DGGML_CUDA=OFF -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS
cmake --build . --config Release
```

---

### 5.3 Linux 平台配置

#### 5.3.1 GPU 版本配置（推荐）

##### 准备 CUDA 环境

```bash
# 验证 CUDA
nvcc --version
nvidia-smi
```

##### 下载 llama.cpp 预编译包

```bash
# 从 releases 下载 llama-*-bin-ubuntu-x64.zip
wget https://github.com/ggml-org/llama.cpp/releases/download/<version>/llama-<version>-bin-ubuntu-x64.zip
unzip llama-*-bin-ubuntu-x64.zip -d /opt/llamacpp
```

##### 或自行编译（启用 CUDA）

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

##### 下载模型文件

```bash
pip install huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
mkdir -p /opt/llamacpp/models
huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir /opt/llamacpp/models
```

##### 测试服务

```bash
cd /opt/llamacpp
./llama-server \
  -m models/PaddleOCR-VL-1.6.Q4_K_M.gguf \
  --mmproj models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf \
  --host 127.0.0.1 --port 8080 -ngl 99 --temp 0 -c 4096
```

#### 5.3.2 CPU 版本配置

##### 下载或编译 CPU 版 llama.cpp

```bash
# 方式一：下载预编译的 CPU 版本
# 方式二：编译时不启用 CUDA
cmake .. -DGGML_CUDA=OFF -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS
```

##### 测试 CPU 版本

```bash
cd /opt/llamacpp

# 设置 CPU 线程数（建议为物理核心数）
export OMP_NUM_THREADS=$(nproc)

./llama-server \
  -m models/PaddleOCR-VL-1.6.Q4_K_M.gguf \
  --mmproj models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf \
  --host 127.0.0.1 --port 8080 -ngl 0 -t $(nproc) --temp 0 -c 4096
```

---

### 5.4 macOS Apple Silicon 平台配置

> ✨ Apple Silicon 使用 Metal Framework 加速，无需额外安装 CUDA。

#### 5.4.1 安装 llama.cpp

##### 方式一：通过 Homebrew（最简单，推荐）

```bash
brew install llama.cpp
```

##### 方式二：下载预编译包

```bash
# 从 releases 下载 llama-*-bin-macos-arm64.zip
unzip llama-*-bin-macos-arm64.zip -d /opt/llamacpp
```

##### 方式三：自行编译（启用 Metal）

```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

#### 5.4.2 下载模型文件

```bash
pip install huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
mkdir -p /opt/llamacpp/models
huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir /opt/llamacpp/models
```

#### 5.4.3 测试服务

```bash
cd /opt/llamacpp

# Metal 优化环境变量
export GGML_METAL_MAX_BUFFERS=0
export GGML_METAL_MALLOC_LIMIT=0

# 启动服务（-ngl 99 表示全部使用 Metal 加速）
./llama-server \
  -m models/PaddleOCR-VL-1.6.Q4_K_M.gguf \
  --mmproj models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf \
  --host 127.0.0.1 --port 8080 \
  -ngl 99 -t $(sysctl -n hw.physicalcpu) \
  --temp 0 -c 4096 --no-display-prompt
```

> ✨ **Apple Silicon 优势**：
> - Unified Memory 架构，无需担心显存不足
> - CPU + GPU 共享内存，模型加载更快
> - M1 Pro/Max/Ultra 性能强劲，适合批量处理

---

## 6. 启动脚本说明

### 6.1 脚本一览

| 平台 | 安装脚本 | 一键启动脚本 | OCR 服务启动脚本 |
|------|---------|-------------|-----------------|
| **Windows** | `setup.ps1` | `start_all.bat` | `start_llama_server.bat` |
| **Linux** | `setup.sh` | `start_all.sh` | `start_llama_server.sh` |
| **macOS M系列** | `setup_mac.sh` | `start_all_mac.sh` | `start_llama_server_mac.sh` |

### 6.2 配置启动参数

#### Windows

编辑项目根目录下的 `start_llama_server.bat`，根据实际路径修改：

**GPU 版本：**

```batch
@echo off
echo Starting llama-server with PaddleOCR-VL-1.6 Q4_K_M (GPU)...
echo Server will listen on http://127.0.0.1:8080
echo.

G:\llamacpp\llama-server.exe ^
  -m "G:\llamacpp\models\PaddleOCR-VL-1.6.Q4_K_M.gguf" ^
  --mmproj "G:\llamacpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf" ^
  --host 127.0.0.1 ^
  --port 8080 ^
  -ngl 99 ^
  -c 4096 ^
  -b 512 ^
  -t 8

echo.
echo Server stopped. Exit code: %ERRORLEVEL%
pause
```

**CPU 版本：**

```batch
@echo off
echo Starting llama-server with PaddleOCR-VL-1.6 Q4_K_M (CPU)...
echo Server will listen on http://127.0.0.1:8080
echo.

set OMP_NUM_THREADS=8

C:\llamacpp-cpu\llama-server.exe ^
  -m "C:\llamacpp-cpu\models\PaddleOCR-VL-1.6.Q4_K_M.gguf" ^
  --mmproj "C:\llamacpp-cpu\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf" ^
  --host 127.0.0.1 ^
  --port 8080 ^
  -ngl 0 ^
  -c 4096 ^
  -b 512 ^
  -t 8

echo.
echo Server stopped. Exit code: %ERRORLEVEL%
pause
```

#### Linux

编辑 `start_llama_server.sh`，修改以下配置：

```bash
# llama.cpp 安装目录
LLAMACPP_DIR="/opt/llamacpp"

# 模型文件路径
MODEL_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6.Q4_K_M.gguf"
MMPROJ_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

# GPU 层数量: 99=全部GPU, 0=纯CPU
NGL="99"

# CPU 线程数
THREADS=$(nproc 2>/dev/null || echo 8)
```

#### macOS Apple Silicon

编辑 `start_llama_server_mac.sh`，修改以下配置（Homebrew 安装通常无需修改）：

```bash
# llama.cpp 安装目录
LLAMACPP_DIR="/opt/llamacpp"

# 模型文件路径
MODEL_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6.Q4_K_M.gguf"
MMPROJ_FILE="$LLAMACPP_DIR/models/PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

# Metal 层数量: 99=全部加速, 0=纯CPU
NGL="99"

# CPU 线程数（性能核心数）
THREADS=$(sysctl -n hw.physicalcpu 2>/dev/null || echo 8)
```

### 6.3 快速启动步骤

#### 日常使用

**方式一：一键启动（推荐）**

| 平台 | 命令 |
|------|------|
| Windows | 双击 `start_all.bat` |
| Linux | `./start_all.sh` |
| macOS | `./start_all_mac.sh` |

**方式二：分开启动（推荐，方便看日志）**

**Windows：**
```powershell
# 终端 1：启动 OCR 服务（如果需要解析扫描件）
cd "g:\ws\Prism PDF"
start_llama_server.bat

# 终端 2：启动主服务
cd "g:\ws\Prism PDF"
venv\Scripts\activate
python -m backend.main
```

**Linux：**
```bash
# 终端 1：启动 OCR 服务（如需）
./start_llama_server.sh

# 终端 2：启动主服务
source venv/bin/activate
python -m backend.main
```

**macOS：**
```bash
# 终端 1：启动 OCR 服务（如需）
./start_llama_server_mac.sh

# 终端 2：启动主服务
source venv/bin/activate
python -m backend.main
```

#### 首次使用

首次启动会自动下载 AI 模型（YOLO + Surya），请耐心等待。

### 6.4 验证服务

1. 打开浏览器访问 http://localhost:8000
2. 上传一个 PDF 文件测试
3. 查看控制台日志确认无错误

---

## 7. 常见问题排查

### 7.1 依赖安装问题

**Q: `pip install` 时提示 torch 安装失败**

A: 手动安装合适版本的 torch：

**Windows/Linux (CUDA):**
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
```

**Windows/Linux (CPU):**
```powershell
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**macOS (Apple Silicon):**
```bash
# PyTorch 官方已原生支持，通常无需特殊处理
pip install torch torchvision
```

**Q: paddlepaddle 安装失败**

A: 参考官方文档：https://www.paddlepaddle.org.cn/install/quick

**Q: `ModuleNotFoundError: No module named 'backend'`**

A: 确保在项目根目录下运行，且使用 `python -m backend.main` 方式启动。

---

### 7.2 CUDA / GPU 问题 (Windows/Linux)

**Q: 运行时提示 `CUDA out of memory`**

A: 
1. 减少 `-c` 参数（上下文长度），如 `-c 2048`
2. 使用 `Q4_K_M` 量化模型（已默认）
3. 减少 `-ngl` 参数，部分层使用 CPU：`-ngl 20`
4. 关闭其他占用显存的程序

**Q: YOLO 模型无法使用 GPU**

A: 检查 `backend/config.py` 中的配置：

```python
YOLO_DEVICE = "cuda"  # 改为 "cuda"
```

并确认 torch 已正确安装 CUDA 版本：

```bash
python -c "import torch; print(torch.cuda.is_available())"
# 应为 True
```

---

### 7.3 MPS 问题 (macOS Apple Silicon)

**Q: MPS 不可用**

A: 
1. 确认使用 Apple Silicon (arm64) Python 版本
2. 确认 PyTorch 版本 ≥ 2.0
3. 更新 PyTorch 到最新版：`pip install --upgrade torch`
4. 可手动修改 config.py：`YOLO_DEVICE = "mps"`

**Q: MPS 运行时报错**

A: 部分操作 MPS 尚不支持，可回退到 CPU：
```python
# backend/config.py
YOLO_DEVICE = "cpu"
```

---

### 7.4 OCR 服务问题

**Q: llama-server 启动后输出为空或卡住**

A:
1. 添加 `-n 500` 限制生成 token 数
2. 添加 `--no-display-prompt`
3. 检查模型文件路径是否正确
4. 确认图片路径正确

**Q: 调用 OCR 时报错 `Connection refused`**

A: 确认 llama-server 已启动并监听 8080 端口：

**Windows:**
```powershell
netstat -ano | findstr "8080"
```

**Linux/macOS:**
```bash
lsof -ti:8080
# 或
ss -tlnp | grep 8080
```

**Q: OCR 识别速度很慢**

| 平台 | 现象 | 可能原因 | 解决方案 |
|------|------|----------|----------|
| 全部 | CPU 版每张图 30s+ | CPU 性能不足 | 升级 CPU，增加线程数 `-t` |
| Windows | GPU 版每张图 5s+ | 显存不足导致使用 CPU | 检查 `nvidia-smi`，减少 `-c` |
| Linux | GPU 版每张图 5s+ | CUDA 未正确配置 | 重新安装 CUDA 版 PyTorch |
| macOS | 每张图 5s+ | 未启用 Metal | 确认 `-ngl 99`，检查 Metal 编译 |
| 全部 | 首次调用慢 | 模型加载中 | 正常，后续调用会快很多 |

---

### 7.5 模型下载问题

**Q: HuggingFace 下载超时或速度慢**

A: 确认已配置镜像：

**Windows (PowerShell):**
```powershell
$env:HF_ENDPOINT = "https://hf-mirror.com"
```

**Linux/macOS:**
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

或使用 ModelScope 镜像手动下载。

**Q: YOLO 模型下载失败**

A: 手动下载模型放到 `models/` 目录：

```
https://hf-mirror.com/Armaggheddon/yolo26-document-layout/resolve/main/yolo26m_doc_layout.pt
```

---

### 7.6 PDF 解析问题

**Q: 扫描件 PDF 内容为空**

A:
1. 确认 llama-server 已启动
2. 检查页面是否被正确识别为扫描件（`is_scanned: true`）
3. 查看 llama-server 日志确认请求到达
4. 检查 `backend/services/ocr_service_vl.py` 中的服务地址配置

**Q: 表格识别效果差**

A:
1. 确保使用 GPU/Metal 加速版本和 Q4_K_M 以上模型
2. 检查 PDF 清晰度，扫描件建议 300 DPI 以上
3. 对于复杂表格，可以使用"重解析"功能重新识别

**Q: 中文乱码**

A: 系统会自动检测乱码并触发 OCR。如果仍有乱码：
1. 检查 PDF 字体是否嵌入
2. 手动触发重解析，系统会自动使用 OCR

---

## 附录：端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| 主服务 (FastAPI) | 8000 | Web 界面和 API |
| llama.cpp OCR 服务 | 8080 | OpenAI 兼容 API |

如需修改端口：
- 主服务：修改 `backend/main.py` 中的 `uvicorn.run` 参数
- OCR 服务：修改对应启动脚本中的 `--port` 参数和 `backend/services/ocr_service_vl.py` 中的 `LLAMA_SERVER_URL`
