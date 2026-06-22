# Prism PDF 解析流程设计文档

## 整体架构总览

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Web 前端                                       │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────────────────┐ │
│  │ 文档列表页   │  │ 详情页-缩略图 │  │ 详情页-解析结果编辑区         │ │
│  │ (index.html) │  │ + PDF 预览    │  │ (元素编辑/翻译/导出)          │ │
│  └──────────────┘  └───────────────┘  └───────────────────────────────┘ │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │ HTTP API
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      FastAPI 后端 (main.py)                             │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        API 路由层 (routes.py)                     │  │
│  │  /upload  /parse  /status  /results  /export  /translate  ...    │  │
│  └──────────────────────────────┬────────────────────────────────────┘  │
│                                 │                                        │
│  ┌──────────────────────────────▼────────────────────────────────────┐  │
│  │                     主解析调度层 (parse_service.py)               │  │
│  │   process_upload() → process_document() → _parse_page()          │  │
│  └────────┬───────────────────┬───────────────────┬────────────────┘  │
│           │                   │                   │                     │
│  ┌────────▼───────┐  ┌────────▼──────┐  ┌────────▼────────┐            │
│  │  PDF 基础服务  │  │  布局检测服务 │  │  阅读顺序服务   │            │
│  │ pdf_service.py │  │ layout_service│  │ order_service   │            │
│  └────────┬───────┘  └────────┬──────┘  └────────┬────────┘            │
│           │                   │                   │                     │
│  ┌────────▼───────┐  ┌────────▼──────┐  ┌────────▼────────┐            │
│  │  表格提取服务  │  │  图片提取服务 │  │  OCR 服务       │            │
│  │ table_service  │  │picture_service│  │ ocr_service_vl  │            │
│  └────────┬───────┘  └───────────────┘  └────────┬────────┘            │
│           │                                        │                    │
│  ┌────────▼───────┐                     ┌──────────▼────────┐           │
│  │   数据库层     │                     │ llama.cpp 服务器  │           │
│  │  database.py   │                     │ (外部独立进程)    │           │
│  └────────────────┘                     └───────────────────┘           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 一、文档上传与验证流程

```
用户上传 PDF
    │
    ▼
POST /api/upload
    │
    ▼
validate_pdf() [pdf_service.py:22]
    │
    ├─ 尝试用 PyMuPDF 打开 PDF
    │
    ├─ 检查是否加密
    │   ├─ 未加密 → 继续
    │   └─ 已加密 → 尝试空密码认证
    │       ├─ 认证成功 → 继续
    │       └─ 认证失败 → 返回错误，拒绝上传
    │
    ├─ 检查文件有效性
    │   └─ 损坏文件 → 返回错误
    │
    └─ 获取页数、文件大小等元信息
    │
    ▼
保存文件到 tmp/{uuid}.pdf
    │
    ▼
create_document() [database.py]
    ├─ 插入 pdf_documents 表
    │   ├─ 状态: uploaded
    │   ├─ 记录文件名、路径、大小、页数
    │   └─ 记录创建时间
    └─ 返回 document_id
    │
    ▼
返回 document_id 和 page_count
```

---

## 二、解析任务启动流程

```
POST /api/parse/{doc_id}
    │
    ▼
检查文档状态 (get_document)
    │
    ├─ status = processing → 返回 "已在处理中"
    ├─ status = completed  → 返回 "已完成"
    └─ status = uploaded / failed → 继续
    │
    ▼
更新文档状态为 processing
    │
    ▼
创建异步任务:
    asyncio.create_task(process_document(doc_id))
    │
    ▼
返回 "解析已开始"
```

> 💡 解析任务在后台异步执行，前端通过轮询 `/api/status/{doc_id}` 获取进度。

---

## 三、完整解析流程 (process_document)

### 阶段 1：初始化与页面预处理 (0% ~ 30%)

