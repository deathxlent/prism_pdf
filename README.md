# Prism PDF — 本地高精度 PDF 解析与翻译系统

> 一个功能完整的本地 PDF 解析系统，集成多种 AI 模型，实现文档布局分析、内容提取、表格识别、机器翻译和结构化输出。

---

## 📖 工具功能

Prism PDF 是一款**完全本地化运行**的 PDF 文档智能解析工具，专为需要高精度文档结构化提取的场景设计。它将 PDF 文档转化为可编辑、可检索的结构化数据，支持扫描件识别和多语言翻译。

### 核心能力

| 功能模块 | 能力说明 |
|---------|---------|
| **文档管理** | PDF 上传、加密/损坏检测、文档列表、删除、批量操作 |
| **布局分析** | 11 类文档元素识别：标题、段落、列表、表格、图片、公式、页眉页脚等 |
| **阅读顺序** | 支持多栏、复杂排版的智能阅读顺序排序 |
| **内容提取** | 原生 PDF 文本直接提取，扫描件/乱码自动切换 OCR 识别 |
| **表格识别** | 完整 HTML 表格输出，支持 rowspan/colspan 跨行跨列、跨页表格自动合并 |
| **图片提取** | 自动提取文档中的图片区域，保存为独立文件，支持 Vision LLM 生成图片描述 |
| **公式识别** | 数学公式区域检测与 LaTeX 格式输出 |
| **机器翻译** | 单元素/单页/整文档翻译，支持自定义目标语言 |
| **结果编辑** | Web 界面人工校正内容、调整类型、重新排序、框选添加新元素 |
| **多格式导出** | HTML / Markdown / PDF 单页导出，支持原文和译文分别导出，支持 RAG 友好格式（自动去除页眉页脚） |
| **LLM 集成** | 灵活的大模型配置管理，支持多种 LLM API 提供商 |

---

## ✨ 亮点特性

### 🎯 高精度解析
- **双模式识别**：原生 PDF 直接提取文本（速度快、精度高），扫描件自动 OCR
- **11 类布局元素**：YOLO26m 深度学习模型，识别标题、段落、列表、表格、图片、公式、页眉页脚等
- **智能阅读顺序**：Surya Order 模型处理多栏、复杂排版，支持 fallback 坐标排序
- **跨行跨列表格**：完整保留 HTML 表格结构，支持 rowspan/colspan

### 🖼️ 智能图片描述
- **Vision LLM 描述**：解析完成后批量生成图片描述，作为 caption 导出
- **页眉页脚排除**：页眉页脚区域的图片不参与描述生成，避免无效描述
- **导出集成**：HTML 导出以 figure-caption 展示，Markdown 导出以 alt 文本展示

### 🔒 完全本地化
- **零数据上传**：所有 AI 推理在本地完成，文档不离开你的设备
- **离线可用**：模型文件下载后可完全断网运行
- **SQLite 存储**：轻量级嵌入式数据库，无需额外部署数据库服务

### 🌍 多语言支持
- **翻译导出**：一键翻译并导出为 HTML/Markdown
- **灵活的 LLM 配置**：Web 界面管理多种翻译模型提供商
- **批量翻译**：支持单页和整文档批量翻译

### 🤖 RAG 友好格式导出
- **自动去页眉页脚**：导出时自动过滤所有页眉页脚元素（基于类型和阈值标记双重判断）
- **两种导出模式**：可选择保留原始页码（每页单独 HTML，打包 ZIP）或不保留（合并为单个 HTML）
- **适合知识库构建**：干净、结构化的输出可直接导入向量数据库

### ⚡ 性能优化
- **混合加速**：YOLO/Surya 可 CPU 运行，OCR 推荐 GPU 加速
- **渐进式处理**：分页处理，大文档不会内存溢出
- **自动降级**：GPU 不可用时自动回退 CPU

### 🛠️ 开发友好
- **RESTful API**：完整的 HTTP API，易于集成到其他系统
- **可定制**：模块化设计，易于替换和扩展各个处理组件
- **可视化调试**：支持查看 YOLO 布局检测标注图、原始 OCR 结果

---

## 💻 系统需求

### 支持的操作系统
**Windows** 、**Linux** 、**macOS**4

