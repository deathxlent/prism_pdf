"""
扫描版 PDF 直接解析服务
=======================

核心思路:
    对于扫描版 PDF 页面，不再使用 YOLO 做布局检测 + Surya 做阅读顺序 + 逐区域 OCR，
    而是直接整页调用 PaddleOCR-VL 1.6 的 "Table Recognition:" 提示词，
    一次性获取包含表格在内的所有内容的结构化标签 (<fcel>/<nl>/<ucel>)。

优势:
    1. 省掉 YOLO 和 Surya 两个大模型的加载和推理时间
    2. 表格识别更准确（Table Recognition 提示词专门针对表格优化）
    3. 流程大大简化，一次调用完成所有内容提取

说明:
    整页 Table Recognition 不会返回元素的精确 bbox 坐标，
    所以这里采用启发式方法估算 bbox，保证前端可视化和数据一致性。
"""

import logging
import re
import difflib
from html import escape
from pathlib import Path
from backend.services import ocr_service_vl as ocr_service

logger = logging.getLogger(__name__)


def normalize_text(s: str) -> str:
    """标准化文本，便于比较"""
    if not s:
        return ""
    s = s.replace('\u3000', ' ')  # 全角空格
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def parse_scanned_pages_batch(page_info_list: list[dict]) -> list[list[dict]]:
    """
    批量解析扫描版 PDF 页面。

    Args:
        page_info_list: 页面信息列表，每个元素包含:
            - jpg_path: 页面 JPG 图片路径
            - page_width: JPG 图片宽度（像素）
            - page_height: JPG 图片高度（像素）

    Returns:
        每页的元素列表
    """
    logger.info(f"[Scanned Parse Batch] Starting batch parse for {len(page_info_list)} scanned pages")
    
    results = []
    for idx, page_info in enumerate(page_info_list):
        jpg_path = page_info["jpg_path"]
        page_width = page_info["page_width"]
        page_height = page_info["page_height"]
        logger.info(f"[Scanned Parse Batch] Processing page {idx + 1}/{len(page_info_list)}: {Path(jpg_path).name}")
        try:
            elements = parse_scanned_page_full(jpg_path, page_width, page_height)
            results.append(elements)
        except Exception as e:
            logger.error(f"[Scanned Parse Batch] Failed to parse page {idx + 1}: {e}")
            results.append([])
    
    logger.info(f"[Scanned Parse Batch] Batch parse completed: {len(results)} pages")
    return results