```
set_parse_progress(doc_id, "initializing", 5)
    │
    ▼
prepare_pages() [pdf_service.py]
    │
    ├─ 为每个页面执行:
    │   │
    │   ├─ convert_page_to_jpg()
    │   │   ├─ 按 DEFAULT_DPI (默认 200 DPI) 渲染页面
    │   │   ├─ 保存为 tmp/{doc_id}/page_{n}.jpg
    │   │   └─ 记录图片尺寸 (jpg_width, jpg_height)
    │   │
    │   ├─ save_single_page_pdf()
    │   │   └─ 提取单页 PDF，保存为 tmp/{doc_id}/page_{n}.pdf
    │   │
    │   └─ is_page_scanned()
    │       ├─ 提取页面文本 (PyMuPDF get_text())
    │       ├─ 文本字符数 < SCAN_TEXT_THRESHOLD (默认 10) → 可疑
    │       │   └─ 检查是否只有 1 张大图占页面面积 ≥ 80%
    │       │       ├─ 是 → is_scanned = true
    │       │       └─ 否 → is_scanned = false
    │       └─ 文本充足 → is_scanned = false
    │
    └─ 为每页创建 pdf_pages 数据库记录
    │
    ▼
更新文档状态为 pages_ready
```

### 阶段 2：批量布局检测 (30% ~ 50%)

```
detect_layout_batch() [layout_service.py]
    │
    ├─ 首次调用时:
    │   ├─ 从 HuggingFace 下载 YOLO26m 模型
    │   │   └─ 模型仓库: Armaggheddon/yolo26-document-layout
    │   ├─ 加载模型到 YOLO_DEVICE (cuda / cpu)
    │   └─ 全局单例缓存
    │
    ├─ 收集所有页面图片路径
    │
    ├─ 批量推理:
    │   └─ model.predict(images, imgsz=YOLO_IMG_SIZE, conf=0.25)
    │
    ├─ 解析检测结果 (每页):
    │   ├─ 支持 11 类元素:
    │   │   ├─ Title (标题)
    │   │   ├─ Section-header (章节标题)
    │   │   ├─ Text (正文段落)
    │   │   ├─ List-item (列表项)
    │   │   ├─ Table (表格)
    │   │   ├─ Picture (图片)
    │   │   ├─ Formula (公式)
    │   │   ├─ Caption (图/表标题)
    │   │   ├─ Footnote (脚注)
    │   │   ├─ Page-header (页眉)
    │   │   └─ Page-footer (页脚)
    │   │
    │   ├─ 每个检测结果包含:
    │   │   ├─ bbox: [x0, y0, x1, y1] (像素坐标)
    │   │   ├─ confidence: 0.0 ~ 1.0
    │   │   └─ class_id: 类别 ID
    │   │
    │   └─ 保存原始检测数据用于调试
    │
    └─ remove_overlapping_elements() → 重叠过滤
        │
        ├─ 计算所有检测框两两之间的 IoU (交并比)
        │
        ├─ 包含关系处理 (IoU ≥ 0.9 且面积差大):
        │   └─ 保留较大的、非 Text 类型的
        │
        ├─ 部分重叠处理 (IoU ≥ 0.5):
        │   └─ 非 Text 类型优先于 Text 类型
        │
        └─ 同类型重叠:
            └─ 保留 confidence 高的
```

### 阶段 3：阅读顺序排序 (50% ~ 55%)

```
assign_reading_order_batch() [order_service.py]
    │
    ├─ 首次调用时:
    │   ├─ 加载 Surya Order 模型
    │   │   └─ 模型仓库: vikp/surya_order
    │   └─ 加载到 SURYA_ORDER_DEVICE (cuda / cpu)
    │
    ├─ 准备输入数据:
    │   └─ 每页: 页面图片 + 所有 bbox
    │
    ├─ batch_ordering() → Surya 模型推理
    │   └─ 输出每个 bbox 的阅读顺序位置 (position)
    │
    ├─ 匹配 YOLO 检测框与 Surya 结果
    │   └─ 使用 IoU 匹配，找到最接近的阅读顺序
    │
    ├─ 失败降级 fallback 排序:
    │   └─ 按 bbox 的 (y1, x1) 坐标排序
    │       ├─ 先从上到下 (y1 升序)
    │       └─ 同一行从左到右 (x1 升序)
    │
    └─ 重新编号 reading_order 从 0 开始连续编号
```