---

### 🪟 纯本地运行配置参考

#### 最低配置（可运行）
任意机器，4G以上内存，但会缺失自动阅读排序序功能，同时只用CPU加速的话，OCR会非常慢
|------|------|
| CPU | Intel i5-6500 / AMD Ryzen 5 1600 以上 |
| 内存 | 16 GB DDR4 |
| 硬盘 | 50 GB 可用空间（SSD 推荐） |
| 显卡 | 核显即可（OCR 会使用 CPU，速度较慢） |

#### 推荐配置（性价比最优）
8G以上NVIDIA显卡，最小模型建议使用YOLO+SURYA Order（1G显存），Qwen3.5-4B.Q4_K_M4（3G显存，如果没有翻译和图生成描述要求的话，可以不使用），OCR采用PaddleOCR-VL-1.6.Q4_K_M（3G显存，如果没有OCR需求的话，可以不使用）。

#### 专业配置（批量处理）
主要看部署的图生文模型和OCR模型，其他模型的显存需求比较低。

---
### 🪟 如果OCR和图生文模型已在其他地方部署
纯CPU会缺失自动阅读排序序功能，其他无影响
如果有大于1G的显存，则所有功能均可使用

---

> 📚 详细硬件需求与性能对比见由AI 生成的 [hardware_requirements.md](hardware_requirements.md) 仅供参考

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Web 前端 (index.html)                    │
│   三栏式界面：缩略图导航 + PDF 预览 + 解析结果编辑              │
│   原生 HTML/CSS/JS · PDF.js · Font Awesome 6                   │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTP API (FastAPI)
┌────────────────────────────▼────────────────────────────────────┐
│                   FastAPI 后端 (uvicorn)                        │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    API 路由层 (routes.py)                 │  │
│  │  /upload /parse /status /results /export /translate ... │  │
│  └────────────────────┬─────────────────────────────────────┘  │
│                       │                                          │
│  ┌────────────────────▼─────────────────────────────────────┐  │
│  │                 主解析调度层 (parse_service.py)          │  │
│  │    process_upload() → process_document() → _parse_page()│  │
│  └──────┬──────────────┬──────────────┬─────────────────────┘  │
│         │              │              │                          │
│  ┌──────▼─────┐ ┌──────▼─────┐ ┌────▼───────────┐              │
│  │ PDF 基础   │ │ 布局检测    │ │ 阅读顺序排序   │              │
│  │ 服务       │ │ YOLO26m    │ │ Surya Order    │              │
│  └──────┬─────┘ └────────────┘ └────┬───────────┘              │
│         │                           │                          │
│  ┌──────▼─────┐ ┌────────────┐ ┌────▼───────────┐              │
│  │ 表格提取   │ │ 图片提取    │ │ OCR 服务       │              │
│  │ (原生+扫描)│ │            │ │ llama.cpp VL   │              │
│  └────────────┘ └────────────┘ └────┬───────────┘              │
│                                     │                          │
│  ┌─────────────────────┐    ┌──────▼──────┐                    │
│  │  SQLite 数据库      │    │ llama-server │                    │
│  │  (aiosqlite)        │    │ (独立进程)   │                    │
│  └─────────────────────┘    └─────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

### 技术栈明细

| 层级 | 技术选型 | 用途 |
|------|---------|------|
| **Web 框架** | FastAPI + uvicorn | HTTP API 服务 |
| **PDF 处理** | PyMuPDF (fitz) | PDF 解析、文本提取、转图 |
| **布局检测** | Ultralytics YOLOv8 (YOLO26m) | 11 类文档元素定位 |
| **阅读顺序** | Surya Order Model | 多栏布局阅读排序 |
| **OCR 识别** | PaddleOCR-VL + llama.cpp | 扫描件/乱码多模态识别 |
| **机器翻译** | 可配置 LLM (OpenAI 兼容 API) | 元素/页面/文档翻译 |
| **数据存储** | SQLite + aiosqlite | 文档、页面、元素持久化 |
| **前端** | 原生 HTML5/CSS3/JavaScript | 无需构建，直接运行 |
| **PDF 渲染** | PDF.js | 浏览器端 PDF 预览 |

---

## 🚀 快速开始

