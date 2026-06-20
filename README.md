# Prism PDF — 本地高精度 PDF 解析系统

> 一个功能完整的本地 PDF 解析系统，集成多种 AI 模型，实现文档布局分析、内容提取、表格识别和结构化输出。

---

## ✨ 功能特性

### 📄 核心解析能力

| 能力 | 说明 | 技术方案 |
|------|------|----------|
| **PDF 上传管理** | 上传、验证（加密/损坏检测）、列表、删除 | PyMuPDF |
| **扫描件自动检测** | 识别扫描版 PDF 和乱码文本，自动切换 OCR 流程 | 文本量 + 图片占比 + CJK 乱码检测 |
| **11 类文档布局分析** | Title / Section-header / Text / List-item / Table / Picture / Formula / Caption / Footnote / Page-header / Page-footer | YOLO26m (Document Layout) |
| **智能阅读顺序** | 支持多栏、复杂布局的阅读顺序 | Surya Order Model + fallback 坐标排序 |
| **文本提取** | 原生 PDF 直接提取 + 扫描件 PaddleOCR-VL 识别 | PyMuPDF / PaddleOCR-VL (GGUF) |
| **结构化表格提取** | 支持 rowspan/colspan、跨页表格自动检测与合并 | PyMuPDF find_tables / PaddleOCR-VL |
| **数学公式识别** | 公式区域识别并输出 LaTeX 格式 | PaddleOCR-VL |
| **图片提取** | 自动提取文档中的图片并保存为 PNG | PyMuPDF |
| **跨页表格合并** | 智能合并跨页断开的表格，处理空单元格吸收 | 启发式列匹配 + 内容分析 + rowspan/colspan 扩展 |
| **页眉页脚去重** | 基于位置 IoU 和内容相似度自动去重 | 重叠检测 + 序列匹配 |

### 🖥️ 前端交互

- **三栏式界面**：缩略图导航 + PDF 预览 + 解析结果编辑区
- **实时进度**：解析进度百分比 + 阶段提示
- **人工校正**：编辑元素内容、类型、阅读顺序
- **手动添加**：鼠标框选添加新元素
- **Surya 重排序**：对任意页面调用 AI 重排阅读顺序
- **布局标注查看**：YOLO 模型原始检测标注图
- **多视图切换**：列表视图 / 书架卡片视图
- **多格式导出**：单页 / 整文档 HTML、Markdown、单页 PDF
- **批量导出**：全文档各页分别导出为 ZIP 压缩包
- **LLM 配置管理**：在 UI 中配置和管理多个 LLM 提供商

---

## 🧱 技术架构