def parse_scanned_page_full(jpg_path: str, page_width: int, page_height: int,
                            table_force_no_header_map: dict = None,
                            prev_table_last_row_data: list = None) -> list[dict]:
    """
    直接调用 PaddleOCR-VL Table Recognition 解析整页扫描件图片。

    Args:
        jpg_path: 页面 JPG 图片路径
        page_width: JPG 图片宽度（像素）
        page_height: JPG 图片高度（像素）
        table_force_no_header_map: 字典 {table_block_index: bool}，指定哪些表格块需要强制不识别表头
        prev_table_last_row_data: 前一页接续表格的最后一行数据（用于本页第一行空单元格合并判断）

    Returns:
        元素列表，每个元素包含:
            - element_type: Text / Section-header / Table / Title / Page-header / Page-footer
            - bbox: (x0, y0, x1, y1) 估算坐标
            - confidence: 置信度 (固定 0.8)
            - reading_order: 阅读顺序 (0, 1, 2, ...)
            - content: 文本内容 或 HTML 表格
            - content_format: markdown / html
    """
    logger.info(f"[Scanned Parse] Full-page Table Recognition for: {Path(jpg_path).name}")

    # Step 1a: 先调用 "OCR:" 拿纯文本（先调用避免被 Table Recognition 缓存截断）
    plain_ocr_lines = []
    extra_header_content = ""
    extra_footer_content = ""
    try:
        ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
        if ocr_plain and ocr_plain.strip():
            plain_ocr_lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]

            # --- 提取页眉 ---
            found_header_idx = -1
            for i in range(min(3, len(plain_ocr_lines))):
                line = plain_ocr_lines[i]
                if re.match(r'^\s*\d+\s*$', line):
                    continue
                if 5 < len(line) < 100:
                    found_header_idx = i
                    break

            if found_header_idx >= 0:
                header_line = plain_ocr_lines[found_header_idx]
                if len(header_line) > 80:
                    header_line = header_line[:80]
                extra_header_content = header_line
            elif plain_ocr_lines and 5 < len(plain_ocr_lines[0]) < 80:
                extra_header_content = plain_ocr_lines[0]

            # --- 提取页脚 ---
            for i in range(1, min(4, len(plain_ocr_lines)) + 1):
                last_line = plain_ocr_lines[-i]
                if re.match(r'^\s*\d+\s*$', last_line) or re.match(r'^\s*-\s*\d+\s*-\s*$', last_line):
                    extra_footer_content = last_line
                    break
                if not extra_footer_content and len(last_line) < 15:
                    extra_footer_content = last_line

            logger.info(
                f"[Scanned Parse] Supplementary OCR lines={len(plain_ocr_lines)}, "
                f"header='{extra_header_content[:40]}...' ({len(extra_header_content)} chars), "
                f"footer='{extra_footer_content}'"
            )
    except Exception as e:
        logger.warning(f"[Scanned Parse] Supplementary OCR failed (non-critical): {e}")

    # Step 1b: 调用整页 Table Recognition
    try:
        raw_output = ocr_service._call_llama_server(
            "Table Recognition:",
            jpg_path,
            max_tokens=16384
        )
    except Exception as e:
        logger.error(f"[Scanned Parse] Table Recognition failed: {e}")
        if not plain_ocr_lines:
            try:
                raw_output = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
            except Exception as e2:
                logger.error(f"[Scanned Parse] OCR fallback also failed: {e2}")
                return []
        else:
            raw_output = "\n".join(plain_ocr_lines)

    if not raw_output or not raw_output.strip():
        logger.warning(f"[Scanned Parse] Empty output for {Path(jpg_path).name}")
        return []

    logger.info(f"[Scanned Parse] Raw output length: {len(raw_output)} chars")
    logger.debug(f"[Scanned Parse] Raw output preview: {raw_output[:500]}")

    # Step 2: 解析结构化行
    rows = _parse_structured_rows(raw_output)
    logger.info(f"[Scanned Parse] Parsed {len(rows)} structured rows")

    # Step 3: 把行分组为块（表格块 / 文本块）
    blocks = _group_rows_to_blocks(rows)
    logger.info(f"[Scanned Parse] Grouped into {len(blocks)} blocks")

    # Step 4: 估算每个块的 bbox，转为元素（支持强制不识别表头）
    elements = _blocks_to_elements(blocks, page_width, page_height,
                                   table_force_no_header=table_force_no_header_map)
    logger.info(f"[Scanned Parse] Generated {len(elements)} elements from Table Recognition")

    # Step 4b: 插入补充的页眉页脚元素（从纯 OCR 提取的）
    insert_y_top = 2
    insert_y_bottom = page_height - 2

    if extra_header_content:
        # 检查是否已有元素内容高度重合（已包含页眉）
        header_exists = False
        for e in elements:
            bbox = e["bbox"]
            if bbox[1] < page_height * 0.1:  # 顶部 10%
                existing = normalize_text(e.get("content", "") or "")
                new = normalize_text(extra_header_content)
                if new and (new in existing or existing in new or
                            difflib.SequenceMatcher(None, new, existing).ratio() > 0.7):
                    header_exists = True
                    break

        if not header_exists:
            h = page_height * 0.05  # 页眉高度 5%
            header_elem = {
                'element_type': 'Page-header',
                'bbox': (page_width * 0.05, insert_y_top,
                         page_width * 0.95, insert_y_top + h),
                'confidence': 0.75,
                'reading_order': 0,  # 后面会重新分配
                'content': extra_header_content,
                'content_format': 'markdown',
            }
            elements.insert(0, header_elem)
            logger.info(f"[Scanned Parse] Inserted supplementary Page-header ({len(extra_header_content)} chars)")

    if extra_footer_content:
        footer_exists = False
        for e in elements:
            bbox = e["bbox"]
            if bbox[3] > page_height * 0.9:
                existing = normalize_text(e.get("content", "") or "")
                new = normalize_text(extra_footer_content)
                if new and (new in existing or existing == new):
                    footer_exists = True
                    break

        if not footer_exists:
            h = page_height * 0.04
            footer_elem = {
                'element_type': 'Page-footer',
                'bbox': (page_width * 0.4, page_height - h - 2,
                         page_width * 0.6, page_height - insert_y_bottom),
                'confidence': 0.80,
                'reading_order': 0,
                'content': extra_footer_content,
                'content_format': 'markdown',
            }
            elements.append(footer_elem)
            logger.info(f"[Scanned Parse] Appended supplementary Page-footer: '{extra_footer_content}'")

    # Step 5: 后处理 - 识别页眉页脚、章节标题等特殊类型
    elements = _post_process_element_types(elements, page_width, page_height)

    # Step 6: 分配阅读顺序
    for i, elem in enumerate(elements):
        elem["reading_order"] = i

    return elements


