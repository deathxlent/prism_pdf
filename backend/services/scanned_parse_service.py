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


def parse_scanned_page_full(jpg_path: str, page_width: int, page_height: int) -> list[dict]:
    """
    直接调用 PaddleOCR-VL Table Recognition 解析整页扫描件图片。

    Args:
        jpg_path: 页面 JPG 图片路径
        page_width: JPG 图片宽度（像素）
        page_height: JPG 图片高度（像素）

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
    # 纯文本用于: (1) 提取页眉页脚 (2) 补全表格缺失的数字列
    plain_ocr_lines = []
    extra_header_content = ""
    extra_footer_content = ""
    try:
        ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
        if ocr_plain and ocr_plain.strip():
            plain_ocr_lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]

            # --- 提取页眉 ---
            header_keywords = ['集团', '有限公司', '年度', '票据', '说明书', '公告',
                               '报告', '招股', '募集', '债券', '审计']
            found_header_idx = -1
            for i in range(min(3, len(plain_ocr_lines))):
                if any(kw in plain_ocr_lines[i] for kw in header_keywords):
                    found_header_idx = i
                    break

            if found_header_idx >= 0:
                header_line = plain_ocr_lines[found_header_idx]
                if len(header_line) > 80:
                    header_line = header_line[:80]
                extra_header_content = header_line
            elif plain_ocr_lines and len(plain_ocr_lines[0]) < 80:
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

    # Step 4: 估算每个块的 bbox，转为元素
    elements = _blocks_to_elements(blocks, page_width, page_height)
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

    # Step 5b: 从 supplementary OCR 纯文本补全表格缺失的列（如收费里程等右侧数字列）
    if plain_ocr_lines:
        elements = _supplement_table_missing_columns(elements, plain_ocr_lines)

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
            - is_ucel: bool 是否是跨行接续（第一列省略的接续行）
            - cell_count: int 有效单元格数量
            - has_lcel: bool 是否包含 <lcel> 标签（通常表示非表格的长文本跨列）
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
        remaining = part
        while '<fcel>' in remaining or '<lcel>' in remaining:
            # 找下一个 <fcel> 或 <lcel>
            fcel_pos = remaining.find('<fcel>')
            lcel_pos = remaining.find('<lcel>')

            if fcel_pos >= 0 and (lcel_pos == -1 or fcel_pos <= lcel_pos):
                _, after = remaining.split('<fcel>', 1)
            else:
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
            remaining = after[next_pos:]

        has_lcel = '<lcel>' in part
        non_empty = [c for c in cells if c]
        cell_count = len(non_empty)

        rows.append({
            'cells': cells if cells else [part],
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


def _blocks_to_elements(blocks: list[dict], page_w: int, page_h: int) -> list[dict]:
    """
    将块转换为元素，估算 bbox 坐标。

    bbox 估算策略:
        1. 先统计所有块的 "视觉总行数" = sum(block.line_count)
        2. 每行的平均高度 = page_h / (总视觉行数 + 2)（上下留白）
        3. x 方向: 占页面 90% 宽度居中，表格占更宽
        4. 表格行高度略大于文本行
    """
    elements = []

    # 计算总行数（带权重）
    total_weighted_lines = 0
    for b in blocks:
        if b['type'] == 'table':
            # 表格每行按 1.5 倍权重计算（表格有边框和 padding）
            total_weighted_lines += b['line_count'] * 1.5 + 0.5  # + 标题边框
        else:
            total_weighted_lines += b['line_count']

    # 上下各留 5% 边距
    margin_top = page_h * 0.05
    margin_bottom = page_h * 0.05
    usable_h = page_h - margin_top - margin_bottom

    # 加权平均每行高度
    line_h = usable_h / max(total_weighted_lines, 1)

    # x 边距
    margin_x = page_w * 0.05
    text_x0 = margin_x
    text_x1 = page_w - margin_x
    table_x0 = page_w * 0.02   # 表格占更宽
    table_x1 = page_w - page_w * 0.02

    current_y = margin_top

    for block in blocks:
        block_type = block['type']
        rows = block['rows']

        if block_type == 'table':
            # 构建 HTML 表格
            html, rows_count, cols_count = _table_rows_to_html(rows)

            # 计算高度
            block_h = line_h * (len(rows) * 1.5 + 0.5)
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
                # 表格构建失败，fallback 为文本
                plain = _rows_to_plain_text(rows)
                elements.append({
                    'element_type': 'Text',
                    'bbox': bbox,
                    'confidence': 0.75,
                    'reading_order': 0,
                    'content': plain,
                    'content_format': 'markdown',
                })

            current_y += block_h

        else:  # text block
            plain = _rows_to_plain_text(rows)
            block_h = line_h * len(rows) * 1.2  # 文本行略松

            bbox = (text_x0, current_y, text_x1, current_y + block_h)

            elements.append({
                'element_type': 'Text',
                'bbox': bbox,
                'confidence': 0.80,
                'reading_order': 0,
                'content': plain,
                'content_format': 'markdown',
            })

            current_y += block_h

        # 块之间留小间距
        current_y += line_h * 0.3

    return elements


def _table_rows_to_html(rows: list[dict]) -> tuple[str, int, int]:
    """
    将表格行数据转换为带 rowspan/colspan 的 HTML。

    处理逻辑:
        1. 先计算最大列数
        2. 第一行为表头
        3. ucel 标记的行: 第一列是跨行（从最近的非 ucel 行延伸下来）
        4. 跨行用 <td rowspan='N'> 实现
    """
    if len(rows) < 2:
        return "", 0, 0

    # Step 1: 计算最大列数
    max_cols = 0
    for r in rows:
        ncells = len(r['cells'])
        if r['is_ucel']:
            # ucel 行的第一列是从上一行继承的，所以实际单元格数 = cells + 1
            # 但也可能第一格就是合并，所以取较大者
            ncells_actual = max(ncells + 1, ncells)
            max_cols = max(max_cols, ncells_actual)
        else:
            max_cols = max(max_cols, ncells)

    if max_cols < 2:
        return "", 0, 0

    # Step 2: 构建 rowspan 映射
    # rowspan_map[row_idx][col_idx] = 该单元格是否为"被覆盖"（由上面的 rowspan 覆盖）
    covered = [[False] * max_cols for _ in range(len(rows))]
    # 真实 rowspan 值
    real_rowspan = [[1] * max_cols for _ in range(len(rows))]

    for ri in range(len(rows)):
        r = rows[ri]
        if r['is_ucel']:
            # 第一列是被覆盖的（从上面跨行下来）
            # 找到这个 ucel 对应的起始行: 往上找最近的非 ucel 行
            start_r = ri - 1
            while start_r >= 0 and rows[start_r]['is_ucel']:
                start_r -= 1

            if start_r >= 0:
                # 计算跨越的总行数: 从 start_r 一直到这个 ucel 行
                span_len = ri - start_r + 1
                # 还需要检查后面还有没有连续的 ucel
                end_r = ri
                while end_r + 1 < len(rows) and rows[end_r + 1]['is_ucel']:
                    end_r += 1
                    span_len = end_r - start_r + 1

                covered[ri][0] = True  # 这一行的第 0 列被覆盖
                real_rowspan[start_r][0] = max(real_rowspan[start_r][0], span_len)

    # Step 3: 生成 HTML
    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]
    for ri, r in enumerate(rows):
        cells = list(r['cells'])

        # 如果是 ucel，前面补一个空（因为 covered[0]=True，会被跳过输出）
        if r['is_ucel']:
            cells = [''] + cells

        # 补齐到 max_cols
        while len(cells) < max_cols:
            cells.append('')

        is_header = (ri == 0 and not r['is_ucel'])
        html_parts.append("  <tr>")

        for ci in range(max_cols):
            if covered[ri][ci]:
                continue

            tag = "th" if is_header else "td"
            content = escape(cells[ci]) if ci < len(cells) else ''

            attrs = ""
            if real_rowspan[ri][ci] > 1:
                attrs += f" rowspan='{real_rowspan[ri][ci]}'"

            html_parts.append(f"    <{tag}{attrs}>{content}</{tag}>")
        html_parts.append("  </tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts), len(rows), max_cols


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


def _supplement_table_missing_columns(elements: list[dict], plain_ocr_lines: list[str]) -> list[dict]:
    """
    从 supplementary OCR 纯文本中提取缺失的表格列，追加到右侧。

    背景: PaddleOCR-VL 在列数很多（>=7）时，可能会截断右侧的数字列（如收费里程）。
          但 "OCR:" 纯文本模式通常能完整识别所有数字。

    策略:
        1. 扫描 plain_ocr_lines，找到所有浮点数 (xxx.xx)
        2. 按连续出现的位置，把浮点数聚类成 N 列 M 行的矩阵
        3. 对于每个 Table 元素，如果它数据行的数字数量 < OCR 中识别到的列数，
           就把缺失的数字列追加进去

    注意: 这是一个启发式补救，仅处理浮点数列（如里程、金额）。
    """
    if not plain_ocr_lines:
        return elements

    # ============ Step 1: 从纯文本提取所有浮点数，按行组织 ============
    ocr_number_matrix = []  # 每行的浮点数列表: [[118.17, 117.88], [44.96, 51.59], ...]
    for line in plain_ocr_lines:
        nums = re.findall(r'\b\d+\.\d+\b', line)
        if nums:
            ocr_number_matrix.append([float(n) for n in nums])

    if not ocr_number_matrix:
        return elements

    logger.info(f"[Scanned Parse] Supplementary OCR numbers: {len(ocr_number_matrix)} rows with floats. "
                f"Row lengths: {[len(r) for r in ocr_number_matrix[:8]]}"
                f"{'...' if len(ocr_number_matrix) > 8 else ''}")

    # ============ Step 2: 处理每个 Table 元素 ============
    new_elements = []

    for ei, elem in enumerate(elements):
        if elem['element_type'] != 'Table' or not elem.get('content'):
            new_elements.append(elem)
            continue

        table_html = elem['content']
        table_2d, has_header = _parse_table_html_to_2d(table_html)

        if not table_2d:
            new_elements.append(elem)
            continue

        n_rows = len(table_2d)
        n_cols = len(table_2d[0]) if table_2d else 0
        data_rows_start = 1 if has_header else 0
        n_data_rows = n_rows - data_rows_start

        # --- 统计当前表格每行有多少个浮点数 ---
        table_floats_per_row = []
        for row in table_2d[data_rows_start:]:
            row_floats = []
            for cell in row:
                cell = cell.strip()
                if not cell:
                    continue
                m = re.match(r'^\s*(\d+\.\d+)\s*$', cell)
                if m:
                    row_floats.append(float(m.group(1)))
            table_floats_per_row.append(row_floats)

        # --- 找 OCR 中对应的数字矩阵（行数一致 + 数值范围匹配）---
        avg_current_floats = (
            sum(len(r) for r in table_floats_per_row) / len(table_floats_per_row)
            if table_floats_per_row else 0
        )

        best_matrix = None
        best_score = -1

        # --- Step 0: 关键词门控，判断是否需要补列 ---
        # 合并表格内部文本 + 前面 1-3 个上下文元素的文本（Caption/Text）
        full_table_text = ' '.join([' '.join(r) for r in table_2d])
        # 加上前面元素的文本（比如表格标题 "表 5-10: ...（单位：公里）"）
        context_text_parts = []
        for prev_ei in range(max(0, ei - 3), ei):
            prev_elem = elements[prev_ei]
            if prev_elem.get('element_type') in ('Caption', 'Text', 'Section-header'):
                prev_content = prev_elem.get('content', '') or ''
                context_text_parts.append(prev_content)
        context_text = ' '.join(context_text_parts)
        combined_text = full_table_text + ' ' + context_text

        supplement_keywords = ['里程', '金额', '万元', '公里', '长度', '数量',
                               '面积', '人数', '单价', '总价', '合计金额']
        has_supplement_keyword = any(kw in combined_text for kw in supplement_keywords)

        # 补列判定: 有关键词 OR 每行浮点数很少 (<2)
        need_supplement = has_supplement_keyword or avg_current_floats < 2.0

        if not need_supplement and avg_current_floats >= 2.0:
            logger.info(
                f"[Scanned Parse] Table #{ei} skip supplement: "
                f"no keywords, avg floats={avg_current_floats:.1f}/row (sufficient)"
            )
            new_elements.append(elem)
            continue

        logger.info(
            f"[Scanned Parse] Table #{ei} needs supplement: "
            f"keyword_hit={has_supplement_keyword}, "
            f"avg_floats={avg_current_floats:.1f}/row, "
            f"context='{context_text[:60]}...'"
        )

        # --- Step A: 计算当前表格已有浮点数的数值范围 ---
        all_table_floats = []
        for row in table_floats_per_row:
            all_table_floats.extend(row)

        if all_table_floats:
            table_f_min = min(all_table_floats) * 0.7
            table_f_max = max(all_table_floats) * 1.3
        else:
            # 没有浮点数时，从上下文关键词推断范围
            if any(kw in combined_text for kw in ['里程', '公里']):
                table_f_min, table_f_max = 5.0, 300.0
            elif any(kw in combined_text for kw in ['金额', '万元']):
                table_f_min, table_f_max = 0.0, 1e7
            else:
                table_f_min, table_f_max = 0.0, 1e5

        MAX_SUPPLEMENT_COLS = 3

        # --- Step B: 从表格自身表头提取关键词，用于在 plain_ocr_lines 中定位 ---
        header_keywords_for_search = []
        if has_header:
            header_row = table_2d[0]
            for cell in header_row[:5]:
                cell = cell.strip()
                if not cell:
                    continue
                meaningful = re.findall(r'[\u4e00-\u9fa5A-Za-z]{2,}', cell)
                header_keywords_for_search.extend(meaningful)
        sample_row_text = ' '.join([' '.join(r[:3]) for r in table_2d[1:3] if len(r) >= 3])
        meaningful2 = re.findall(r'[\u4e00-\u9fa5A-Za-z]{2,}', sample_row_text)
        header_keywords_for_search.extend(meaningful2)
        header_keywords_for_search = list(dict.fromkeys(header_keywords_for_search))[:10]

        if header_keywords_for_search:
            logger.info(f"[Scanned Parse] Table search keywords: {header_keywords_for_search}")

        # --- Step C: 在 plain_ocr_lines 中找匹配的行范围（关键词 + 数值范围）---
        table_ocr_start = -1
        table_ocr_end = -1
        if header_keywords_for_search and all_table_floats:
            best_hit_count = 0
            best_start_line = -1
            for li, line in enumerate(plain_ocr_lines):
                hit_count = sum(1 for kw in header_keywords_for_search if kw and kw in line)
                if hit_count > best_hit_count:
                    best_hit_count = hit_count
                    best_start_line = li

            if best_hit_count >= 2 and best_start_line >= 0:
                table_ocr_start = best_start_line
                # 结束行: 从 start 往后找，直到连续 5 行无浮点数或超出 30 行
                no_float_streak = 0
                for le in range(best_start_line, min(best_start_line + 30, len(plain_ocr_lines))):
                    nums_in_line = re.findall(r'\b\d+\.\d+\b', plain_ocr_lines[le])
                    if nums_in_line:
                        # 关键: 只计入"数值范围匹配当前表格"的行，防止串表
                        matched_nums = [float(n) for n in nums_in_line
                                        if table_f_min <= float(n) <= table_f_max]
                        if matched_nums:
                            no_float_streak = 0
                            table_ocr_end = le + 1
                            continue
                    no_float_streak += 1
                    if no_float_streak >= 5:
                        break

                logger.info(
                    f"[Scanned Parse] Located table in OCR lines: "
                    f"{table_ocr_start}-{table_ocr_end} "
                    f"(keyword_hits={best_hit_count}/{len(header_keywords_for_search)}, "
                    f"float_range=[{table_f_min:.1f}~{table_f_max:.1f}])"
                )

        # --- Step D: 从定位到的范围提取浮点数矩阵（数值必须匹配当前表格范围）---
        scoped_ocr_number_matrix = []
        if table_ocr_start >= 0:
            for li in range(table_ocr_start, table_ocr_end):
                if 0 <= li < len(plain_ocr_lines):
                    nums = re.findall(r'\b\d+\.\d+\b', plain_ocr_lines[li])
                    if nums:
                        # 过滤: 只保留数值范围匹配的浮点数
                        filtered = [float(n) for n in nums
                                    if table_f_min <= float(n) <= table_f_max]
                        if filtered:
                            scoped_ocr_number_matrix.append(filtered)
        if not scoped_ocr_number_matrix:
            # 回退: 全局范围 + 数值过滤
            for nums in ocr_number_matrix:
                filtered = [n for n in nums if table_f_min <= n <= table_f_max]
                if filtered:
                    scoped_ocr_number_matrix.append(filtered)

        if not scoped_ocr_number_matrix:
            new_elements.append(elem)
            continue

        logger.info(
            f"[Scanned Parse] Scoped OCR numbers: {len(scoped_ocr_number_matrix)} rows. "
            f"Row lengths: {[len(r) for r in scoped_ocr_number_matrix[:8]]}"
            f"{'...' if len(scoped_ocr_number_matrix) > 8 else ''}"
        )

        # --- Step B (Alternative): 对没有浮点数的表格，用上下文标记 + 数字行扫描 ---
        if len(all_table_floats) == 0 and has_supplement_keyword and n_data_rows >= 3:
            marker_in_context = re.findall(
                r'(?:表\s*\d+[-_]\d+|公路资产统计表|募集说明书|主要\w+表|所属干线)',
                combined_text
            )
            target_markers = list(dict.fromkeys(marker_in_context))[:3]

            # Caption 前 20 字的子串（去掉空格、全角标点做模糊匹配）
            def _norm(s):
                return re.sub(r'[\s：:（）()、,，.。\-—]', '', s)

            caption_norm = _norm(context_text[:25])

            logger.info(
                f"[Scanned Parse] Table #{ei} no floats, use marker search. "
                f"target_markers={target_markers}, caption_norm='{caption_norm[:15]}...'"
            )

            marker_found_line = -1
            best_line_score = 0
            for li, line in enumerate(plain_ocr_lines):
                line_norm = _norm(line)
                score = 0
                for marker in target_markers:
                    marker_norm = _norm(marker)
                    if marker_norm and marker_norm in line_norm:
                        score += 5
                if caption_norm and len(caption_norm) >= 6:
                    # 取 caption 中 6-8 字符的滑动窗口做子串匹配
                    for w_start in range(0, len(caption_norm) - 5, 3):
                        probe = caption_norm[w_start:w_start + 8]
                        if len(probe) >= 6 and probe in line_norm:
                            score += 3
                            break
                # 额外: 里程/公里关键词命中
                if '里程' in line or ('公里' in line and ('表' in line or '统计' in line)):
                    score += 2
                if '所属干线' in line or '公路名称' in line:
                    score += 3
                if score > best_line_score and score >= 2:
                    best_line_score = score
                    marker_found_line = li

            logger.info(
                f"[Scanned Parse] Table #{ei} marker_found_line={marker_found_line} "
                f"(score={best_line_score})"
            )

            # --- 新策略: 逐行用表格行的关键词在 OCR 中找对应数字行 ---
            # 因为 OCR 纯文本行顺序是乱的，不能假设先后顺序
            keyword_match_rows: list[list[float]] = []
            all_used_ocr_lines: set[int] = set()

            def _norm(s):
                return re.sub(r'[\s：:（）()、,，.。\-—]', '', s)

            # 收集每个表格数据行的关键词
            table_row_keywords: list[list[str]] = []
            for ri in range(data_rows_start, min(data_rows_start + n_data_rows, len(table_2d))):
                row = table_2d[ri]
                kws = []
                for cell in row:
                    if not cell or not isinstance(cell, str):
                        continue
                    # 去掉纯数字、纯标点
                    c = cell.strip()
                    if not c or re.match(r'^[\d\.\-%—\-\s]+$', c):
                        continue
                    # 找有辨识度的词组（>=2 字，不是"收费还贷"这种重复词）
                    words = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]{2,}', c)
                    for w in words:
                        if w not in ('收费还贷', '起自', '止于', '公路', '高速'):
                            kws.append(w)
                # 去重保序，取前 6 个
                seen = set()
                uniq_kws = []
                for k in kws:
                    if k not in seen:
                        seen.add(k)
                        uniq_kws.append(k)
                table_row_keywords.append(uniq_kws[:6])

            # 为每个数据行在 OCR 中找匹配行
            logger.info(
                f"[Scanned Parse] Table #{ei} keyword matching for {len(table_row_keywords)} data rows"
            )
            # 先收集所有含目标数字的 OCR 行，便于 fallback 时按顺序分配
            all_number_lines: list[tuple[int, list[float]]] = []
            for li, ocr_line in enumerate(plain_ocr_lines):
                nums = re.findall(r'\b\d+\.\d+\b', ocr_line)
                nums_in_range = [float(n) for n in nums if 5.0 <= float(n) <= 300.0]
                has_neg = any(float(n) < 0 for n in nums)
                has_gross_margin_keywords = any(
                    k in ocr_line for k in
                    ['毛利率', '项目', '合计', '2014年', '2015年', '2016年', '运营毛利率']
                )
                if not has_gross_margin_keywords and not has_neg and 1 <= len(nums_in_range) <= 3:
                    all_number_lines.append((li, nums_in_range))

            matched_nums: list[list | None] = [None] * len(table_row_keywords)

            for ri, kws in enumerate(table_row_keywords):
                best_kw_li = -1
                best_kw_score = 0
                for li, ocr_line in enumerate(plain_ocr_lines):
                    if li in all_used_ocr_lines:
                        continue
                    ocr_norm = _norm(ocr_line)
                    if not ocr_norm:
                        continue
                    score = 0
                    for kw in kws:
                        if _norm(kw) in ocr_norm:
                            score += len(kw)
                    if score >= 2 and score > best_kw_score:
                        best_kw_score = score
                        best_kw_li = li

                if best_kw_li >= 0:
                    search_range = list(range(
                        max(0, best_kw_li - 8),
                        min(len(plain_ocr_lines), best_kw_li + 9)
                    ))
                    search_range.sort(key=lambda x: abs(x - best_kw_li))
                    for li in search_range:
                        if li in all_used_ocr_lines:
                            continue
                        for nli, nrow in all_number_lines:
                            if nli == li:
                                matched_nums[ri] = nrow
                                all_used_ocr_lines.add(li)
                                logger.info(
                                    f"[Scanned Parse]   row#{ri} matched OCR line#{li} "
                                    f"(kw_score={best_kw_score}, nums={nrow}): "
                                    f"kws={kws[:3]}"
                                )
                                break
                        if matched_nums[ri] is not None:
                            break

            # --- 对未匹配行: 按顺序分配剩余数字行 ---
            # 按数字行号从小到大排序，然后依次分配给未匹配的表格行
            unused_num_lines = [(li, nrow) for li, nrow in all_number_lines if li not in all_used_ocr_lines]
            unused_num_lines.sort(key=lambda x: x[0])  # 按 OCR 行号从小到大

            for ri in range(len(table_row_keywords)):
                if matched_nums[ri] is None:
                    if unused_num_lines:
                        li, nrow = unused_num_lines.pop(0)
                        matched_nums[ri] = nrow
                        all_used_ocr_lines.add(li)
                        logger.info(
                            f"[Scanned Parse]   row#{ri} no keyword match, assigned number line#{li} (by order): {nrow}"
                        )
                    else:
                        matched_nums[ri] = ['']
                        logger.info(f"[Scanned Parse]   row#{ri} no keyword match, no numbers left, empty")

            keyword_match_rows = [row if row is not None else [''] for row in matched_nums]

            # 用 keyword_match_rows 作为 collected_rows
            collected_rows = keyword_match_rows
            logger.info(f"[Scanned Parse] Table #{ei} keyword match collected_rows={len(collected_rows)} rows")

            # 允许收集到的行数比需要的少（OCR 可能漏掉行），至少 70%
            min_required = max(2, int(n_data_rows * 0.7))
            if len(collected_rows) >= min_required:
                # 如果行数不够，用空字符串填充（不要用重复数据）
                while len(collected_rows) < n_data_rows:
                    collected_rows.append([''] * max(1, len(collected_rows[-1]) if collected_rows and collected_rows[-1] else 1))

                consistent = True
                first_len = len([x for x in collected_rows[0] if not (isinstance(x, str) and x == '')]) or 1
                for row in collected_rows[:n_data_rows]:
                    actual_len = len([x for x in row if not (isinstance(x, str) and x == '')])
                    if actual_len > 0 and abs(actual_len - first_len) >= 2:
                        consistent = False
                        break
                if consistent:
                    candidate = collected_rows[:n_data_rows]
                    best_matrix = candidate
                    best_score = 99999
                    logger.info(
                        f"[Scanned Parse] Table #{ei} keyword search succeeded! "
                        f"Found {len(candidate)} rows. Sample: {candidate[0]}"
                    )
        allow_no_match = (len(all_table_floats) == 0)
        if best_matrix is None:
            for start in range(0, len(scoped_ocr_number_matrix) - n_data_rows + 1):
                candidate = scoped_ocr_number_matrix[start:start + n_data_rows]
                extra_count = 0
                match_count = 0

                for ci, cand_row in enumerate(candidate):
                    table_row = table_floats_per_row[ci] if ci < len(table_floats_per_row) else []
                    if len(cand_row) > len(table_row):
                        extra_count += len(cand_row) - len(table_row)
                    if len(table_row) == 0 and len(cand_row) > 0:
                        extra_count += len(cand_row)
                        continue
                    for tf in table_row:
                        if any(abs(cf - tf) < 0.01 for cf in cand_row):
                            match_count += 1

                avg_extra_per_row = extra_count / max(1, n_data_rows)
                if avg_extra_per_row < 1.0:
                    continue
                if not allow_no_match and match_count < 1:
                    continue

                actual_new = max(len(r) for r in candidate)
                if all_table_floats:
                    actual_new = max(0, actual_new - max(len(r) for r in table_floats_per_row))
                if actual_new > MAX_SUPPLEMENT_COLS:
                    continue

                score = match_count * 100 + extra_count * 10 + n_data_rows
                if score > best_score:
                    best_score = score
                    best_matrix = candidate

        if best_matrix is None:
            new_elements.append(elem)
            continue

        n_new_cols = max(len(r) for r in best_matrix)
        # 如果已有浮点数，减去现有列数（只补新增的）
        if all_table_floats and table_floats_per_row:
            max_existing = max(len(r) for r in table_floats_per_row)
            n_new_cols = max(0, n_new_cols - max_existing)
        n_new_cols = min(n_new_cols, MAX_SUPPLEMENT_COLS)
        actual_n_new_cols = n_new_cols

        if actual_n_new_cols <= 0:
            logger.info(f"[Scanned Parse] Table #{ei} no net new columns after adjustment, skip")
            new_elements.append(elem)
            continue

        logger.info(
            f"[Scanned Parse] Table #{ei} supplement found! "
            f"Current={n_cols} cols, adding {actual_n_new_cols} extra cols. "
            f"OCR matrix sample row: {best_matrix[0]}"
        )

        # --- 确定列名（如果表头有空列名，就从 OCR 附近的行猜）---
        extra_header_names = []
        if has_header:
            # 找真实表头行：包含多个列名关键词（不是"单位"行）
            header_line = None
            best_hdr_score = 0
            for li, line in enumerate(plain_ocr_lines):
                score = 0
                if '所属干线' in line or '公路名称' in line or '项目' in line:
                    score += 5
                if '通车里程' in line:
                    score += 3
                if '收费里程' in line:
                    score += 3
                if '里程' in line:
                    score += 1
                if '金额' in line or '万元' in line:
                    score += 2
                # 降权："单位"行通常不是表头
                if '单位' in line:
                    score -= 2
                if score > best_hdr_score and score >= 3:
                    best_hdr_score = score
                    header_line = line

            if header_line:
                logger.info(f"[Scanned Parse] Table #{ei} guessed header line: '{header_line[:60]}...'")
                # 从表头行里找特征关键词
                if '收费里程' in header_line and '通车' in header_line:
                    extra_header_names = ['通车里程', '收费里程']
                elif '通车里程' in header_line:
                    extra_header_names = ['通车里程']
                elif '收费里程' in header_line:
                    extra_header_names = ['收费里程']
                else:
                    found_names = re.findall(
                        r'[^\s\d]{1,10}?(?:里程|金额|长度|数量|公里|万元|面积|数量)',
                        header_line
                    )
                    # 去重保持顺序
                    seen = set()
                    uniq = []
                    for n in found_names:
                        if n not in seen:
                            seen.add(n)
                            uniq.append(n)
                    extra_header_names = uniq[-n_new_cols:] if uniq else []

        # 如果没猜到列名，用默认名
        while len(extra_header_names) < actual_n_new_cols:
            extra_header_names.append(f'列{n_cols + len(extra_header_names) + 1}')

        # --- 基于 2D 矩阵操作，更可靠 ---
        # table_2d 已经是规范化的矩阵（行列对齐），在每一行末尾追加新列即可
        new_table_2d = []
        for ri, row in enumerate(table_2d):
            new_row = list(row)
            if ri == 0 and has_header:
                # 表头行: 加列名
                for i in range(actual_n_new_cols):
                    name = extra_header_names[i] if i < len(extra_header_names) else ''
                    new_row.append(name)
            elif ri >= data_rows_start:
                # 数据行: 追加数字 (从 best_matrix 中取)
                data_idx = ri - data_rows_start
                if 0 <= data_idx < len(best_matrix):
                    num_row = best_matrix[data_idx]
                    # 获取当前行已有的浮点数集合，避免重复
                    existing_floats = set()
                    for cell in row:
                        m = re.match(r'^\s*(\d+\.\d+)\s*$', cell.strip())
                        if m:
                            existing_floats.add(f"{float(m.group(1)):.2f}")

                    added_count = 0
                    for num in num_row:
                        # 允许空字符串（OCR 漏行时的占位）
                        if isinstance(num, str) and num == '':
                            if added_count < actual_n_new_cols:
                                new_row.append('')
                                added_count += 1
                            continue
                        num_str = f"{float(num):.2f}"
                        # 如果当前行已经有这个数字且还没加过任何新列，跳过
                        # (避免把已有的通车里程再加一遍)
                        if num_str in existing_floats and added_count == 0:
                            continue
                        if added_count >= actual_n_new_cols:
                            break
                        new_row.append(num_str)
                        added_count += 1
                    # 如果没加够，补空
                    while added_count < actual_n_new_cols:
                        new_row.append('')
                        added_count += 1
                else:
                    for _ in range(actual_n_new_cols):
                        new_row.append('')
            else:
                # 其他行: 补空
                for _ in range(actual_n_new_cols):
                    new_row.append('')
            new_table_2d.append(new_row)

        # --- 重新生成干净的 HTML 表格 ---
        new_total_cols = n_cols + actual_n_new_cols
        new_html_lines = ["<table border='1' cellpadding='4' cellspacing='0'>"]
        for ri, row in enumerate(new_table_2d):
            is_header_row = (ri == 0 and has_header)
            tag = "th" if is_header_row else "td"
            new_html_lines.append("  <tr>")
            for ci in range(new_total_cols):
                cell = row[ci] if ci < len(row) else ''
                new_html_lines.append(f"    <{tag}>{escape(cell)}</{tag}>")
            new_html_lines.append("  </tr>")
        new_html_lines.append("</table>")
        new_table_html = "\n".join(new_html_lines)

        # 替换表格内容
        new_elem = dict(elem)
        new_elem['content'] = new_table_html
        new_elements.append(new_elem)

        logger.info(
            f"[Scanned Parse] Table supplemented: "
            f"added {actual_n_new_cols} columns. "
            f"Old={n_rows}x{n_cols}, New={len(new_table_2d)}x{new_total_cols}. "
            f"New HTML length: {len(new_table_html)}"
        )

    return new_elements


def _parse_table_html_to_2d(html: str) -> tuple[list[list[str]], bool]:
    """简易 HTML table 解析，返回 2D 单元格矩阵 + 是否有表头。"""
    rows = []
    has_header = False

    # 找所有 <tr>...</tr>
    tr_pattern = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
    td_pattern = re.compile(r'<(t[dh])[^>]*>(.*?)</t[dh]>', re.DOTALL | re.IGNORECASE)

    for tr_match in tr_pattern.finditer(html):
        tr_content = tr_match.group(1)
        cells = []
        row_has_th = False
        for td_match in td_pattern.finditer(tr_content):
            tag = td_match.group(1).lower()
            content = re.sub(r'<[^>]+>', '', td_match.group(2)).strip()
            cells.append(content)
            if tag == 'th':
                row_has_th = True
        if cells:
            rows.append(cells)
            if row_has_th and len(rows) == 1:
                has_header = True

    # 补齐到相同列数
    if rows:
        max_cols = max(len(r) for r in rows)
        for row in rows:
            while len(row) < max_cols:
                row.append('')

    return rows, has_header


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
