# Prism PDF 整体解析流程

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Web 前端 (index.html)                      │
│  ┌─────────────┐  ┌───────────────┐  ┌───────────────────────────────┐ │
│  │  缩略图导航 │  │  PDF 预览区   │  │  解析结果编辑区               │ │
│  └─────────────┘  └───────────────┘  └───────────────────────────────┘ │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │ HTTP API
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          FastAPI 后端 (main.py)                        │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        API 路由层 (routes.py)                     │  │
│  │  /upload, /parse, /status, /results, /export, /documents         │  │
│  └─────────────────────────────────────┬─────────────────────────────┘  │
│                                        │                                │
│  ┌─────────────────────────────────────▼─────────────────────────────┐  │
│  │                     主解析调度层 (parse_service.py)               │  │
│  │  process_upload() → process_document() → _parse_page()           │  │
│  └──────────┬───────────────────┬───────────────────┬────────────────┘  │
│             │                   │                   │                   │
│  ┌──────────▼───────┐  ┌────────▼──────┐  ┌────────▼────────┐          │
│  │  PDF 基础服务    │  │  布局检测服务 │  │  阅读顺序服务   │          │
│  │  pdf_service.py  │  │ layout_service│  │ order_service   │          │
│  └──────────┬───────┘  └────────┬──────┘  └────────┬────────┘          │
│             │                   │                   │                   │
│  ┌──────────▼───────┐  ┌────────▼──────┐  ┌────────▼────────┐          │
│  │  表格提取服务    │  │  图片提取服务 │  │  OCR 服务       │          │
│  │ table_service.py │  │picture_service│  │ ocr_service_vl  │          │
│  └──────────┬───────┘  └───────────────┘  └────────┬────────┘          │
│             │                                        │                   │
│  ┌──────────▼───────┐                     ┌──────────▼────────┐          │
│  │   数据库层       │                     │ llama.cpp 服务器  │          │
│  │  database.py     │                     │ (外部独立进程)    │          │
│  └──────────────────┘                     └───────────────────┘          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 一、文档上传与验证流程

```
用户上传 PDF
    │
    ▼
POST /api/upload
    │
    ▼
validate_pdf() [pdf_service.py:22]
    ├─ 尝试打开 PDF
    ├─ 检查是否加密 → 若加密尝试空密码认证
    │   └─ 仍加密 → 返回错误，拒绝上传
    ├─ 检查文件有效性 → 损坏文件返回错误
    └─ 获取页数
    │
    ▼
create_document() [database.py:85]
    ├─ 生成唯一文件名保存到 tmp/ 目录
    ├─ 记录文档元数据（文件名、路径、大小、页数）
    └─ 状态: uploaded → validated
    │
    ▼
返回 document_id 和 page_count
```

## 二、解析任务启动流程

```
POST /api/parse/{doc_id}
    │
    ▼
检查文档状态
    ├─ 若 processing → 返回"已在处理中"
    ├─ 若 completed → 返回"已完成"
    │
    ▼
创建异步任务 process_document()
    │
    ▼
返回"解析已开始"
```

## 三、完整解析流程 (process_document)

### 阶段 1：初始化与页面预处理 (0% - 30%)

```
set_parse_progress(doc_id, "initializing", 5)
    │
    ▼
更新文档状态为 processing
    │
    ▼
prepare_pages() [pdf_service.py:134]
    ├─ 为每个页面执行：
    │   ├─ convert_page_to_jpg() → 200 DPI 转 JPG
    │   ├─ save_single_page_pdf() → 提取单页 PDF
    │   └─ is_page_scanned() → 扫描件检测
    │       ├─ 提取页面文本
    │       ├─ 文本 < 10 字符 → 可能是扫描件
    │       │   └─ 检查是否只有 1 张大图占比 ≥ 80%
    │       └─ 返回 is_scanned 标记
    │
    ▼
create_page() → 为每页创建数据库记录（含 is_scanned 标记）
    │
    ▼
更新文档状态为 pages_ready
```

### 阶段 2：模型加载与 VRAM 管理 (30% - 35%)

```
加载 YOLO 模型到显存
    ├─ _get_model() [layout_service.py:197]
    ├─ 检测 CUDA 可用性
    └─ 加载到 GPU（或 CPU fallback）
    │
    ▼
检查 VRAM 剩余资源
    ├─ check_vram_available() [order_service.py:15]
    ├─ 默认需要 ≥ 800MB 空闲显存
    │
    ├─ 显存充足 → 加载 Surya 排序模型
    │   ├─ _get_ordering_model_and_processor()
    │   ├─ 加载到 CUDA（或 CPU fallback）
    │   └─ surya_available = True
    │
    └─ 显存不足 → 跳过 Surya 加载
        ├─ 记录警告日志
        └─ surya_available = False
           （所有页面将使用 fallback 排序，标记 is_ordered=0）
```

