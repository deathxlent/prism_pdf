# Prism PDF 环境配置与启动指南

## 目录

1. [系统要求](#1-系统要求)
2. [Python 环境配置](#2-python-环境配置)
3. [主项目安装](#3-主项目安装)
4. [llama.cpp OCR 服务配置（扫描件必需）](#4-llamacpp-ocr-服务配置扫描件必需)
5. [启动脚本](#5-启动脚本)
6. [常见问题排查](#6-常见问题排查)

---

## 1. 系统要求

### 操作系统
- Windows 10 / Windows 11（推荐）
- Linux（需自行调整路径和脚本）

### 软件依赖
- Python 3.10 ~ 3.12（推荐 3.10）
- Git（可选，用于克隆项目）
- CUDA Toolkit 12+（仅 GPU 版本需要）

### 硬件要求
详见 [hardware_requirements.md](hardware_requirements.md)

---

## 2. Python 环境配置

### 2.1 安装 Python

1. 下载 Python 3.10.x：https://www.python.org/downloads/release/python-31011/
2. 运行安装程序，**勾选 "Add Python to PATH"**
3. 安装完成后验证：

```powershell
python --version
# 输出: Python 3.10.x
```

### 2.2 创建虚拟环境（推荐）

在项目根目录下执行：

```powershell
cd "g:\ws\Prism PDF"
python -m venv venv
```

### 2.3 激活虚拟环境

```powershell
venv\Scripts\activate
```

激活后命令行前缀会显示 `(venv)`。

> 💡 退出虚拟环境：`deactivate`

---

## 3. 主项目安装

### 3.1 安装 Python 依赖

确保已激活虚拟环境，然后执行：

```powershell
pip install -r requirements.txt
```

如果下载速度慢，可以使用国内镜像：

```powershell
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 3.2 验证安装

```powershell
python -c "import fastapi, fitz, ultralytics; print('All dependencies OK')"
```

### 3.3 配置模型下载镜像（国内用户必需）

项目已默认配置 HuggingFace 镜像，无需额外设置：

```python
# backend/config.py
HF_MIRROR_URL = "https://hf-mirror.com"
```

首次运行时会自动下载以下模型：
- **YOLO26m 布局检测模型**（~100MB）：`Armaggheddon/yolo26-document-layout`
- **Surya 阅读顺序模型**（~500MB）：`vikp/surya_order`

> 💡 模型会自动下载到 `models/` 目录下，只需下载一次。

### 3.4 目录结构说明

首次运行后会自动创建以下目录：

```
Prism PDF/
├── models/          # AI 模型文件
├── tmp/             # 临时文件（上传的 PDF、处理结果）
└── data.db          # SQLite 数据库文件（自动创建）
```

---

## 4. llama.cpp OCR 服务配置（扫描件必需）

如果需要解析**扫描版 PDF** 或包含**乱码**的 PDF，需要配置 llama.cpp OCR 服务。

### 4.1 方案选择

| 方案 | 适用场景 | 速度 | 显存需求 |
|------|----------|------|----------|
| **GPU 版本** | 有 NVIDIA 显卡 | 快 (~60 t/s) | 4GB+ |
| **CPU 版本** | 无显卡 | 慢 (~5-10 t/s) | 2GB+ 内存 |

---

### 4.2 GPU 版本配置（推荐）

#### 4.2.1 准备 CUDA 环境

1. 检查显卡是否支持 CUDA：NVIDIA 显卡，计算能力 ≥ 5.0
2. 安装 CUDA Toolkit 12.x：https://developer.nvidia.com/cuda-toolkit
3. 安装 cuDNN（可选，推荐）
4. 验证安装：

```powershell
nvcc --version
nvidia-smi
```

#### 4.2.2 下载 llama.cpp 预编译包

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

#### 4.2.3 下载 PaddleOCR-VL 模型

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

#### 4.2.4 目录结构确认

```
G:\llamacpp\
├── llama-server.exe
├── ggml-cuda.dll
└── models\
    ├── PaddleOCR-VL-1.6.Q4_K_M.gguf
    └── PaddleOCR-VL-1.6-GGUF-mmproj.gguf
```

#### 4.2.5 测试 OCR 服务

```powershell
cd G:\llamacpp

# 启动测试服务器
llama-server.exe -m models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --host 127.0.0.1 --port 8080 -ngl 99 --temp 0 -c 4096
```

看到 `HTTP server listening on port 8080` 表示启动成功。

按 `Ctrl+C` 停止服务。

---

### 4.3 CPU 版本配置

如果没有 NVIDIA 显卡，使用 CPU 版本。

#### 4.3.1 下载 llama.cpp CPU 版本

1. 访问 https://github.com/ggml-org/llama.cpp/releases
2. 下载最新版本的 `llama-*-bin-win-cpu-x64.zip`
3. 解压到 `C:\llamacpp-cpu\` 目录

```
C:\llamacpp-cpu\
├── llama-cli.exe
├── llama-server.exe
└── models\
```

#### 4.3.2 下载模型文件

与 GPU 版本相同，下载以下文件放到 `C:\llamacpp-cpu\models\`：
- `PaddleOCR-VL-1.6.Q4_K_M.gguf` (286MB)
- `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (841MB)

#### 4.3.3 测试 CPU 版本

```powershell
cd C:\llamacpp-cpu

# 启动 CPU 版服务器（-ngl 0 表示纯 CPU）
llama-server.exe -m models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --host 127.0.0.1 --port 8080 -ngl 0 -t 8 --temp 0 -c 4096
```

> 💡 `-t 8` 表示使用 8 个 CPU 线程，建议设置为物理核心数。
> 设置环境变量 `set OMP_NUM_THREADS=8` 可进一步加速。

---

### 4.4 自行编译 llama.cpp（可选）

如果预编译包不适用，可以自行编译：

#### GPU 版编译

```powershell
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build
cd build

cmake .. -DGGML_CUDA=ON
cmake --build . --config Release

# 产物在 build\bin\Release\
```

#### CPU 版编译

```powershell
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build
cd build

cmake .. -DGGML_CUDA=OFF -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS
cmake --build . --config Release
```

---

## 5. 启动脚本

### 5.1 配置启动参数

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

### 5.2 一键启动脚本

创建 `start_all.bat` 一键启动所有服务：

```batch
@echo off
echo ========================================
echo Prism PDF 一键启动脚本
echo ========================================
echo.

echo [1/2] 启动 llama.cpp OCR 服务...
start "llama-server" cmd /k "cd /d \"%~dp0\" && start_llama_server.bat"

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
```

### 5.3 快速启动步骤

#### 日常使用

**方式一：分开启动（推荐，方便看日志）**

```powershell
# 终端 1：启动 OCR 服务（如果需要解析扫描件）
cd "g:\ws\Prism PDF"
start_llama_server.bat

# 终端 2：启动主服务
cd "g:\ws\Prism PDF"
venv\Scripts\activate
python -m backend.main
```

**方式二：一键启动**

双击 `start_all.bat`

#### 首次使用

首次启动会自动下载 AI 模型（YOLO + Surya），请耐心等待。

### 5.4 验证服务

1. 打开浏览器访问 http://localhost:8000
2. 上传一个 PDF 文件测试
3. 查看控制台日志确认无错误

---

## 6. 常见问题排查

### 6.1 依赖安装问题

**Q: `pip install` 时提示 torch 安装失败**

A: 手动安装合适版本的 torch：

```powershell
# GPU 版本
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121

# CPU 版本
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
```

**Q: paddlepaddle 安装失败**

A: 参考官方文档：https://www.paddlepaddle.org.cn/install/quick

**Q: `ModuleNotFoundError: No module named 'backend'`**

A: 确保在项目根目录下运行，且使用 `python -m backend.main` 方式启动。

---

### 6.2 CUDA / GPU 问题

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

```powershell
python -c "import torch; print(torch.cuda.is_available())"
# 应为 True
```

---

### 6.3 OCR 服务问题

**Q: llama-server 启动后输出为空或卡住**

A:
1. 添加 `-n 500` 限制生成 token 数
2. 添加 `--no-display-prompt`
3. 检查模型文件路径是否正确
4. 确认图片路径正确

**Q: 调用 OCR 时报错 `Connection refused`**

A: 确认 llama-server 已启动并监听 8080 端口：

```powershell
netstat -ano | findstr "8080"
```

**Q: OCR 识别速度很慢**

| 现象 | 可能原因 | 解决方案 |
|------|----------|----------|
| CPU 版每张图 30s+ | CPU 性能不足 | 升级 CPU，增加线程数 `-t` |
| GPU 版每张图 5s+ | 显存不足导致使用 CPU | 检查 `nvidia-smi`，减少 `-c` |
| 首次调用慢 | 模型加载中 | 正常，后续调用会快很多 |

---

### 6.4 模型下载问题

**Q: HuggingFace 下载超时或速度慢**

A: 确认已配置镜像：

```powershell
set HF_ENDPOINT=https://hf-mirror.com
```

或使用 ModelScope 镜像手动下载。

**Q: YOLO 模型下载失败**

A: 手动下载模型放到 `models/` 目录：

```
https://hf-mirror.com/Armaggheddon/yolo26-document-layout/resolve/main/yolo26m_doc_layout.pt
```

---

### 6.5 PDF 解析问题

**Q: 扫描件 PDF 内容为空**

A:
1. 确认 llama-server 已启动
2. 检查页面是否被正确识别为扫描件（`is_scanned: true`）
3. 查看 llama-server 日志确认请求到达
4. 检查 `backend/services/ocr_service_vl.py` 中的服务地址配置

**Q: 表格识别效果差**

A:
1. 确保使用 GPU 版本和 Q4_K_M 以上模型
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
- OCR 服务：修改 `start_llama_server.bat` 中的 `--port` 参数和 `backend/services/ocr_service_vl.py` 中的 `LLAMA_SERVER_URL`
