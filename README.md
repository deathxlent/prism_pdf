# Prism PDF - PDF 高精度解析系统

一个功能完整的本地 PDF 解析系统，支持原生 PDF 和扫描件 PDF 的高精度解析，集成多种 AI 模型进行布局分析、内容提取和结构化输出。

## ✨ 功能特性

### 📄 核心解析功能

| 功能 | 描述 | 技术方案 |
|------|------|----------|
| **PDF 上传管理** | 支持 PDF 文件上传、验证、加密检测、列表管理、删除 | PyMuPDF |
| **扫描件检测** | 自动识别扫描版 PDF 和乱码文本，触发 OCR 流程 | 文本量检测 + 图片占比分析 |
| **布局分析** | 11 类文档元素智能识别和定位 | YOLO26m (Document Layout) |
| **阅读顺序** | 智能确定元素阅读顺序，支持多栏布局 | Surya Order Model |
| **文本提取** | 原生 PDF 直接提取，扫描件 OCR 识别 | PyMuPDF + PaddleOCR-VL |
| **表格提取** | 支持跨行跨列的结构化表格，自动检测跨页表格 | PyMuPDF find_tables + PaddleOCR-VL |
| **公式识别** | 数学公式识别，输出 LaTeX 格式 | PaddleOCR-VL |
| **图片提取** | 自动提取文档中的图片并保存 | PyMuPDF |
| **跨页表格合并** | 智能识别并合并跨页的表格 | 启发式列数匹配 + 内容分析 |

### 🎯 支持的元素类型

系统支持识别 11 种文档元素类型：

- **Title** - 文档标题
- **Section-header** - 章节标题
- **Text** - 正文文本
- **List-item** - 列表项
- **Table** - 表格（支持 rowspan/colspan）
- **Picture** - 图片
- **Formula** - 数学公式
- **Caption** - 图表标题
- **Footnote** - 脚注
- **Page-header** - 页眉（自动去重）
- **Page-footer** - 页脚（自动去重）

### 🖥️ 前端交互功能

- **三栏式界面**：缩略图导航 + PDF 预览 + 解析结果
- **实时进度**：解析进度实时显示
- **人工校正**：支持编辑元素内容、类型、阅读顺序
- **手动添加**：可手动框选添加新元素
- **标注查看**：查看 YOLO 模型原始检测标注图
- **多视图切换**：文档列表/书架视图
- **多格式导出**：单页/整文档 HTML、Markdown 导出

### 🔧 技术架构

**后端技术栈**：
- FastAPI - Web 框架
- PyMuPDF - PDF 处理
- Ultralytics YOLO - 布局检测
- Surya - 阅读顺序排序
- PaddleOCR - 传统 OCR（备用）
- PaddleOCR-VL (GGUF) + llama.cpp - 多模态 OCR
- SQLite + aiosqlite - 数据存储

**前端技术栈**：
- 原生 HTML/CSS/JavaScript
- PDF.js - PDF 渲染
- Font Awesome - 图标库

## 📦 项目结构

```
Prism PDF/
├── backend/
│   ├── api/
│   │   └── routes.py          # API 路由定义
│   ├── services/
│   │   ├── pdf_service.py     # PDF 基础处理（转图、验证、文本提取）
│   │   ├── layout_service.py  # 布局检测（YOLO）
│   │   ├── order_service.py   # 阅读顺序排序（Surya）
│   │   ├── ocr_service.py     # 传统 OCR（PaddleOCR）
│   │   ├── ocr_service_vl.py  # 多模态 OCR（PaddleOCR-VL + llama.cpp）
│   │   ├── table_service.py   # 表格提取与结构化
│   │   ├── picture_service.py # 图片提取
│   │   └── parse_service.py   # 主解析流程编排
│   ├── config.py              # 配置参数
│   ├── database.py            # 数据库操作
│   └── main.py                # 应用入口
├── frontend/
│   ├── index.html             # 主页面
│   ├── app.js                 # 前端逻辑
│   └── style.css              # 样式文件
├── models/                    # 模型文件目录（自动创建）
├── tmp/                       # 临时文件目录（自动创建）
├── requirements.txt           # Python 依赖
├── start_llama_server.bat     # llama.cpp 服务器启动脚本
├── setup.md                   # 详细配置指南
├── flow.md                    # 解析流程图
└── hardware_requirements.md   # 硬件需求说明
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 2. 启动 llama.cpp OCR 服务器（可选，用于扫描件）

```bash
# 编辑 start_llama_server.bat 中的路径，然后运行
start_llama_server.bat
```

### 3. 启动主服务

```bash
python -m backend.main
```

### 4. 访问应用

打开浏览器访问：`http://localhost:8000`