### 阶段 4：逐页内容解析 (55% ~ 95%)

对每个页面调用 `_parse_page()`：

```
┌─ detect_garbled_text() → 中文乱码检测
│   ├─ 统计页面中文字符总数
│   ├─ 统计乱码字符 (0xfffd, 控制字符等)
│   └─ 乱码比例 ≥ GARBLE_CJK_THRESHOLD (30%) → 强制 OCR
│
├─ 确定 force_ocr = is_scanned or has_garbled
│
├─ 收集待处理任务 (批处理优化):
│   ├─ Text/Title/Section-header/List-item/Caption/Footnote + force_ocr → OCR 任务
│   ├─ Formula → 公式 OCR 任务
│   └─ Table + force_ocr → 表格 OCR 任务
│
├─ 批量执行 OCR:
│   └─ ocr_batch() → 一次性发送所有区域到 llama.cpp 服务器
│
├─ 遍历每个元素，按类型提取内容:
│   │
│   ├─ [Text / Section-header / List-item / Title / Caption / Footnote]
│   │   ├─ force_ocr = true  → 使用 OCR 结果
│   │   └─ force_ocr = false → extract_text_in_region()
│   │       ├─ 坐标转换: JPG 像素 → PDF 点坐标 (× 72/DPI)
│   │       └─ PyMuPDF 提取区域内文本
│   │
│   ├─ [Formula 公式]
│   │   ├─ force_ocr = true  → 使用 OCR 结果
│   │   └─ force_ocr = false → ocr_formula() 调用 VL 模型
│   │       └─ Prompt: "Please recognize this formula and output LaTeX format:"
│   │
│   ├─ [Picture 图片]
│   │   └─ extract_picture()
│   │       ├─ 裁剪 bbox 区域
│   │       ├─ 保存为 tmp/{doc_id}/img/{page}_{idx}.png
│   │       └─ content 存储图片相对路径
│   │
│   └─ [Table 表格] ← 最复杂，详见 第四节
│       ├─ 跨页表格检测 (详见第五节)
│       ├─ force_ocr = true  → extract_table_from_scanned()
│       └─ force_ocr = false → extract_table_from_native()
│
├─ deduplicate_header_footer() → 页眉页脚去重
│   ├─ 基于位置 IoU 和内容相似度比较所有页面
│   ├─ Page-header / Page-footer 重复内容去重
│   └─ 保留内容更长、置信度更高的版本
│
├─ mark_header_footer() → 页眉页脚区域标记
│   ├─ 识别页眉类型元素 (page-header, header)，记录最大 y1 作为 header_y_threshold
│   ├─ 识别页脚类型元素 (page-footer, footer, footnote)，记录最小 y0 作为 footer_y_threshold
│   ├─ 将阈值保存到 pdf_pages 表 (header_y_threshold, footer_y_threshold)
│   └─ 标记位于阈值范围内的其他元素:
│       ├─ 左上角 y0 < header_y_threshold → header_footer_mark = "header"
│       └─ 右下角 y1 > footer_y_threshold → header_footer_mark = "footer"
│
└─ 批量写入 page_elements 数据库表
```

### 阶段 5：图片描述批量生成 (96%)

```
所有页面解析完成后，批量执行图片描述:
    │
    ▼
_describe_images_for_document(doc_id)
    │
    ├─ 遍历所有页面的 Picture/Figure 元素
    │   ├─ 跳过已有 image_description 的元素
    │   ├─ 跳过 header_footer_mark = "header" 或 "footer" 的元素
    │   └─ 跳过图片文件不存在的元素
    │
    ├─ 对每个需要描述的图片:
    │   ├─ 调用 describe_image_silent() → Vision LLM 生成描述
    │   └─ 保存 image_description 到 page_elements 表
    │
    └─ 日志记录描述完成数量
```

