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
            # 泛用逻辑: 如果前3行中，选择长度适中且不是纯数字的行作为页眉候选
            found_header_idx = -1
            for i in range(min(3, len(plain_ocr_lines))):
                line = plain_ocr_lines[i]
                # 跳过纯数字行（可能是页码）
                if re.match(r'^\s*\d+\s*$', line):
                    continue
                # 跳过过短或过长的行
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