### 阶段 3：按类型批量处理 (35% - 55%)

```
将页面分为扫描页和非扫描页两类：

┌─── 非扫描页（YOLO + Surya 流程）───────────────────────────────────┐
│                                                                     │
│  detect_layout_batch() [layout_service.py:308]                     │
│      ├─ 批量推理所有非扫描页图片                                    │
│      ├─ 11 类元素检测 + 重叠过滤                                    │
│      └─ 返回每页元素列表（含 bbox, confidence）                     │
│                                                                     │
│  assign_reading_order_batch() [order_service.py:203]                │
│      ├─ 若 surya_available → Surya 模型批量排序                     │
│      └─ 否则 → _fallback_reading_order() 坐标排序                   │
│           （标记这些页面 is_ordered=0）                               │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘

┌─── 扫描页（PaddleOCR-VL + Surya 流程）────────────────────────────┐
│                                                                     │
│  扫描页在 _parse_page() 阶段处理：                                  │
│      ├─ Step A: YOLO 检测 Picture/Figure 元素                       │
│      ├─ Step B: PaddleOCR-VL 全页 Table Recognition 解析             │
│      ├─ Step C: 合并 Picture + OCR 结果                             │
│      │   ├─ 若 surya_available → Surya 模型排序 (is_ordered=1)      │
│      │   └─ 否则 → fallback 坐标排序 (is_ordered=0)                 │
│      └─ 保存元素到数据库                                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 阶段 4：逐页内容解析 (55% - 95%)

对每个页面调用 `_parse_page()`：

```
┌─ 检测乱码 detect_garbled_text()
│   ├─ 统计中文字符总数
│   ├─ 统计乱码字符（0xfffd, 控制字符等）
│   └─ 乱码比例 ≥ 30% → 强制 OCR
│
├─ 确定 force_ocr = is_scanned or has_garbled
│
├─ 收集待处理任务（批处理优化）：
│   ├─ Text 类 + force_ocr → OCR 任务
│   ├─ Formula → 公式 OCR 任务
│   └─ Table + force_ocr → 表格 OCR 任务
│
├─ 批量执行 OCR（调用 llama.cpp 服务器）：
│   └─ ocr_batch() → 一次性发送所有区域
│
├─ 遍历每个元素提取内容：
│   │
│   ├─ [Text / Section-header / List-item / Title 等]
│   │   ├─ force_ocr → 使用 OCR 结果
│   │   └─ 否则 → extract_text_in_region() 从 PDF 提取
│   │
│   ├─ [Formula]
│   │   ├─ force_ocr → 使用公式 OCR 结果
│   │   └─ 否则 → ocr_formula() 调用 VL 模型
│   │
│   ├─ [Picture]
│   │   └─ extract_picture() → 裁剪保存为 PNG
│   │
│   └─ [Table] ← 最复杂，详见表格提取流程
│       ├─ 跨页表格检测
│       ├─ force_ocr → extract_table_from_scanned()
│       └─ 否则 → extract_table_from_native()
│
├─ deduplicate_header_footer() → 页眉页脚去重
│   ├─ 基于位置 IoU 和内容相似度
│   └─ 保留内容更长的版本
│
└─ 批量写入数据库 create_element()
    └─ 更新 is_ordered 标记
```

### 阶段 5：完成 (95% - 100%)

```
更新文档状态为 completed
    │
    ▼
清除进度缓存
    │
    ▼
前端轮询 /api/status 检测到完成
    │
    ▼
用户可查看、编辑、导出结果
    │
    ├─ 未排序页面（is_ordered=0）显示"重排序"按钮
    └─ 点击"重排序"→ POST /api/pages/{page_id}/resort
        └─ 使用 Surya 模型重新排序该页元素
```

## 四、表格提取详细流程

### 4.1 原生 PDF 表格提取 (extract_table_from_native)

```
坐标转换：JPG 像素 → PDF 点坐标 (× 72/200)
    │
    ▼
扩大检测区域（避免边界截断）：
    左右 +3pt，顶部 +3pt，底部 +20pt
    │
    ▼
_find_valid_table() 多级策略检测：
    ├─ Strategy 1: "lines" - 宽松线条检测
    ├─ Strategy 2: "lines_strict" - 严格线条检测
    └─ Strategy 3: "text" - 基于文本排列检测
    │
    ├─ 每级策略检测后验证：
    │   ├─ 行数 ≥ 3，列数 ≥ 2
    │   ├─ 非空单元格 ≥ 30%
    │   └─ 包含数字或行数 ≥ 5
    │
    └─ 返回第一个有效表格
    │
    ▼