## 📚 相关文档

- **[setup.md](setup.md)** - 详细环境配置指南，包含 llama.cpp 编译、模型下载、启动脚本
- **[flow.md](flow.md)** - 整体解析流程详解
- **[hardware_requirements.md](hardware_requirements.md)** - 硬件需求说明（CPU/GPU 版本）

## ⚙️ 工作原理

### 解析流程概览

1. **上传验证**：检查 PDF 是否加密、损坏
2. **页面预处理**：每页转 JPG、提取单页 PDF、扫描件检测
3. **批量布局检测**：YOLO 模型检测所有页面的元素位置和类型
4. **阅读顺序排序**：Surya 模型确定元素阅读顺序
5. **内容提取**：
   - 原生 PDF：直接提取文本，PyMuPDF 提取表格
   - 扫描件/乱码：PaddleOCR-VL 进行 OCR 和表格识别
6. **跨页表格合并**：检测并合并跨页的表格
7. **结果存储**：所有元素存入 SQLite 数据库
8. **人工校正**：Web 界面支持编辑和导出

### 智能特性

- **乱码检测**：自动检测中文乱码，触发 OCR 流程
- **页眉页脚去重**：自动识别并移除重复的页眉页脚
- **重叠元素过滤**：基于 IoU 和类型优先级过滤重叠检测
- **跨页表格检测**：列数匹配 + 内容特征识别接续表格

## 📝 输出格式

### 导出格式

- **HTML**：保留完整格式，支持表格 rowspan/colspan，推荐使用
- **Markdown**：轻量格式，表格跨行跨列信息会丢失
- **单页 PDF**：可导出单页原始 PDF

### 数据库结构

- `pdf_documents` - 文档元数据
- `pdf_pages` - 页面信息
- `page_elements` - 元素详情（类型、位置、内容、阅读顺序）

## 🔧 配置说明

### 关键配置项 (`backend/config.py`)

```python
YOLO_DEVICE = "cpu"           # YOLO 运行设备: "cpu" 或 "cuda"
YOLO_IMG_SIZE = 1280          # YOLO 推理图片尺寸
SCAN_TEXT_THRESHOLD = 10      # 扫描件检测文本阈值
SCAN_IMAGE_AREA_RATIO = 0.8   # 扫描件图片占比阈值
GARBLE_CJK_THRESHOLD = 0.3    # 中文乱码检测阈值
TABLE_STRATEGY = "lines_strict"  # 表格检测策略
```

### llama.cpp 服务配置 (`ocr_service_vl.py`)

```python
LLAMA_SERVER_URL = "http://127.0.0.1:8080"
LLAMA_MODEL_NAME = "PaddleOCR-VL-1.6.Q4_K_M.gguf"
```

## 📄 License

本项目仅供学习和研究使用。

## 🤝 致谢

- [YOLO26m Document Layout](https://huggingface.co/Armaggheddon/yolo26-document-layout) - 文档布局检测模型
- [Surya](https://github.com/VikParuchuri/surya) - 文档阅读顺序排序
- [PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF) - 多模态 OCR 模型
- [llama.cpp](https://github.com/ggml-org/llama.cpp) - 大模型推理框架
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) - PDF 处理库