```
┌─────────────────────────────────────────────────────┐
│                    Web 前端                          │
│  原生 HTML/CSS/JS · PDF.js · Font Awesome           │
└────────────────────────┬────────────────────────────┘
                         │ HTTP API
┌────────────────────────▼────────────────────────────┐
│              FastAPI 后端 (uvicorn)                   │
│  ┌────────────────────────────────────────────────┐ │
│  │              API 路由层 (routes.py)             │ │
│  │  /upload /parse /status /results /export /edit │ │
│  └──────────────────┬─────────────────────────────┘ │
│                     │                                │
│  ┌──────────────────▼─────────────────────────────┐ │
│  │              解析编排服务                        │ │
│  │  parse_service.py / pdf_service.py              │ │
│  └──────┬────────────┬────────────┬────────────────┘ │
│         │            │            │                   │
│  ┌──────▼─────┐ ┌───▼────┐ ┌────▼─────────┐          │
│  │ 布局检测    │ │阅读顺序│ │ 内容提取     │          │
│  │ YOLO       │ │ Surya  │ │ PyMuPDF/OCR  │          │
│  └────────────┘ └────────┘ └────┬─────────┘          │
│                                  │                    │
│  ┌────────────┐  ┌───────────┐ ┌▼────────────┐       │
│  │ 表格提取   │  │ 图片提取  │ │ llama.cpp   │       │
│  │ table_     │  │ picture_  │ │ OCR 服务     │       │
│  │ service    │  │ service   │ │ (外部进程)   │       │
│  └────────────┘  └───────────┘ └─────────────┘       │
│                                                       │
│  ┌────────────────────────────────────────────────┐  │
│  │          SQLite 数据库 (aiosqlite)              │  │
│  │  pdf_documents · pdf_pages · page_elements     │  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 技术栈明细

**后端**
- FastAPI + uvicorn（Web 框架）
- PyMuPDF（PDF 处理）
- Ultralytics YOLO（文档布局检测）
- Surya（阅读顺序排序）
- PaddleOCR-VL via llama.cpp（多模态 OCR）
- SQLite + aiosqlite（数据持久化）
- HuggingFace Hub（模型自动下载）

**前端**
- 原生 HTML5 / CSS3 / JavaScript
- PDF.js（PDF 渲染）
- Font Awesome 6（图标）

**推理**
- llama-server 外部进程（OpenAI 兼容 API）
- GGUF 量化模型（Q4_K_M）

---

## 📦 项目结构

```
Prism PDF/
├── backend/
│   ├── api/
│   │   └── routes.py                  # 17 个 API 端点
│   ├── services/
│   │   ├── pdf_service.py             # PDF 验证、转图、文本提取
│   │   ├── layout_service.py          # YOLO 布局检测 + 重叠过滤
│   │   ├── order_service.py           # Surya 阅读顺序排序 + fallback
│   │   ├── ocr_service_vl.py          # llama.cpp OCR 客户端
│   │   ├── ocr_service.py             # 传统 PaddleOCR（备用）
│   │   ├── table_service.py           # 原生/扫描件表格提取
│   │   ├── scanned_parse_service.py   # 扫描件整页解析引擎
│   │   ├── picture_service.py         # 图片提取
│   │   ├── parse_service.py           # 主解析流程编排
│   │   └── llm_config_service.py      # LLM 配置管理
│   ├── config.py                      # 全局配置
│   ├── database.py                    # SQLite CRUD
│   └── main.py                        # 应用入口
├── frontend/
│   ├── index.html                     # 主页面 (三栏布局)
│   ├── app.js                         # 前端逻辑 (~2000 行)
│   └── style.css                      # 样式
├── models/                            # AI 模型文件（自动下载）
├── tmp/                               # 临时文件目录
├── data.db                            # SQLite 数据库
├── requirements.txt                   # Python 依赖
├── llm_config.yaml                    # LLM 配置（YAML）
├── llm_config_local.json              # LLM 配置（本地覆盖）
├── start_all.bat                      # 一键启动脚本
├── start_llama_server.bat             # llama.cpp 启动脚本
├── setup.md                           # 详细环境配置指南
├── flow.md                            # 解析流程图与设计文档
└── hardware_requirements.md           # 硬件需求说明
```

---

## 🚀 快速开始

### 环境要求

- Python 3.10 ~ 3.12
- NVIDIA GPU + CUDA 12+（推荐，OCR 需要 GPU 加速）
- 16GB+ 内存
- 50GB+ 磁盘空间（含模型文件和依赖）

### 安装

```bash
# 1. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 3. 启动 OCR 服务（解析扫描件必需）
#    编辑 start_llama_server.bat 配置路径，然后运行
start_llama_server.bat

# 4. 启动主服务
python -m backend.main

# 5. 访问 http://localhost:8000
```

> 首次启动会自动下载 YOLO 和 Surya 模型（约 600MB）。
> 详见 [setup.md](setup.md) 完整配置指南。

---

## ⚙️ 解析流程

```
上传 PDF → 验证(加密/损坏) → 页面预处理
  ├─ 每页转 JPG (200 DPI)
  ├─ 提取单页 PDF
  └─ 扫描件检测 (文本量 + 图片占比)
       │
       ▼
布局检测 [YOLO26m] → 11 类元素定位 → 重叠过滤
       │
       ▼
阅读顺序 [Surya Order] → 多栏布局排序 → GPU不足时用坐标 fallback
       │
       ▼
逐页内容提取:
  ├─ 原生 PDF 页 → PyMuPDF 提取文本 + find_tables
  ├─ 扫描件页   → PaddleOCR-VL 整页 Table Recognition
  └─ 跨页表格检测 → 列匹配 + 空单元格吸收 + rowspan/colspan 更新
       │
       ▼