### 阶段 6：完成 (97% ~ 100%)

```
更新 pdf_documents 状态为 completed
    │
    ▼
清除内存中的进度缓存
    │
    ▼
前端轮询 /api/status 检测到 status = completed
    │
    ▼
用户可:
  - 查看解析结果
  - 人工编辑校正
  - 翻译内容
  - 导出 (HTML / Markdown / PDF)
```

---

## 四、表格提取详细流程

### 4.1 原生 PDF 表格提取 (extract_table_from_native)

```
坐标转换: JPG 像素坐标 → PDF 点坐标
    │   公式: pdf_coord = jpg_coord × (72 / DEFAULT_DPI)
    │
    ▼
扩大检测区域 (避免边界截断):
    │   左右各 +3pt，顶部 +3pt，底部 +20pt
    │
    ▼
_find_valid_table() → 多级策略检测
    │
    ├─ Strategy 1: "lines" (宽松线条检测)
    │   └─ table = page.find_tables(strategy="lines")
    │
    ├─ Strategy 2: "lines_strict" (严格线条检测)
    │   └─ table = page.find_tables(strategy="lines_strict")
    │
    └─ Strategy 3: "text" (基于文本排列检测)
        └─ table = page.find_tables(strategy="text")
    │
    ├─ 每级策略检测后验证有效性:
    │   ├─ 行数 ≥ 3 且 列数 ≥ 2
    │   ├─ 非空单元格比例 ≥ 30%
    │   └─ 包含数字 或 行数 ≥ 5
    │
    └─ 返回第一个有效表格，全部失败返回 None
    │
    ▼
_table_to_html() → 生成带 rowspan/colspan 的 HTML
    │
    ├─ 构建 covered 矩阵 (row × col)，标记已输出单元格
    │
    ├─ 遍历 rows[row].cells[col]:
    │   ├─ 检查右侧连续 None → colspan = n
    │   ├─ 检查下侧连续 None → rowspan = m
    │   ├─ 标记 covered[row:row+m, col:col+n]
    │   └─ 生成 <td rowspan="m" colspan="n"> 内容 </td>
    │
    ├─ 检测表头行:
    │   ├─ 使用 table.header 属性
    │   └─ 若无 header，默认第一行为表头 <th>
    │
    └─ HTML 特殊字符转义 (&, <, >, ", ')
    │
    ▼
同时生成 Markdown (fallback)
    └─ content_format = "markdown"
```

### 4.2 扫描件表格提取 (extract_table_from_scanned)

```
调用 llama.cpp 服务器
    │   Prompt: "Table Recognition: Please recognize this table..."
    │
    ▼
VL 模型输出结构化标签格式示例:
    │   <fcel>项目名称<fcel>2017年<fcel>2018年<nl>
    │   <fcel>收入<fcel>100万元<fcel>150万元<nl>
    │   <ucel><fcel>支出<fcel>50万元<fcel>80万元<nl>
    │
    │   标签说明:
    │     <fcel>  - 单元格开始
    │     <ucel>  - 跨行合并标记 (该单元格继承上方内容)
    │     <nl>    - 换行
    │
    ▼
_parse_fcel_structured_to_html() → 解析标签生成 HTML
    │
    ├─ 按 <nl> 分割行
    │
    ├─ 按 <fcel> 分割单元格
    │
    ├─ 检测跨行合并:
    │   ├─ <ucel> 出现在行首
    │   ├─ 计算连续跨行的 rowspan
    │   └─ 更新之前行对应单元格的 rowspan 属性
    │
    ├─ 检测表格行组 (连续 ≥2 行的表格行)
    │
    └─ 生成 HTML table 结构
    │
    ▼
同时生成 Markdown 版本 (fallback)
```