### 步骤 1：环境准备

确保已安装：
- **Python 3.10 ~ 3.12**（推荐 3.10）
- **CUDA Toolkit 12+**（Windows/Linux 如有 NVIDIA GPU，可选但推荐）
- **Homebrew**（macOS 推荐，用于安装依赖）

---

### 步骤 2：一键安装（按平台选择）

#### 🪟 Windows

在项目根目录下打开 PowerShell，运行：

```powershell
.\setup.ps1
```

#### 🐧 Linux

在终端中运行：

```bash
chmod +x setup.sh && ./setup.sh
```

> 💡 Ubuntu/Debian 首次使用请先安装基础依赖：
> ```bash
> sudo apt update && sudo apt install python3 python3-pip python3-venv
> ```

#### 🍎 macOS (Apple Silicon / M系列)

在终端中运行：

```bash
chmod +x setup_mac.sh && ./setup_mac.sh
```

> 💡 首次使用请先安装 Homebrew（如未安装）：
> ```bash
> /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
> ```

---

安装脚本会自动完成：
1. ✅ 创建 Python 虚拟环境
2. ✅ 安装所有 Python 依赖
3. ✅ 验证环境配置
4. ✅ 创建必要的目录

> 如果手动安装，请参考 [setup.md](setup.md)

---

### 步骤 3：配置 OCR 服务（扫描件必需）

如果需要解析扫描版 PDF 或包含乱码的文档，需要配置 llama.cpp OCR 服务。

#### 🪟 Windows

**1. 下载 llama.cpp**

从 https://github.com/ggml-org/llama.cpp/releases 下载预编译包：
- GPU 版本：`llama-*-bin-win-cuda-x64.zip`
- CPU 版本：`llama-*-bin-win-cpu-x64.zip`

解压到例如 `G:\llamacpp\`

**2. 下载 PaddleOCR-VL 模型**

访问 https://hf-mirror.com/PaddlePaddle/PaddleOCR-VL-1.6-GGUF 下载：
- `PaddleOCR-VL-1.6.Q4_K_M.gguf`（286 MB，LLM 主干）
- `PaddleOCR-VL-1.6-GGUF-mmproj.gguf`（841 MB，视觉编码器）

放到 `G:\llamacpp\models\` 目录。

**3. 修改配置**

编辑 `start_llama_server.bat`，将路径改为你实际的 llama.cpp 和模型路径。

#### 🐧 Linux

**1. 安装 llama.cpp**

方式一：下载预编译包（推荐）
```bash
# 从 releases 下载 llama-*-bin-ubuntu-x64.zip
unzip llama-*-bin-ubuntu-x64.zip -d /opt/llamacpp
```

方式二：自行编译（启用 CUDA）
```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

**2. 下载模型**

```bash
pip install huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
mkdir -p /opt/llamacpp/models
huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir /opt/llamacpp/models
```

**3. 修改配置**

编辑 `start_llama_server.sh`，调整 `LLAMACPP_DIR` 和模型路径。

#### 🍎 macOS (Apple Silicon)

**1. 安装 llama.cpp**

方式一：通过 Homebrew（最简单）
```bash
brew install llama.cpp
```

方式二：下载预编译包
```bash
# 下载 llama-*-bin-macos-arm64.zip 解压到 /opt/llamacpp
```

方式三：自行编译（启用 Metal）
```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. -DGGML_METAL=ON -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

**2. 下载模型**

```bash
pip install huggingface_hub
export HF_ENDPOINT=https://hf-mirror.com
mkdir -p /opt/llamacpp/models
huggingface-cli download PaddlePaddle/PaddleOCR-VL-1.6-GGUF --local-dir /opt/llamacpp/models
```

**3. 修改配置**

编辑 `start_llama_server_mac.sh`，调整路径（Homebrew 安装通常无需修改）。

---

### 步骤 4：启动服务（按平台选择）

#### 🪟 Windows

**方式一：一键启动（推荐）**

```powershell
.\start_all.bat
```

**方式二：分开启动（方便查看日志）**

```powershell
# 终端 1：启动 OCR 服务（如需）
.\start_llama_server.bat