结果存储 (SQLite) → Web 编辑校正 → 导出 (HTML/Markdown/PDF)
```

---

## 📊 数据库模型

| 表 | 字段 | 说明 |
|----|------|------|
| `pdf_documents` | id, filename, file_size, page_count, status, error_message | 文档元数据 |
| `pdf_pages` | id, document_id, page_number, jpg_path, is_scanned, is_ordered | 页面信息 |
| `page_elements` | id, page_id, element_type, bbox, confidence, reading_order, content, cross_page_group | 文档元素 |

---

## 🧩 建议的新功能 & 优化方向

### 新功能候选

| 优先级 | 功能 | 说明 |
|--------|------|------|
| 🔴 **高** | **全文搜索** | 跨文档搜索解析后的文本内容，sqlite FTS5 即可实现 |
| 🔴 **高** | **批量上传** | 一次上传多个 PDF，批量排队解析 |
| 🔴 **高** | **DOCX 导出** | 将解析结果导出为 Word 文档，保留格式 |
| 🟡 **中** | **AI 摘要/关键词** | 调用 LLM 生成文档摘要和关键词标签 |
| 🟡 **中** | **文档标签/收藏** | 用户自定义标签体系和收藏夹 |
| 🟡 **中** | **暗色模式** | 前端 CSS 变量主题切换 |
| 🟡 **中** | **水印检测/去除** | 检测并标记文档中的水印区域 |
| 🟡 **中** | **试卷/表单识别** | 针对试卷、表格类文档的特殊优化模式 |
| 🟢 **低** | **文档版本管理** | 同一 PDF 多次解析的版本对比 |
| 🟢 **低** | **用户认证系统** | 多用户登录权限管理 |
| 🟢 **低** | **REST API 文档** | 自动生成 Swagger/OpenAPI 文档增强 |
| 🟢 **低** | **图表数据提取** | 从柱状图/折线图中提取数据 |

### 性能优化

| 问题 | 优化方案 |
|------|----------|
| OCR 逐区域串行处理 | 并行化 OCR 请求（当前每个区域串行 `ocr_batch` 实为串行循环） |
| YOLO + Surya 阻塞主线程 | 两者已在 `asyncio.to_thread` 中运行，但 Surya 推理加全局锁可优化 |
| 200 DPI 固定分辨率 | 支持自适应 DPI（根据 PDF 清晰度自动选择 150/200/300 DPI） |
| 大文档内存溢出 | 分页流式处理，避免一次性加载所有页面 |
| 模型重复下载 | 支持离线模式，缓存模型文件 |

### 代码质量提升

| 问题 | 建议 |
|------|------|
| `routes.py` 3 份重复 HTML 生成代码 | 抽取为公共 HTML 渲染模块 |
| `_parse_page` 600+ 行 | 拆分为原生流/扫描件流两个独立函数 |
| 配置硬编码 | 支持 .env 文件 + 环境变量覆盖 |
| 零测试覆盖 | 添加 pytest 单元测试 + API 集成测试 |
| 前端无构建工具 | 引入 Vite + TypeScript（可选）|
| 全局锁粒度粗 | 模型级 + 页面级精细锁 |

### 架构演进

- **Docker 容器化**：一键部署，消除环境依赖问题
- **消息队列**：引入 Redis/Celery 管理异步解析任务，支持任务优先级
- **分布式 OCR**：多 GPU 节点并行 OCR，支持大规模批量处理
- **WebSocket 推送**：替代前端轮询，实时推送解析进度

---

## 📝 导出格式

| 格式 | 支持范围 | 特点 |
|------|----------|------|
| **HTML** | 单页 / 整文档 / ZIP 批量 | 保留 rowspan/colspan，推荐 |
| **Markdown** | 单页 | 轻量，表格跨行列信息丢失 |
| **单页 PDF** | 单页 | 原始 PDF 页面下载 |

---

## 📚 文档索引

| 文档 | 内容 |
|------|------|
| [setup.md](setup.md) | 完整环境配置指南（llama.cpp 编译、模型下载、GPU/CPU 配置） |
| [flow.md](flow.md) | 解析流程详细设计说明 |
| [hardware_requirements.md](hardware_requirements.md) | 硬件需求分析与配置建议 |

---

## 📄 License

本项目仅供学习和研究使用。

## 🤝 致谢

- [YOLO26m Document Layout](https://huggingface.co/Armaggheddon/yolo26-document-layout) — 文档布局检测模型
- [Surya](https://github.com/VikParuchuri/surya) — 文档阅读顺序排序
- [PaddleOCR-VL](https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF) — 多模态 OCR 模型
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — 大模型推理框架
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) — PDF 处理库