---

## 五、跨页表格检测与合并流程

```
解析当前页时，维护 last_table_info:
    ├─ page_number: 来源页码
    ├─ col_count: 列数
    ├─ last_row_content: 最后一行内容
    ├─ cross_page_group: 跨页组 ID (NULL = 非跨页)
    └─ at_page_bottom: 表格是否在页面底部 70% 区域
    │
    ▼
解析下一页第一个 Table 元素时:
    │
    ├─ 检查是否在页面顶部 30% 区域
    ├─ 检查前一页表格是否在页面底部 70% 区域
    ├─ 检查列数是否匹配 (相差 ≤ 1)
    ├─ 检查当前表格前是否有正文内容
    └─ 检查内容特征 (数字行、空单元格模式)
    │
    ├─ 匹配成功 → 判定为跨页表格:
    │   ├─ force_no_header = True (当前页表格不识别表头)
    │   ├─ 继承 cross_page_group，若为 NULL 则新建
    │   └─ 回溯更新前一表格的 cross_page_group
    │
    └─ 匹配失败 → 独立表格，cross_page_group = NULL
    │
    ▼
导出时合并 (_merge_cross_page_tables):
    ├─ 按 cross_page_group 分组所有页面的表格
    ├─ 提取每组所有 <tr> 行 (跳过重复表头)
    └─ 合并到第一个表格中，移除后续表格
```

---

## 六、OCR 服务调用流程 (ocr_service_vl.py)

```
ocr_region(image_path, bbox, prompt="OCR:")
    │
    ▼
_crop_and_save_image()
    ├─ 按 bbox 裁剪图片区域
    └─ 保存为临时 PNG 文件
    │
    ▼
_call_llama_server(prompt, tmp_image_path)
    │
    ├─ 图片 base64 编码 (data:image/png;base64,...)
    │
    ├─ 发送 POST 请求到 LLAMA_SERVER_URL
    │   默认: http://127.0.0.1:8080/v1/chat/completions
    │
    ├─ 请求体格式 (OpenAI 兼容):
    │   {
    │     "model": "PaddleOCR-VL",
    │     "messages": [{
    │       "role": "user",
    │       "content": [
    │         {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    │         {"type": "text", "text": prompt}
    │       ]
    │     }],
    │     "temperature": 0,
    │     "max_tokens": 500,
    │     "stream": false
    │   }
    │
    └─ 超时 180 秒
    │
    ▼
解析返回结果:
    ├─ result["choices"][0]["message"]["content"]
    └─ _parse_fcel_to_text() → 去除 <fcel> 等标签，返回纯文本
    │
    ▼
删除临时 PNG 文件
    │
    ▼
返回识别文本
```

> 💡 **批量优化**: `ocr_batch()` 一次收集多个区域，串行发送请求（避免并发导致 llama.cpp OOM）。

---

## 七、翻译流程

```
用户点击翻译 (元素 / 页面 / 文档)
    │
    ▼
获取活跃 LLM 配置
    └─ llm_config_service.get_active_config()
    │
    ▼
翻译单元素 translate_element():
    │
    ├─ 收集待翻译文本:
    │   ├─ Picture 类型 → 若已有 image_description 则使用；否则提示先生成图片描述
    │   └─ 其他类型 → content 字段
    │
    ├─ translate_text(text, target_language) [llm_service.py]
    │   └─ 调用 LLM API (OpenAI 兼容格式)
    │
    └─ 保存结果: update_element(translated_content=...)
    │
    ▼
翻译单页 / 整文档 translate_page() / translate_document():
    │
    ├─ 获取页面/文档所有元素
    │
    ├─ translate_page_content(elements, target_language)
    │   │
    │   ├─ 将元素内容分段 (每段 ≤ 1000 字符)
    │   │
    │   ├─ 构造批量翻译 Prompt:
    │   │   请将以下文本翻译成 {target_language}。
    │   │   文本用 [N] 标记，按编号返回结果。
    │   │   [0] 第一段文本...
    │   │   [1] 第二段文本...
    │   │
    │   ├─ 调用 LLM API
    │   │
    │   └─ _parse_translated_result()
    │       └─ 解析 [N] 标记，匹配原文与译文
    │
    └─ 批量保存 translated_content
```

