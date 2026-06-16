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
create_page() → 为每页创建数据库记录
    │
    ▼
更新文档状态为 pages_ready
```

### 阶段 2：批量布局检测 (30% - 50%)

```
detect_layout_batch() [layout_service.py:289]
    ├─ 首次调用时下载/加载 YOLO26m 模型
    │   ├─ 从 HuggingFace 下载 yolo26m_doc_layout.pt
    │   └─ 支持 CUDA 加速（如果可用）
    │
    ├─ 批量推理所有页面图片 (imgsz=1280)
    │
    ├─ 解析检测结果：
    │   ├─ 11 类元素：Title, Section-header, Text, List-item,
    │   │             Table, Picture, Formula, Caption, Footnote,
    │   │             Page-header, Page-footer
    │   ├─ 每个检测结果包含：bbox, confidence, class_id
    │   └─ 保存原始检测数据用于调试
    │
    └─ remove_overlapping_elements() → 过滤重叠元素
        ├─ 计算 IoU (交并比)
        ├─ 包含关系处理：保留大的、非 Text 的
        ├─ 重叠处理：非 Text 优先于 Text
        └─ 同类型：保留 confidence 高的
```

### 阶段 3：阅读顺序排序 (50% - 55%)

```
assign_reading_order_batch() [order_service.py:195]
    ├─ 加载 Surya Order 模型（首次调用自动下载）
    │
    ├─ batch_ordering() → 批量处理所有页面
    │   └─ Surya 模型输出每个 bbox 的阅读顺序 position
    │
    ├─ 匹配 YOLO 检测框与 Surya 结果
    │   └─ 使用 IoU 匹配，找到最接近的阅读顺序
    │
    ├─ 失败降级：fallback 排序
    │   └─ 按 bbox 的 y1, x1 坐标排序（从上到下，从左到右）
    │
    └─ 重新编号 reading_order 从 0 开始
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
        export_document_html() [routes.py:377]
        └─ _merge_cross_page_tables()
            ├─ 按 cross_page_group 分组
            ├─ 提取所有 <tr> 行
            └─ 合并到第一个表格中
```

## 六、OCR 服务调用流程 (ocr_service_vl.py)

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
    ├─ 请求体格式（OpenAI 兼容）：
    │   {
    │     "model": "PaddleOCR-VL-1.6.Q4_K_M.gguf",
    │     "messages": [{
    │       "role": "user",
    │       "content": [
    │         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}},
    │         {"type": "text", "text": "OCR:"}
    │       ]
    │     }],
    │     "temperature": 0,
    │     "max_tokens": 500
    │   }
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

### 7.3 添加新元素

```
POST /api/pages/{page_id}/elements
    ├─ 前端框选 bbox
    ├─ 选择 element_type
    ├─ 输入 content
    └─ 自动分配 reading_order（追加到末尾）
```

### 7.4 导出 HTML

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
| `YOLO_DEVICE` | `"cpu"` | YOLO 推理设备，设为 `"cuda"` 启用 GPU |
| `YOLO_IMG_SIZE` | `1280` | YOLO 推理图片尺寸，越大越精确但越慢 |
| `SCAN_TEXT_THRESHOLD` | `10` | 扫描件检测文本字符数阈值 |
| `SCAN_IMAGE_AREA_RATIO` | `0.8` | 扫描件图片占页面比例阈值 |
| `GARBLE_CJK_THRESHOLD` | `0.3` | 中文乱码比例阈值 |
| `LLAMA_SERVER_URL` | `"http://127.0.0.1:8080"` | llama.cpp OCR 服务器地址 |
| `DEFAULT_DPI` | `200` | PDF 转图片的 DPI |