def _parse_structured_rows(raw_text: str) -> list[dict]:
    """
    解析 PaddleOCR-VL Table Recognition 输出的 <fcel>/<nl>/<ucel>/<lcel> 标签。

    返回:
        行列表，每行包含:
            - cells: list[str] 单元格内容
            - cell_tags: list[str] 每个单元格对应的标签类型 ('fcel'/'lcel')
            - is_ucel: bool 是否是跨行接续（第一列省略的接续行）
            - cell_count: int 有效单元格数量
            - has_lcel: bool 是否包含 <lcel> 标签
            - raw: str 原始行文本
    """
    rows = []

    if '<nl>' not in raw_text and '<fcel>' not in raw_text:
        # 纯文本输出，没有结构化标签，按换行分割
        for line in raw_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            rows.append({
                'cells': [line],
                'cell_tags': ['text'],
                'is_ucel': False,
                'cell_count': 1,
                'has_lcel': False,
                'raw': line
            })
        return rows

    parts = raw_text.split('<nl>')
    for part in parts:
        part = part.strip()
        if not part:
            continue

        is_ucel = part.startswith('<ucel>')
        if is_ucel:
            part = part[len('<ucel>'):]

        cells = []
        cell_tags = []
        remaining = part
        while '<fcel>' in remaining or '<lcel>' in remaining:
            # 找下一个 <fcel> 或 <lcel>
            fcel_pos = remaining.find('<fcel>')
            lcel_pos = remaining.find('<lcel>')

            if fcel_pos >= 0 and (lcel_pos == -1 or fcel_pos <= lcel_pos):
                tag_type = 'fcel'
                _, after = remaining.split('<fcel>', 1)
            else:
                tag_type = 'lcel'
                _, after = remaining.split('<lcel>', 1)

            # 找结束位置（下一个标签）
            next_fcel = after.find('<fcel>')
            next_lcel = after.find('<lcel>')
            next_pos = len(after)
            if next_fcel >= 0:
                next_pos = min(next_pos, next_fcel)
            if next_lcel >= 0:
                next_pos = min(next_pos, next_lcel)

            content = after[:next_pos].strip()
            # 去除 HTML 标签残留
            content = re.sub(r'<[^>]+>', '', content).strip()
            cells.append(content)
            cell_tags.append(tag_type)
            remaining = after[next_pos:]

        has_lcel = '<lcel>' in part
        non_empty = [c for c in cells if c]
        cell_count = len(non_empty)

        rows.append({
            'cells': cells if cells else [part],
            'cell_tags': cell_tags if cells else [],
            'is_ucel': is_ucel,
            'cell_count': cell_count,
            'has_lcel': has_lcel,
            'raw': part
        })

    return rows