---

## 八、人工校正与导出流程

### 8.1 元素编辑

```
PUT /api/elements/{element_id}
    │
    ├─ 更新 content (识别内容)
    ├─ 更新 translated_content (译文)
    ├─ 更新 element_type (元素类型)
    └─ 更新 reading_order (阅读顺序)
```

### 8.2 阅读顺序重排

```
PUT /api/pages/{page_id}/elements/reorder
    │
    └─ 接收 element_order 列表 (按阅读顺序排列的 element_id)
    └─ 批量更新每个元素的 reading_order
```

### 8.3 Surya 重新排序

```
PUT /api/pages/{page_id}/surya-reorder
    │
    └─ 对该页重新调用 Surya Order 模型排序
    └─ 更新所有元素的 reading_order
```

### 8.4 添加新元素

```
POST /api/pages/{page_id}/elements
    │
    ├─ 前端框选 bbox (在图片上拖拽)
    ├─ 用户选择 element_type
    ├─ 用户输入 content
    └─ reading_order 自动追加到末尾
```

### 8.5 导出功能总览

#### 导出 API 端点列表

```
整文档导出:
  GET /api/documents/{doc_id}/export/html                      → 原文 HTML
  GET /api/documents/{doc_id}/export/markdown                  → 原文 Markdown
  GET /api/documents/{doc_id}/export/html-zip                  → 每页 HTML ZIP
  GET /api/documents/{doc_id}/export/translated/html           → 译文 HTML
  GET /api/documents/{doc_id}/export/translated/markdown       → 译文 Markdown
  GET /api/documents/{doc_id}/export/translated/html-zip       → 译文每页 HTML ZIP
  GET /api/documents/{doc_id}/export/rag-html                  → RAG 友好格式（单HTML，已去页眉页脚）
  GET /api/documents/{doc_id}/export/rag-html-zip              → RAG 友好分页格式（ZIP，每页单独HTML）

单页导出:
  GET /api/pages/{page_id}/export/html                         → 单页原文 HTML
  GET /api/pages/{page_id}/export/markdown                     → 单页原文 Markdown
  GET /api/pages/{page_id}/export/translated/html              → 单页译文 HTML
  GET /api/pages/{page_id}/export/translated/markdown          → 单页译文 Markdown
  GET /api/pages/{page_id}/export/rag-html                     → 单页 RAG 友好格式
  GET /api/pages/{page_id}/pdf                                 → 单页原 PDF 文件
  GET {jpg_path}                                               → 单页原 PDF 渲染图片
```

#### 前端导出菜单结构

**列表页 & 详情页右上角（整文档导出）:**
```
导出
├── 原文
│   ├── 整本 HTML
│   ├── 整本 Markdown
│   └── 每页 HTML ZIP
├── 译文
│   ├── 译文 HTML
│   ├── 译文 Markdown
│   └── 译文每页 HTML ZIP
└── RAG 友好
    ├── RAG 友好格式（单HTML，已去页眉页脚）
    └── RAG 友好分页格式（ZIP，每页单独HTML）
```

**详情页单页导出:**
```
导出
├── 原文
│   ├── 原文 HTML
│   ├── 原文 Markdown
│   ├── 原文 PDF
│   └── 原文 PDF 图片
├── 译文
│   ├── 译文 HTML
│   └── 译文 Markdown
└── RAG 友好
    └── RAG 单页友好格式
```

### 8.6 通用导出流程