_table_to_html() → 生成带 rowspan/colspan 的 HTML：
    ├─ 构建 covered 矩阵标记已输出单元格
    ├─ 遍历 rows[row].cells[col]
    ├─ 右侧连续 None → colspan
    ├─ 下侧连续 None → rowspan
    ├─ 检测表头行（通过 table.header 或第一行）
    └─ HTML 特殊字符转义
    │
    ▼
生成 Markdown（fallback）→ table.to_markdown()
```

### 4.2 扫描件表格提取 (extract_table_from_scanned)

```
调用 llama.cpp 服务器，提示词 "Table Recognition:"
    │
    ▼
VL 模型输出结构化标签格式：
    <fcel>项目<fcel>2017年<nl>
    <fcel>收入<fcel>100万<nl>
    <ucel><fcel>支出<fcel>50万<nl>
    │
    ▼
_parse_fcel_structured_to_html() → 解析标签：
    ├─ <nl> → 行分隔
    ├─ <fcel> → 单元格开始
    ├─ <ucel> → 跨行合并标记
    ├─ 检测表格行组（连续 ≥2 行表格行）
    ├─ 计算 rowspan（检测跨行标记）
    └─ 生成 HTML table
    │
    ▼
同时生成 Markdown 版本（fallback）
```

## 五、跨页表格检测与合并流程

```
解析前一页时记录 last_table_info:
    ├─ col_count - 列数
    ├─ last_row - 最后一行内容
    ├─ cross_page_group - 跨页组 ID
    └─ at_page_bottom - 是否在页面底部
    │
    ▼
解析当前页第一个表格时：
    ├─ 检查是否在页面顶部 30%
    ├─ 检查前一表格是否在页面底部 70%
    ├─ 检查列数是否匹配（相差 ≤1）
    ├─ 检查当前页表格前是否有正文内容
    └─ 检查内容特征（数字行、空单元格）
    │
    ├─ 匹配成功 → force_no_header=True（不识别表头）
    │   ├─ 继承 cross_page_group 或新建
    │   └─ 回溯更新前一表格的 cross_page_group
    │
    └─ 导出时合并：
        export_document_html() [routes.py]
        └─ _merge_cross_page_tables()
            ├─ 按 cross_page_group 分组
            ├─ 提取所有 <tr> 行
            └─ 合并到第一个表格中
```

## 六、OCR 服务调用流程 (ocr_service_vl.py)

### 6.1 调用流程

```
ocr_region(image_path, bbox)
    │
    ▼
_crop_and_save_image() → 裁剪 bbox 区域为临时 PNG
    │
    ▼
_call_llama_server("OCR:", tmp_path)
    ├─ 图片 base64 编码
    ├─ 发送到 http://127.0.0.1:8080/v1/chat/completions
    ├─ 请求体格式（OpenAI Chat Completions 兼容）
    └─ 超时 180 秒
    │
    ▼
_parse_fcel_to_text() → 解析 <fcel> 标签为纯文本
    │
    ▼
删除临时文件
    │
    ▼
返回识别文本
```

### 6.2 PaddleOCR-VL API 接口格式

PaddleOCR-VL 通过 llama.cpp 服务器提供 OpenAI Chat Completions 兼容接口。

**接口地址**: `POST http://127.0.0.1:8080/v1/chat/completions`

**请求格式**:
```json
{
  "model": "PaddleOCR-VL-1.6.Q4_K_M.gguf",
  "messages": [{
    "role": "user",
    "content": [
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,{BASE64_IMAGE}"}},
      {"type": "text", "text": "{PROMPT}"}
    ]
  }],
  "temperature": 0,
  "max_tokens": 8000,
  "stream": false
}
```

**提示词**:
| 提示词 | 用途 | 输出格式 |
|--------|------|----------|
| `OCR:` | 纯文本 OCR | 每行一个文本行 |
| `Table Recognition:` | 表格识别 | `<fcel>/<nl>/<ucel>/<lcel>` 结构化标签 |
| 手动输入 | 自定义提示 | 由模型生成 |

**响应格式**:
```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "<fcel>...识别结果..."
    },
    "finish_reason": "stop"
  }],
  "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
}
```

### 6.3 兼容接口替换方案

由于 PaddleOCR-VL 使用 OpenAI Chat Completions 兼容协议，可以替换为任何支持多模态视觉输入的兼容 API 服务：

**可替换的兼容接口**:
1. **vLLM + 多模态模型**: 如 Qwen2-VL、InternVL 等，启动时指定 `--served-model-name`
2. **Ollama**: 支持 `POST /api/chat` 或 OpenAI 兼容模式 `POST /v1/chat/completions`
3. **其他 OpenAI 兼容服务**: 如 LM Studio、LocalAI 等支持的视觉模型