def _group_rows_to_blocks(rows: list[dict]) -> list[dict]:
    """
    将结构化行分组为"块"（表格块 或 文本块）。

    判断规则:
        - 表格块: 连续 ≥2 行，每行 cell_count ≥ 2，且非 lcel 跨列
        - 文本块: 其余行（单行列数少 / 含 lcel 标签的长文本）

    返回:
        块列表，每个块包含:
            - type: 'table' or 'text'
            - rows: list[dict] 行数据
            - row_span_info: list 跨行信息（仅表格）
            - line_count: 估算视觉行数（用于 bbox 高度估算）
    """
    blocks = []
    i = 0
    n = len(rows)

    while i < n:
        row = rows[i]

        # 判断这一行是否可能是表格起始行
        # 表格起始特征: 非 ucel，cell_count >= 2，不是 lcel 跨列单文本
        is_table_start = (
            not row['is_ucel']
            and row['cell_count'] >= 2
            and not (row['has_lcel'] and row['cell_count'] == 1 and len(row['cells']) <= 1)
        )

        if is_table_start:
            # 尝试收集连续的表格行
            table_rows = [row]
            j = i + 1

            while j < n:
                nr = rows[j]

                # 接续行（ucel）总是属于表格
                if nr['is_ucel']:
                    table_rows.append(nr)
                    j += 1
                    continue

                # 正常表格行: cell_count >= 2
                if nr['cell_count'] >= 2 and not (nr['has_lcel'] and nr['cell_count'] == 1):
                    table_rows.append(nr)
                    j += 1
                    continue

                # 检查: 是否是 "表格下方解释文字"（特征: lcel + 1个非空大单元格 + 位置靠近表格）
                if nr['has_lcel'] and nr['cell_count'] <= 1 and len(table_rows) >= 2:
                    # 先不加入，看看后续还有没有表格行
                    # 如果后面紧接着还有表格行，则这个是表格中间的注释行
                    if j + 1 < n and rows[j+1]['cell_count'] >= 2:
                        table_rows.append(nr)
                        j += 1
                        continue

                break

            if len(table_rows) >= 2:
                # 确认是表格块
                blocks.append({
                    'type': 'table',
                    'rows': table_rows,
                    'line_count': len(table_rows) + 1,  # +1 给表格边框
                })
                i = j
                continue

        # 不是表格块，逐行判断是否需要拆分
        # 拆分规则:
        #   1. 单行标题特征 (表X-X, 图X-X, 章节开头（一二、1.2.等）, 单行短文本) → 单独成块
        #   2. 否则合并连续的文本行（长段落）
        def _is_title_like(r: dict) -> bool:
            text = ' '.join([c for c in r['cells'] if c])
            t = text.strip()
            if not t:
                return False
            # 太长的（>100字）肯定不是标题
            if len(t) > 100:
                return False
            # 表X-X / 图X-X 标题
            if re.match(r'^[图表]\s*\d+[-—]', t):
                return True
            # 单位说明 "(单位：%)" 之类
            if re.match(r'^\s*（.*?）\s*$', t) or re.match(r'^\s*\(.*?\)\s*$', t):
                return True
            # 章节开头
            if re.match(r'^\s*[（(][一二三四五六七八九十百千]+[)）]', t):
                return True
            if re.match(r'^\s*[一二三四五六七八九十百千]+[、.]', t):
                return True
            if re.match(r'^\s*\d+[、.．)]', t):
                return True
            if re.match(r'^\s*第[一二三四五六七八九十百千\d]+[章节篇条]', t):
                return True
            # 单行短文本（<40字）且下一行是表格开始 → 作为标题
            return False

        def _is_single_short_line(r: dict) -> bool:
            """单行短文本，适合单独成块"""
            text = ' '.join([c for c in r['cells'] if c])
            t = text.strip()
            if not t:
                return True  # 空行也是分隔
            return len(t) < 50 and len(t) > 0

        current_block = [row]
        j = i + 1

        while j < n:
            nr = rows[j]

            # 下一行是表格起始 → 必须停止当前块
            is_next_table = (
                not nr['is_ucel']
                and nr['cell_count'] >= 2
                and not (nr['has_lcel'] and nr['cell_count'] == 1)
            )
            if is_next_table:
                break

            # 拆分条件: 当前行或下一行是标题特征
            #   → 先把已累积的 current_block 作为一个块
            #   → 然后把标题特征行单独作为一个块
            if _is_title_like(nr):
                # 如果 current_block 非空，先 flush
                if len(current_block) >= 1:
                    first = current_block[0]
                    if _is_title_like(first) and len(current_block) == 1:
                        blocks.append({
                            'type': 'text',
                            'rows': current_block,
                            'line_count': len(current_block),
                            'hint': 'title_like',
                        })
                    else:
                        blocks.append({
                            'type': 'text',
                            'rows': current_block,
                            'line_count': len(current_block),
                            'hint': 'paragraph',
                        })
                current_block = [nr]
                j += 1
                continue

            # 如果当前块只有一行且是标题特征 → 先 flush 成单独块
            if len(current_block) == 1 and _is_title_like(current_block[0]):
                blocks.append({
                    'type': 'text',
                    'rows': current_block,
                    'line_count': len(current_block),
                    'hint': 'title_like',
                })
                current_block = [nr]
                j += 1
                continue

            # 正常追加
            current_block.append(nr)
            j += 1

        # flush 最后一个块
        if current_block:
            first = current_block[0]
            hint = 'title_like' if (len(current_block) == 1 and _is_title_like(first)) else 'paragraph'
            blocks.append({
                'type': 'text',
                'rows': current_block,
                'line_count': len(current_block),
                'hint': hint,
            })
        i = j

    return blocks