```
GET /api/documents/{doc_id}/export/html
    │
    ├─ get_parse_results() → 获取所有页面和元素
    │
    ├─ _merge_cross_page_tables() → 合并跨页表格
    │
    ├─ 按页面遍历:
    │   └─ 按 reading_order 排序元素
    │   └─ element_to_html() 按类型转换:
    │       ├─ Title          → <h1 style="color: #dc143c;">
    │       ├─ Section-header → <h2>
    │       ├─ Table          → 直接输出内容 (已为 HTML)
    │       ├─ Picture        → <img> (有 image_description 时用 figure-container 包裹并显示 caption)
    │       ├─ Formula        → <div class="formula">
    │       ├─ List-item      → <li>
    │       └─ 其他文本类型   → <p>
    │
    ├─ build_html_document() → 添加 CSS 样式
    │
    └─ 返回 Response，Content-Disposition: attachment
```

**译文导出流程相同**，只需在 element_to_html() 和 generate_page_markdown() 中设置 `use_translated=True`，优先使用 translated_content 字段。图片元素的 caption 在译文模式下优先使用 translated_content（即图片描述的译文）。

### 8.7 RAG 友好格式导出

```
前端点击 "RAG 友好格式" 或 "RAG 友好分页格式" 菜单项:
    │
    ├─ RAG 友好格式 (GET /api/documents/{doc_id}/export/rag-html):
    │   │
    │   ├─ generate_rag_single_html()
    │   │   ├─ 遍历所有页面
    │   │   ├─ _filter_rag_elements() → 排除 header_footer_mark=header/footer 及 Page-header/Page-footer 元素
    │   │   └─ 按 generate_document_html 方式合并为单个 HTML
    │   │
    │   └─ 文件名: {原文件名}_RAG友好.html
    │
    └─ RAG 友好分页格式 (GET /api/documents/{doc_id}/export/rag-html-zip):
        │
        ├─ generate_rag_per_page_zip()
        │   ├─ 遍历所有页面
        │   ├─ _filter_rag_elements() → 排除页眉页脚相关元素
        │   ├─ 每页单独生成 HTML (generate_page_html)，文件名 page_001.html / page_002.html ...
        │   └─ 所有 HTML 打包为 ZIP 返回
        │
        └─ 文件名: {原文件名}_RAG友好_按页.zip
```

**RAG 友好格式特性**:
- 自动移除所有页眉页脚（包括 Page-header / Page-footer 类型元素和被 `header_footer_mark` 标记的元素）
- 保留图片描述作为 caption（同普通导出）
- 保留跨页表格合并逻辑
- 支持整文档导出和单页导出

**单页 RAG 友好格式**:
- 端点: `GET /api/pages/{page_id}/export/rag-html`
- 逻辑: `generate_rag_single_page_html()` → 过滤页眉页脚元素后调用 `generate_page_html()`

---

## 九、数据库表结构与关系