# 终端 2：启动主服务
python -m backend.main
```

#### 🐧 Linux

**方式一：一键启动（推荐）**

```bash
chmod +x start_all.sh start_llama_server.sh
./start_all.sh
```

**方式二：分开启动（方便查看日志）**

```bash
# 终端 1：启动 OCR 服务（如需）
./start_llama_server.sh

# 终端 2：启动主服务
source venv/bin/activate
python -m backend.main
```

#### 🍎 macOS (Apple Silicon)

**方式一：一键启动（推荐）**

```bash
chmod +x start_all_mac.sh start_llama_server_mac.sh
./start_all_mac.sh
```

**方式二：分开启动（方便查看日志）**

```bash
# 终端 1：启动 OCR 服务（如需）
./start_llama_server_mac.sh

# 终端 2：启动主服务
source venv/bin/activate
python -m backend.main
```

---

### 步骤 5：开始使用

浏览器打开 http://localhost:8000

1. 点击"上传 PDF"选择文档
2. 点击"开始解析"等待处理完成
3. 在右侧查看和编辑解析结果
4. 点击"导出"选择格式下载（支持原文/译文分别导出）

---

## ⚡ 性能和效果优化

### 模型替换指南

#### 1. 布局检测模型（YOLO）

当前使用：`Armaggheddon/yolo26-document-layout`

可替换为其他文档布局模型：

| 候选模型 | 来源 | 精度 | 速度 | 说明 |
|---------|------|------|------|------|
| **YOLOv8-DocLayout** | HuggingFace | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 当前使用，综合表现好 |
| **LayoutLMv3** | Microsoft | ⭐⭐⭐⭐⭐ | ⭐⭐ | 更高精度，速度较慢 |
| **DocAnalyzer** | PaddlePaddle | ⭐⭐⭐⭐ | ⭐⭐⭐ | 百度出品 |
| **YOLOR-Doc** | HuggingFace | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 轻量快速 |

**替换方式**：修改 `backend/config.py` 中的 `YOLO_MODEL_REPO` 和 `YOLO_MODEL_FILE`。

#### 2. OCR 识别模型（PaddleOCR-VL）

当前使用：`PaddleOCR-VL-1.6 Q4_K_M` via llama.cpp

可替换方案：

| 方案 | 精度 | 速度 | 部署难度 | 说明 |
|------|------|------|---------|------|
| **PaddleOCR-VL** | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 当前使用，多模态，效果好 |
| **Qwen2-VL** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 通义千问视觉模型，精度更高 |
| **PaddleOCR (传统)** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐ | 速度快，纯 Python |
| **EasyOCR** | ⭐⭐⭐ | ⭐⭐⭐ | ⭐ | 支持 80+ 语言 |
| **Tesseract** | ⭐⭐ | ⭐⭐⭐ | ⭐ | 开源老牌，中文效果一般 |

**量化级别选择**：
| 级别 | 文件大小 | 精度 | 显存占用 | 推荐场景 |
|------|---------|------|---------|---------|
| Q2_K | ~180 MB | ⭐⭐ | ~600 MB | 极低显存 |
| Q4_K_M | ~286 MB | ⭐⭐⭐⭐ | ~1.2 GB | **推荐，性价比最高** |
| Q5_K_M | ~350 MB | ⭐⭐⭐⭐⭐ | ~1.5 GB | 追求精度 |
| Q6_K | ~420 MB | ⭐⭐⭐⭐⭐ | ~1.8 GB | 最高精度 |

#### 3. 翻译模型（LLM）

当前支持 OpenAI 兼容 API，可灵活配置：

| 模型 | 翻译质量 | 速度 | 成本 | 说明 |
|------|---------|------|------|------|
| **GPT-4o** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 高 | 最佳翻译质量 |
| **DeepSeek-V3** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 低 | 国产模型，中文优秀 |
| **GPT-3.5-Turbo** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中 | 性价比高 |
| **Qwen3.5-4B（本地）** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 免费 | **推荐本地部署**，4B 小模型，性价比极高 |
| **Qwen2.5-72B** | ⭐⭐⭐⭐ | ⭐⭐⭐ | 低 | 可本地部署，大模型 |
| **其他本地模型** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 免费 | llama.cpp 运行本地 LLM |

在 Web 界面的 **"LLM 配置"** 面板中添加和切换翻译模型。

##### 推荐本地模型：Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled

这是一款基于 Qwen3.5-4B 的蒸馏模型，由 Claude 4.6 Opus 推理能力蒸馏而来，非常适合本地部署的翻译和文档处理任务。

| 量化级别 | 文件大小 | 显存占用 | 翻译质量 | 推荐场景 |
|---------|---------|---------|---------|---------|
| **Q4_K_M** | ~2.7 GB | ~3.5 GB | ⭐⭐⭐⭐ | **推荐，性价比最高**，4GB 显存即可 |
| Q5_K_M | ~3.3 GB | ~4.2 GB | ⭐⭐⭐⭐ | 追求精度，6GB 显存 |
| Q6_K | ~3.9 GB | ~4.8 GB | ⭐⭐⭐⭐⭐ | 最高精度，8GB 显存 |

**快速部署步骤：**

```bash
# 1. 下载模型
# Windows: 运行 download_qwen_model.bat
# Linux/macOS: 运行 download_qwen_model.sh