def _blocks_to_elements(blocks: list[dict], page_w: int, page_h: int,
                        table_force_no_header: dict = None) -> list[dict]:
    """
    将块转换为元素，估算 bbox 坐标。

    坐标估算策略:
        使用内容感知的权重分配: 根据实际文本长度和行数决定每个块的高度，
        而非均匀分布。表格块使用更宽的边距。
        所有坐标均在 JPG 像素空间（与非扫描版 YOLO 检测一致）。
    
    Args:
        blocks: 块列表
        page_w: 页面宽度（像素）
        page_h: 页面高度（像素）
        table_force_no_header: 字典 {table_block_index: bool}，指定哪些表格块需要强制不识别表头
    """
    elements = []
    if table_force_no_header is None:
        table_force_no_header = {}

    # 计算内容权重: 文本用字符数/80估算行数，表格用行数+权重
    total_weight = 0
    block_weights = []
    for b in blocks:
        if b['type'] == 'table':
            rows = b['rows']
            # 表格: 行数*1.5 + 额外间距
            weight = len(rows) * 1.5 + 0.8
        else:
            rows = b['rows']
            # 文本: 根据实际文本总长度估算行数
            total_chars = 0
            for r in rows:
                for c in r.get('cells', []):
                    total_chars += len(c)
            # 假设每行约60字符
            est_lines = max(len(rows), total_chars / 60.0)
            weight = est_lines * 1.0 + 0.3
        block_weights.append(weight)
        total_weight += weight

    # 页边距: 顶部留8%（页眉区域），底部留6%（页脚区域）
    margin_top = page_h * 0.08
    margin_bottom = page_h * 0.06
    usable_h = page_h - margin_top - margin_bottom
    # 预留块间间距 (每个块之间1%页高)
    inter_block_gap = page_h * 0.01
    total_gaps = inter_block_gap * (len(blocks) - 1) if len(blocks) > 1 else 0
    usable_h_for_content = usable_h - total_gaps
    # 每单位权重的像素高度
    pixel_per_weight = usable_h_for_content / max(total_weight, 0.01)

    # 横向边距: 文本使用8%，表格使用3%
    text_margin_ratio = 0.08
    table_margin_ratio = 0.03
    text_x0 = page_w * text_margin_ratio
    text_x1 = page_w - page_w * text_margin_ratio
    table_x0 = page_w * table_margin_ratio
    table_x1 = page_w - page_w * table_margin_ratio

    current_y = margin_top
    table_block_idx = 0

    for bi, block in enumerate(blocks):
        block_type = block['type']
        rows = block['rows']

        block_h = block_weights[bi] * pixel_per_weight
        block_h = max(block_h, page_h * 0.02)  # 最小高度

        if block_type == 'table':
            force_hdr = table_force_no_header.get(table_block_idx, False)
            html, rows_count, cols_count = _table_rows_to_html(rows, force_no_header=force_hdr)
            table_block_idx += 1

            bbox = (table_x0, current_y, table_x1, current_y + block_h)

            if html and rows_count >= 2:
                elements.append({
                    'element_type': 'Table',
                    'bbox': bbox,
                    'confidence': 0.85,
                    'reading_order': 0,
                    'content': html,
                    'content_format': 'html',
                    'table_cols': cols_count,
                    'table_rows': rows_count,
                })
            else:
                plain = _rows_to_plain_text(rows)
                elements.append({
                    'element_type': 'Text',
                    'bbox': bbox,
                    'confidence': 0.75,
                    'reading_order': 0,
                    'content': plain,
                    'content_format': 'markdown',
                })
        else:
            plain = _rows_to_plain_text(rows)
            bbox = (text_x0, current_y, text_x1, current_y + block_h)
            elements.append({
                'element_type': 'Text',
                'bbox': bbox,
                'confidence': 0.80,
                'reading_order': 0,
                'content': plain,
                'content_format': 'markdown',
            })

        current_y += block_h + inter_block_gap

    return elements