```
pdf_documents (文档表)
    │
    │  字段:
    │  ├─ id                    INTEGER PRIMARY KEY
    │  ├─ filename              TEXT      (系统生成的唯一文件名)
    │  ├─ original_filename     TEXT      (用户上传的原始文件名)
    │  ├─ file_path             TEXT      (PDF 存储路径)
    │  ├─ file_size             INTEGER   (字节)
    │  ├─ page_count            INTEGER
    │  ├─ status                TEXT      (uploaded/processing/completed/failed)
    │  ├─ error_message         TEXT
    │  ├─ created_at            TIMESTAMP
    │  └─ updated_at            TIMESTAMP
    │
    └── has many → pdf_pages (通过 document_id 外键关联)

pdf_pages (页面表)
    │
    │  字段:
    │  ├─ id                    INTEGER PRIMARY KEY
    │  ├─ document_id           INTEGER   (FK → pdf_documents.id)
    │  ├─ page_number           INTEGER
    │  ├─ width                 REAL      (PDF 点坐标宽度)
    │  ├─ height                REAL      (PDF 点坐标高度)
    │  ├─ jpg_width             INTEGER   (渲染图片像素宽度)
    │  ├─ jpg_height            INTEGER   (渲染图片像素高度)
    │  ├─ jpg_path              TEXT      (渲染 JPG 路径)
    │  ├─ single_pdf_path       TEXT      (单页 PDF 路径)
    │  ├─ is_scanned            BOOLEAN   (是否为扫描件)
    │  ├─ is_ordered            BOOLEAN   (阅读顺序是否已排序)
    │  ├─ header_y_threshold    REAL      (页眉区域 y 阈值，低于此值为页眉区)
    │  ├─ footer_y_threshold    REAL      (页脚区域 y 阈值，高于此值为页脚区)
    │  ├─ status                TEXT
    │  └─ error_message         TEXT
    │
    └── has many → page_elements (通过 page_id 外键关联)

page_elements (文档元素表)
    │
    │  字段:
    │  ├─ id                    INTEGER PRIMARY KEY
    │  ├─ page_id               INTEGER   (FK → pdf_pages.id)
    │  ├─ element_type          TEXT      (11种类型)
    │  ├─ bbox_x0 / bbox_y0     REAL      (JPG像素坐标)
    │  ├─ bbox_x1 / bbox_y1     REAL
    │  ├─ confidence            REAL      (0.0~1.0)
    │  ├─ reading_order         INTEGER   (阅读顺序，从0开始)
    │  ├─ content               TEXT      (识别内容)
    │  ├─ content_format        TEXT      (html/markdown/text)
    │  ├─ image_description     TEXT      (图片描述，Vision LLM 生成)
    │  ├─ translated_content    TEXT      (译文内容)
    │  ├─ header_footer_mark    TEXT      (页眉页脚标记: "header" / "footer" / NULL)
    │  ├─ cross_page_group      TEXT      (跨页表格组ID，NULL为非跨页)
    │  └─ created_at            TIMESTAMP
```

---

## 十、关键配置项

| 配置项 | 默认值 | 说明 | 位置 |
|--------|--------|------|------|
| `YOLO_MODEL_REPO` | `"Armaggheddon/yolo26-document-layout"` | YOLO 模型 HuggingFace 仓库 | config.py |
| `YOLO_MODEL_FILE` | `"yolo26m_doc_layout.pt"` | YOLO 模型文件名 | config.py |
| `YOLO_IMG_SIZE` | `1280` | YOLO 推理图片尺寸 (px) | config.py |
| `YOLO_DEVICE` | `"cuda"` | YOLO 推理设备: cuda / cpu | config.py |
| `SURYA_ORDER_MODEL_REPO` | `"vikp/surya_order"` | Surya 模型仓库 | config.py |
| `SURYA_ORDER_DEVICE` | `"cuda"` | Surya 推理设备 | config.py |
| `DEFAULT_DPI` | `200` | PDF 转图片分辨率 | pdf_service.py |
| `SCAN_TEXT_THRESHOLD` | `10` | 扫描件检测: 文本字符数阈值 | config.py |
| `SCAN_IMAGE_AREA_RATIO` | `0.8` | 扫描件检测: 单张图片占页面面积比 | config.py |
| `GARBLE_CJK_THRESHOLD` | `0.3` | 中文乱码比例阈值 | parse_service.py |
| `TABLE_STRATEGY` | `"lines_strict"` | 原生表格检测默认策略 | config.py |
| `HF_MIRROR_URL` | `"https://hf-mirror.com"` | HuggingFace 国内镜像 | config.py |
| `LLAMA_SERVER_URL` | `"http://127.0.0.1:8080"` | llama.cpp OCR 服务地址 | ocr_service_vl.py |
| `TMP_DIR` | `./tmp` | 临时文件目录 | config.py |
| `MODELS_DIR` | `./models` | AI 模型文件目录 | config.py |
| `DB_PATH` | `./data.db` | SQLite 数据库路径 | config.py |