# 2. 启动 LLM 服务
# Windows: 运行 start_llm_llama_server.bat
# Linux:   运行 start_llm_llama_server.sh
# macOS:   运行 start_llm_llama_server_mac.sh

# 3. 在 Web 界面配置
#    类型: LlamaCPP / OpenAI 兼容
#    Base URL: http://127.0.0.1:8081/v1
#    模型名称: qwen3.5-4b
```

### 性能调优

#### 1. GPU 显存优化

```python
# backend/config.py
YOLO_DEVICE = "cuda"  # 使用 GPU
YOLO_IMG_SIZE = 1024  # 降低推理尺寸，速度↑ 精度↓
```

```batch
REM start_llama_server.bat
-ngl 99          # 全部层 GPU 加速
-c 2048          # 降低上下文长度，节省显存
```

#### 2. CPU 性能优化

```batch
REM start_llama_server.bat
set OMP_NUM_THREADS=8   # 设置等于物理核心数
-t 8                    # CPU 线程数
```

```python
# backend/config.py
YOLO_DEVICE = "cpu"
YOLO_IMG_SIZE = 1280    # CPU 推理可以用较大尺寸
```

#### 3. 解析速度优化

| 优化项 | 效果 | 代价 |
|--------|------|------|
| 降低 YOLO_IMG_SIZE 到 1024 | 布局检测速度 +30% | 小元素漏检率略增 |
| 禁用 Surya，使用坐标排序 fallback | 阅读排序速度 +200% | 多栏布局顺序可能错乱 |
| 提高扫描件检测阈值 | 减少不必要的 OCR | 可能漏判扫描件 |
| 关闭页眉页脚去重 | 解析速度 +5% | 可能有重复页眉页脚 |

#### 4. 批量处理优化

- 使用多进程/多线程并行处理多个文档
- 将 OCR 服务部署在独立机器，通过网络调用
- 使用 SSD 存储临时文件和数据库

---

## 📦 外部依赖项目

### AI 模型

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [YOLO26m Document Layout](https://huggingface.co/Armaggheddon/yolo26-document-layout) | Apache-2.0 | 文档布局检测 |
| [Surya](https://github.com/VikParuchuri/surya) | GPL-3.0 | 文档阅读顺序排序 |
| [PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF) | Apache-2.0 | 多模态 OCR 识别 |
| [Qwen3.5-4B-Claude-Distilled](https://huggingface.co/Jackrong/Qwen3.5-4B-Claude-4.6-Opus-Reasoning-Distilled-v2-GGUF) | Apache-2.0 | **推荐** 本地 LLM 翻译模型 |

### 推理框架

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | MIT | 大模型本地推理 |
| [Ultralytics YOLOv8](https://github.com/ultralytics/ultralytics) | AGPL-3.0 | 目标检测推理框架 |
| [PyTorch](https://pytorch.org/) | BSD-3 | 深度学习框架 |

### 核心库

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [PyMuPDF](https://github.com/pymupdf/PyMuPDF) | AGPL-3.0 | PDF 处理核心库 |
| [FastAPI](https://fastapi.tiangolo.com/) | MIT | Web API 框架 |
| [PaddlePaddle](https://github.com/PaddlePaddle/Paddle) | Apache-2.0 | 百度深度学习框架 |
| [PDF.js](https://github.com/mozilla/pdf.js) | Apache-2.0 | 浏览器端 PDF 渲染 |
| [Pillow](https://python-pillow.org/) | HPND | Python 图像处理 |
| [HuggingFace Hub](https://github.com/huggingface/huggingface_hub) | Apache-2.0 | 模型下载管理 |

### 前端库

| 项目 | 许可证 | 用途 |
|------|--------|------|
| [Font Awesome](https://fontawesome.com/) | CC BY 4.0 / MIT | 图标库 |

---

## 📁 项目结构

```
Prism PDF/
├── backend/
│   ├── api/
│   │   └── routes.py                  # 20+ API 端点
│   ├── services/
│   │   ├── parse_service.py           # 主解析流程编排
│   │   ├── pdf_service.py             # PDF 验证、转图、文本提取
│   │   ├── layout_service.py          # YOLO 布局检测 + 重叠过滤
│   │   ├── order_service.py           # Surya 阅读顺序排序
│   │   ├── ocr_service_vl.py          # llama.cpp OCR 客户端
│   │   ├── table_service.py           # 原生/扫描件表格提取
│   │   ├── picture_service.py         # 图片提取
│   │   ├── document_service.py        # 翻译、删除、重解析
│   │   ├── export_service.py          # HTML/Markdown 导出（含译文）
│   │   ├── llm_config_service.py      # LLM 配置管理
│   │   └── llm_service.py             # LLM 调用（翻译等）
│   ├── config.py                      # 全局配置
│   ├── database.py                    # SQLite 数据库操作
│   └── main.py                        # 应用入口
├── frontend/
│   ├── index.html                     # 主页面（三栏布局）
│   ├── detail.html                    # 文档详情页
│   ├── js/
│   │   ├── app.js                     # 列表页逻辑
│   │   ├── detail.js                  # 详情页逻辑
│   │   ├── export.js                  # 导出功能
│   │   └── llm-config.js              # LLM 配置管理
│   └── css/
│       └── style.css                  # 全局样式
├── models/                            # AI 模型文件（自动下载）
├── tmp/                               # 临时文件目录
├── useless/                           # 测试脚本和工具
├── data.db                            # SQLite 数据库（自动创建）
├── LICENSE                            # MIT 许可证
├── README.md                          # 本文档
├── setup.md                           # 详细环境配置指南
├── flow.md                            # 解析流程详细设计
├── hardware_requirements.md           # 硬件需求文档
├── requirements.txt                   # Python 依赖
│
│  🪟 Windows 脚本
├── setup.ps1                          # Windows 一键安装脚本
├── start_all.bat                      # Windows 一键启动脚本
└── start_llama_server.bat             # Windows OCR 服务启动脚本
│
│  🐧 Linux 脚本
├── setup.sh                           # Linux 一键安装脚本
├── start_all.sh                       # Linux 一键启动脚本
└── start_llama_server.sh              # Linux OCR 服务启动脚本
│
│  🍎 macOS Apple Silicon (M系列) 脚本
├── setup_mac.sh                       # macOS M系列 一键安装脚本
├── start_all_mac.sh                   # macOS M系列 一键启动脚本
└── start_llama_server_mac.sh          # macOS M系列 OCR 服务启动脚本
```

---

## 🤝 致谢

感谢以下开源项目和团队的贡献：

- [Ultralytics](https://github.com/ultralytics) — YOLO 目标检测框架
- [VikParuchuri](https://github.com/VikParuchuri) — Surya 文档分析工具
- [PaddlePaddle](https://github.com/PaddlePaddle) — 百度飞桨深度学习平台
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — 高效的本地大模型推理框架
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — 强大的 PDF 处理库
- [FastAPI](https://github.com/tiangolo/fastapi) — 现代化的 Python Web 框架

---

## 📄 License

本项目采用 [MIT License](LICENSE) 开源。

> ⚠️ 注意：部分外部依赖项目使用不同的开源许可证（如 AGPL-3.0、GPL-3.0 等），使用时请遵守相应许可证条款。