**替换步骤**:
1. 修改 `config.py` 中的 `LLAMA_SERVER_URL` 指向新服务地址
2. 修改 `LLAMA_MODEL_NAME` 为对应模型名称
3. 确保新服务支持 `image_url` 格式的多模态输入（base64 编码）
4. 确保输出格式保持一致：OCR 输出纯文本行，Table Recognition 输出 `<fcel>` 标签

**注意事项**:
- 不同模型的提示词格式可能不同，需根据模型要求调整 `PROMPT`
- 表格识别功能依赖 `<fcel>/<nl>/<ucel>` 标签输出格式，替换模型需保证相同输出
- 如只使用纯 OCR 功能，任何视觉模型均可替换，无需标签格式对齐

## 七、人工校正与导出流程

### 7.1 元素编辑

```
PUT /api/elements/{element_id}
    ├─ 更新 content
    ├─ 更新 element_type
    └─ 更新 reading_order
```

### 7.2 阅读顺序重排

```
PUT /api/pages/{page_id}/elements/reorder
    └─ 按提供的 element_order 列表批量更新 reading_order
```

### 7.3 智能重排序（Surya）

```
POST /api/pages/{page_id}/resort
    ├─ 获取当前页所有元素及其 bbox
    ├─ 调用 Surya 排序模型重新分配阅读顺序
    ├─ 更新数据库中所有元素的 reading_order
    ├─ 更新 is_ordered=1
    └─ 返回排序后的元素列表
```

### 7.4 添加新元素

```
POST /api/pages/{page_id}/elements
    ├─ 前端框选 bbox
    ├─ 选择 element_type
    ├─ 输入 content
    └─ 自动分配 reading_order（追加到末尾）
```

### 7.5 导出 HTML

```
GET /api/documents/{doc_id}/export/html
    ├─ 合并跨页表格
    ├─ 按 reading_order 排序元素
    ├─ 按元素类型转换为 HTML 标签：
    │   ├─ Title → <h1 style="color: #dc143c;">
    │   ├─ Section-header → <h2>
    │   ├─ Table → 直接输出 HTML table
    │   ├─ Picture → <img>
    │   ├─ Formula → <div class="formula">
    │   └─ Text → <p>
    └─ 添加 CSS 样式，返回 attachment 下载
```

### 7.6 导出按页 HTML ZIP

```
GET /api/documents/{doc_id}/export/html-zip
    ├─ 为每页生成独立 HTML 文件（文件名：页码号.html）
    ├─ 合并跨页表格
    ├─ 打包为 ZIP 文件下载
    └─ ZIP 内结构：page_1.html, page_2.html, ...
```

## 八、数据库表结构关系

```
pdf_documents (文档表)
    │  id (PK)
    │  filename, original_filename, file_path, file_size
    │  page_count, status, error_message
    │  created_at, updated_at
    │
    ├─ has many → pdf_pages
    │      │  id (PK)
    │      │  document_id (FK)
    │      │  page_number, width, height
    │      │  jpg_width, jpg_height, is_scanned
    │      │  is_ordered (0=未排序/fallback, 1=已Surya排序)
    │      │  jpg_path, single_pdf_path
    │      │  status, error_message
    │      │
    │      └─ has many → page_elements
    │             id (PK)
    │             page_id (FK)
    │             element_type (11 种类型)
    │             bbox_x0, bbox_y0, bbox_x1, bbox_y1
    │             confidence, reading_order
    │             content, content_format
    │             cross_page_group (跨页表格组 ID)
    │             created_at
```

## 关键配置点

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `YOLO_DEVICE` | `"cuda"` | YOLO 推理设备，设为 `"cpu"` 使用 CPU |
| `SURYA_DEVICE` | `"cuda"` | Surya 排序模型设备，设为 `"cpu"` 使用 CPU |
| `YOLO_IMG_SIZE` | `1280` | YOLO 推理图片尺寸，越大越精确但越慢 |
| `SURYA_VRAM_MIN_MB` | `800` | 加载 Surya 模型所需最小空闲显存 (MB) |
| `SCAN_TEXT_THRESHOLD` | `10` | 扫描件检测文本字符数阈值 |
| `SCAN_IMAGE_AREA_RATIO` | `0.8` | 扫描件图片占页面比例阈值 |
| `GARBLE_CJK_THRESHOLD` | `0.3` | 中文乱码比例阈值 |
| `LLAMA_SERVER_URL` | `"http://127.0.0.1:8080"` | llama.cpp OCR 服务器地址（OpenAI 兼容） |
| `LLAMA_MODEL_NAME` | `"PaddleOCR-VL-1.6.Q4_K_M.gguf"` | OCR 模型名称 |
| `DEFAULT_DPI` | `200` | PDF 转图片的 DPI |