def _table_rows_to_html(rows: list[dict], force_no_header: bool = False) -> tuple[str, int, int]:
    """
    将表格行数据转换为带 rowspan/colspan 的 HTML。

    处理逻辑:
        1. 先计算最大列数（fcel=1列，lcel=根据最大列数计算跨度）
        2. 第一行为表头（除非 force_no_header=True）
        3. ucel 标记的行: 第一列是跨行（从最近的非 ucel 行延伸下来）
        4. lcel 标记的单元格: 具有 colspan（跨越到行末或下一个 fcel 边界）
        5. 跨行用 <td rowspan='N'> 实现
    """
    if len(rows) < 2:
        return "", 0, 0

    nrows = len(rows)

    # Step 1: 确定基础列数
    # 非 ucel 行的列数 = 实际单元格数（fcel和lcel都算1个视觉位置）
    # ucel 行的列数 = 额外+1（被合并的第一列）
    max_cols = 0
    for r in rows:
        if r['is_ucel']:
            max_cols = max(max_cols, len(r['cells']) + 1)
        else:
            max_cols = max(max_cols, len(r['cells']))

    if max_cols < 2:
        return "", 0, 0

    # Step 2: 构建行列跨度的记录矩阵
    covered = [[False] * max_cols for _ in range(nrows)]
    real_rowspan = [[1] * max_cols for _ in range(nrows)]
    real_colspan = [[1] * max_cols for _ in range(nrows)]

    # Step 3: 处理 ucel 行 → rowspan（第一列的纵向合并）
    for ri in range(nrows):
        r = rows[ri]
        if not r['is_ucel']:
            continue
        # 找到当前 ucel 连续块的开头行（第一个非 ucel 行）
        start_r = ri - 1
        while start_r >= 0 and rows[start_r]['is_ucel']:
            start_r -= 1
        if start_r >= 0:
            # 计算从 start_r 到最后一个连续 ucel 行的跨度
            end_r = ri
            while end_r + 1 < nrows and rows[end_r + 1]['is_ucel']:
                end_r += 1
            span_len = end_r - start_r + 1
            real_rowspan[start_r][0] = max(real_rowspan[start_r][0], span_len)
            # 标记所有 ucel 行的第一列为 covered
            for ur in range(start_r + 1, end_r + 1):
                covered[ur][0] = True

    # Step 4: 处理 lcel 单元格 → colspan
    for ri in range(nrows):
        r = rows[ri]
        cells = list(r['cells'])
        tags = list(r.get('cell_tags', []))
        if r['is_ucel']:
            # ucel 行: 第一列为空（被上一行覆盖），后续单元格从第1列开始
            cells = [''] + cells
            tags = ['covered'] + tags
        # 补齐到 max_cols
        while len(cells) < max_cols:
            cells.append('')
            tags.append('')

        ci = 0
        for cell_idx in range(len(cells)):
            # 跳过已被覆盖的位置
            while ci < max_cols and covered[ri][ci]:
                ci += 1
            if ci >= max_cols:
                break

            tag_type = tags[cell_idx] if cell_idx < len(tags) else ''

            if tag_type == 'lcel':
                # lcel 表示跨列内容: 跨越到行末的所有剩余列
                cs = max_cols - ci
                real_colspan[ri][ci] = max(1, cs)

            # 标记被当前单元格覆盖的区域
            cs = real_colspan[ri][ci]
            rs = real_rowspan[ri][ci]
            for r2 in range(ri, min(ri + rs, nrows)):
                for c2 in range(ci, min(ci + cs, max_cols)):
                    if r2 != ri or c2 != ci:
                        covered[r2][c2] = True
            ci += cs

    # Step 5: 生成 HTML
    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]
    for ri in range(nrows):
        r = rows[ri]
        cells = list(r['cells'])
        tags = list(r.get('cell_tags', []))
        if r['is_ucel']:
            cells = [''] + cells
            tags = ['covered'] + tags
        while len(cells) < max_cols:
            cells.append('')
            tags.append('')

        is_header = (not force_no_header) and (ri == 0 and not r['is_ucel'])
        html_parts.append("  <tr>")

        ci = 0
        while ci < max_cols:
            if covered[ri][ci]:
                ci += 1
                continue

            tag = "th" if is_header else "td"
            content = escape(cells[ci]) if ci < len(cells) else ''
            attrs = ""
            if real_rowspan[ri][ci] > 1:
                attrs += f" rowspan='{real_rowspan[ri][ci]}'"
            if real_colspan[ri][ci] > 1:
                attrs += f" colspan='{real_colspan[ri][ci]}'"

            html_parts.append(f"    <{tag}{attrs}>{content}</{tag}>")
            ci += real_colspan[ri][ci]

        html_parts.append("  </tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts), nrows, max_cols


def _rows_to_plain_text(rows: list[dict]) -> str:
    """将行列表转为纯文本。"""
    lines = []
    for r in rows:
        cells = r['cells']
        non_empty = [c for c in cells if c and c.strip()]
        if len(non_empty) >= 2:
            # 多单元格，用空格连接
            lines.append(' '.join(non_empty))
        elif non_empty:
            lines.append(non_empty[0])
        elif r['raw']:
            lines.append(r['raw'])
    return '\n'.join(lines)



def _post_process_element_types(elements: list[dict], page_w: int, page_h: int) -> list[dict]:
    """
    基于内容特征和位置，进一步细化元素类型。

    启发式规则:
        1. 页眉区域 (顶部 10% 以内的短文本) → Page-header
        2. 页脚区域 (底部 10% 以内的短文本/数字) → Page-footer
        3. 章节标题 (匹配: 数字+、  或 表X-X:  或 第X章等) → Section-header
        4. 主标题 (短文本, 居中, 在页眉下方) → Title
        5. 图片说明 "如图", "表X-X" 开头等 → Caption
    """
    result = list(elements)
    n = len(result)

    for i, elem in enumerate(result):
        if elem['element_type'] != 'Text':
            continue

        content = elem.get('content', '') or ''
        content_stripped = content.strip()
        if not content_stripped:
            continue

        bbox = elem['bbox']
        y0, y1 = bbox[1], bbox[3]
        x0, x1 = bbox[0], bbox[2]
        first_line = content_stripped.split('\n')[0] if '\n' in content_stripped else content_stripped
        is_short = len(first_line) <= 50

        # --- 页眉 ---
        if y0 < page_h * 0.07 and elem['element_type'].lower() in ('section', 'section-header'):
            elem['element_type'] = 'Page-header'
            continue

        if y0 < page_h * 0.1 and is_short:
            # 不是表格标题的特征字符
            if not re.match(r'^表\s*\d+', first_line):
                elem['element_type'] = 'Page-header'
                continue

        # --- 页脚 ---
        if y1 > page_h * 0.9:
            # 页码 (纯数字或 "数字/总数")
            if re.match(r'^\s*\d+\s*$', first_line) or re.match(r'^\s*-\s*\d+\s*-\s*$', first_line):
                elem['element_type'] = 'Page-footer'
                continue
            if is_short and len(first_line) <= 15:
                elem['element_type'] = 'Page-footer'
                continue

        # --- 图片 ---
        if first_line.startswith('（图') or first_line.startswith('(图') or first_line.startswith('如图'):
            elem['element_type'] = 'Picture'
            # 内容保留说明文字，图片无法提取，保持 image_path 为空
            elem['content'] = first_line
            elem['content_format'] = 'image_path'
            continue

        # --- 章节标题 ---
        section_patterns = [
            r'^\s*（[一二三四五六七八九十]+）',  # （一）、（二）...
            r'^\s*\([一二三四五六七八九十]+\)',   # (一)(二)...
            r'^\s*[一二三四五六七八九十]+、',     # 一、二、...
            r'^\s*\d+[、.．]',                    # 1、 2. 1．
            r'^\s*第\s*[一二三四五六七八九十\d]+\s*[章节篇条]',  # 第一章
            r'^\s*\(\s*\d+\s*\)',                # (1) (2)
            r'^\s*\d+\s*[）)]',                  # 1） 2)
        ]
        if is_short and any(re.match(p, first_line) for p in section_patterns):
            elem['element_type'] = 'Section-header'
            continue

        # --- 表格标题 (表 5-9: ... / 表5-9 ...) ---
        if re.match(r'^\s*表\s*\d+[-—]\d+', first_line) and is_short:
            elem['element_type'] = 'Caption'
            continue

        # --- 图片标题 (图 5-1: ...) ---
        if re.match(r'^\s*图\s*\d+[-—]\d+', first_line) and is_short:
            elem['element_type'] = 'Caption'
            continue

        # --- 主标题 (页面最上方的长公司名/文档名) ---
        if i == 0 and elem['element_type'] == 'Page-header':
            # 如果页眉内容很长，可能是主标题
            if len(first_line) > 20:
                elem['element_type'] = 'Title'
                continue

    return result
