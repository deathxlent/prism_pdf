"""
表格提取服务
===========

功能:
    从 PDF 页面中提取表格，输出带 rowspan/colspan 的 HTML 格式。

设计说明:
    1. 非扫描件: 使用 PyMuPDF 原生 find_tables()（稳定可靠，支持跨行跨列）
    2. 扫描件:  使用 OCR 识别表格区域后转为 HTML
    3. 输出格式: 以 HTML 为主（天然支持 colspan/rowspan），Markdown 作为 fallback

坐标处理:
    传入的 bbox 默认是 JPG 图片的像素坐标（200 DPI），
    内部会自动转换为 PDF 点坐标（72 DPI）后再进行提取。
"""

import logging
import fitz
from backend.services import ocr_service_vl as ocr_service
from backend.services.pdf_service import jpg_bbox_to_pdf_bbox, DEFAULT_DPI

ocr_region = ocr_service.ocr_region
extract_table_with_vl = ocr_service.extract_table_with_vl

logger = logging.getLogger(__name__)

# PyMuPDF find_tables 配置参数
TABLE_STRATEGY = "lines"         # 基于线条检测，比lines_strict宽松，能检测到无线框但有分隔线的表格
SNAP_TOLERANCE = 2               # 线条吸附容差（像素）
JOIN_TOLERANCE = 2               # 线条连接容差（像素）


def _parse_span_num(cell_start: float, cell_end: float, indexes: list[float],
                    tolerance: float = 1.0) -> int:
    """
    计算单元格跨越的行/列数（参考 old-code 的 _parse_span_num）。

    原理:
        1. indexes 是排序后的网格线坐标（x 坐标用于 colspan，y 坐标用于 rowspan）
        2. 找到 cell_start 最接近的起始索引，cell_end 最接近的结束索引
        3. 结束索引 - 起始索引 = 跨越的格子数

    Args:
        cell_start: 单元格的起始坐标（左或上）
        cell_end: 单元格的结束坐标（右或下）
        indexes: 排序后的网格线坐标列表
        tolerance: 容差（默认 1 像素）

    Returns:
        跨越的格子数（>= 1）
    """
    if not indexes:
        return 1

    # 找到起始坐标在 indexes 中的位置（允许一定容差）
    start_idx = 0
    for i, val in enumerate(indexes):
        if abs(val - cell_start) <= tolerance:
            start_idx = i
            break
        elif val > cell_start:
            start_idx = max(0, i - 1)
            break
    else:
        start_idx = len(indexes) - 1

    # 找到结束坐标在 indexes 中的位置（允许一定容差）
    end_idx = len(indexes) - 1
    for i in range(len(indexes) - 1, -1, -1):
        if abs(indexes[i] - cell_end) <= tolerance:
            end_idx = i
            break
        elif indexes[i] < cell_end:
            end_idx = min(len(indexes) - 1, i + 1)
            break
    else:
        end_idx = 0

    span = end_idx - start_idx
    return max(1, span)


def _validate_table(table, cell_data: list) -> bool:
    """
    验证检测到的表格是否为真正的表格，过滤误检测（如图表、标题区域等）。
    
    验证规则:
        1. 行数 >= 3（排除只有表头或只有2行的误检测）
        2. 列数 >= 2（排除单列的误检测）
        3. 数据行中至少有一定比例的单元格有内容
        4. 排除所有单元格内容都很短（<2个字符）且无数字的情况（可能是图表标签）
    
    Args:
        table: PyMuPDF Table 对象
        cell_data: 提取的单元格数据
    
    Returns:
        True 表示是有效表格，False 表示是误检测
    """
    if not cell_data or len(cell_data) < 3:
        return False
    
    col_count = len(cell_data[0]) if cell_data else 0
    if col_count < 2:
        return False
    
    # 统计有内容的单元格比例
    total_cells = 0
    non_empty_cells = 0
    has_numeric = False
    
    for row in cell_data:
        for cell in row:
            if cell is None:
                continue
            total_cells += 1
            cell_text = str(cell).strip()
            if cell_text:
                non_empty_cells += 1
                # 检查是否包含数字
                if any(c.isdigit() for c in cell_text):
                    has_numeric = True
    
    if total_cells == 0:
        return False
    
    # 非空单元格比例需要 >= 30%
    non_empty_ratio = non_empty_cells / total_cells
    if non_empty_ratio < 0.3:
        return False
    
    # 至少要有一些数字（排除纯文本标签区域）
    if not has_numeric and table.row_count < 5:
        return False
    
    return True


def _table_to_html(table, force_no_header: bool = False) -> str:
    """
    将 PyMuPDF Table 对象转换为 HTML 表格。

    关键实现:
        1. 使用 table.rows[row].cells[col] 结构，被span覆盖的位置返回 None
        2. 对于非 None 的单元格，检查右侧和下侧连续的 None 数量来计算 colspan/rowspan
        3. 使用 covered 标记矩阵避免重复输出被跨越的单元格
        4. 检测表头行（通过 table.header 或第一行判断）
        5. HTML 特殊字符转义，避免注入

    Args:
        table: PyMuPDF Table 对象（来自 page.find_tables()）
        force_no_header: 强制不识别表头（用于跨页接续的表格）

    Returns:
        HTML 表格字符串，如果没有数据则返回空字符串
    """
    cell_data = table.extract()
    if not cell_data or not cell_data[0]:
        return ""

    row_count = len(cell_data)
    col_count = len(cell_data[0])

    # 检测表头行
    header_y1 = None
    if not force_no_header and table.header and table.header.cells and table.rows:
        # 使用第一行中最小的y1作为表头分界
        # 注意：第一行可能包含跨行单元格（y1很大），所以取最小的y1
        # 即没有跨行的单元格的底部，作为表头行的实际结束位置
        first_row = table.rows[0]
        valid_cells = [c for c in first_row.cells if c is not None]
        if valid_cells:
            header_y1 = min(c[3] for c in valid_cells)

    # ── 步骤1: 构建覆盖标记矩阵 ────────────────────────────────────
    covered = [[False for _ in range(col_count)] for _ in range(row_count)]

    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]

    # ── 步骤2: 遍历行列生成 HTML ──────────────────────────────────
    for row_idx in range(row_count):
        html_parts.append("  <tr>")
        for col_idx in range(col_count):
            # 如果当前位置已被前面的跨行跨列覆盖，则跳过
            if covered[row_idx][col_idx]:
                continue

            # 获取当前单元格的 bbox（使用 table.rows[row].cells[col]）
            row_obj = table.rows[row_idx]
            cell_bbox = row_obj.cells[col_idx] if col_idx < len(row_obj.cells) else None

            if cell_bbox is None:
                # 理论上不应该到这里，因为 covered 应该已经标记了
                covered[row_idx][col_idx] = True
                continue

            x0, y0, x1, y1 = cell_bbox

            # ── 计算 colspan: 检查右侧连续的 None ──
            colspan = 1
            for c in range(col_idx + 1, col_count):
                if row_obj.cells[c] is None:
                    colspan += 1
                else:
                    break

            # ── 计算 rowspan: 检查下侧连续的 None ──
            rowspan = 1
            for r in range(row_idx + 1, row_count):
                next_row = table.rows[r]
                if col_idx < len(next_row.cells) and next_row.cells[col_idx] is None:
                    rowspan += 1
                else:
                    break

            # 边界检查
            if row_idx + rowspan > row_count:
                rowspan = row_count - row_idx
            if col_idx + colspan > col_count:
                colspan = col_count - col_idx
            rowspan = max(1, rowspan)
            colspan = max(1, colspan)

            # 标记被覆盖的位置
            for r in range(row_idx, row_idx + rowspan):
                for c in range(col_idx, col_idx + colspan):
                    if r < row_count and c < col_count:
                        covered[r][c] = True

            # 获取单元格文本
            cell_value = cell_data[row_idx][col_idx] or ""

            # 判断是否为表头
            is_header = False
            if not force_no_header:
                if header_y1 is not None:
                    is_header = (y1 <= header_y1 + 1)  # 允许1像素容差
                else:
                    is_header = (row_idx == 0)

            tag = "th" if is_header else "td"

            # 构建 span 属性
            span_attrs = ""
            if colspan > 1:
                span_attrs += f" colspan='{colspan}'"
            if rowspan > 1:
                span_attrs += f" rowspan='{rowspan}'"

            # HTML 特殊字符转义
            cell_value = cell_value.replace("&", "&amp;")
            cell_value = cell_value.replace("<", "&lt;").replace(">", "&gt;")

            html_parts.append(f"    <{tag}{span_attrs}>{cell_value}</{tag}>")
        html_parts.append("  </tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts)


def _text_to_html_table(text: str) -> str:
    """
    当 find_tables 未检测到表格时，尝试从纯文本构建 HTML 表格。

    这是 fallback 方案，参考 old-code 中未检测到表格时的处理逻辑:
        - 按行分割文本
        - 尝试用 | 或空白符分割单元格
        - 生成简单的 HTML 表格（无 span）

    Args:
        text: 从 PDF 区域提取的纯文本

    Returns:
        HTML 表格字符串，如果文本为空则返回空字符串
    """
    if not text or not text.strip():
        return ""

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return ""

    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]

    for i, line in enumerate(lines):
        # 优先尝试用 | 分割，其次用多空格分割
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) <= 1:
            cells = [c.strip() for c in line.split() if c.strip()]
        if not cells:
            cells = [line]

        tag = "th" if i == 0 else "td"
        html_parts.append("  <tr>")
        for cell in cells:
            cell = cell.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(f"    <{tag}>{cell}</{tag}>")
        html_parts.append("  </tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts)


def _markdown_to_html_simple(md: str) -> str:
    """
    简单的 Markdown 表格转 HTML（无 span 支持，仅作 fallback）。

    注意: Markdown 表格语法本身不支持跨行跨列，
    所以这只是一个简化的转换，不保证复杂表格的正确性。

    Args:
        md: Markdown 格式的表格文本

    Returns:
        HTML 表格字符串
    """
    if not md or not md.strip():
        return ""

    lines = md.strip().split("\n")
    if len(lines) < 2:
        return ""

    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]

    # 第一行是表头
    header_cells = [c.strip() for c in lines[0].split("|") if c.strip()]
    html_parts.append("  <tr>")
    for cell in header_cells:
        cell = cell.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        html_parts.append(f"    <th>{cell}</th>")
    html_parts.append("  </tr>")

    # 跳过第二行（分隔线），从第三行开始是数据
    for line in lines[2:]:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if not cells:
            continue
        html_parts.append("  <tr>")
        for cell in cells:
            cell = cell.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            html_parts.append(f"    <td>{cell}</td>")
        html_parts.append("  </tr>")

    html_parts.append("</table>")
    return "\n".join(html_parts)


def _find_valid_table(pdf_page: fitz.Page, rect: fitz.Rect) -> tuple:
    """
    使用多级策略查找有效的表格。
    
    策略优先级:
        1. lines策略（宽松的线条检测）
        2. lines_strict策略（严格的线条检测）
        3. text策略（基于文本排列检测，可能不准确）
    
    每个策略检测到表格后都会进行有效性验证。
    """
    # 稍微扩大检测区域，避免边界截断导致的行/列丢失
    # 左右各扩大3个PDF点，顶部扩大3个点，底部扩大20个点（layout边界检测经常截断底部内容）
    expansion_x = 3.0
    expansion_y_top = 3.0
    expansion_y_bottom = 20.0
    expanded_rect = fitz.Rect(
        max(0, rect.x0 - expansion_x),
        max(0, rect.y0 - expansion_y_top),
        min(pdf_page.rect.x1, rect.x1 + expansion_x),
        min(pdf_page.rect.y1, rect.y1 + expansion_y_bottom),
    )
    
    strategies = ["lines", "lines_strict", "text"]
    
    for strategy in strategies:
        try:
            finder = pdf_page.find_tables(
                clip=expanded_rect,
                strategy=strategy,
                snap_tolerance=SNAP_TOLERANCE,
                join_tolerance=JOIN_TOLERANCE,
            )
            
            if not finder.tables:
                continue
            
            # 遍历所有检测到的表格，找第一个有效的
            for table in finder.tables:
                cell_data = table.extract()
                if _validate_table(table, cell_data):
                    logger.info(f"Using '{strategy}' strategy, found valid table: {table.row_count}x{table.col_count}")
                    return table, cell_data, strategy
            
            logger.debug(f"Strategy '{strategy}' found tables but none passed validation")
            
        except Exception as e:
            logger.debug(f"Strategy '{strategy}' failed: {e}")
            continue
    
    return None, None, None


def extract_table_from_native(pdf_page: fitz.Page,
                              bbox: tuple[float, float, float, float] | None,
                              bbox_is_jpg: bool = True,
                              dpi: int = DEFAULT_DPI,
                              force_no_header: bool = False) -> dict:
    """
    从非扫描 PDF 页面提取表格（使用 PyMuPDF 原生方案）。

    流程:
        1. 坐标转换: 如果传入的是 JPG 像素坐标，先转为 PDF 点坐标
        2. 表格检测: 使用多级策略（lines → lines_strict → text）检测有效表格
        3. HTML 生成: 将检测到的表格转换为带 rowspan/colspan 的 HTML
        4. Fallback: 如果未检测到有效表格，尝试从纯文本构建 HTML

    Args:
        pdf_page: PyMuPDF Page 对象
        bbox: 表格区域坐标 (x1, y1, x2, y2)，传 None 则检测整页
        bbox_is_jpg: bbox 是否为 JPG 像素坐标（默认 True，会自动转换）
        dpi: JPG 图片的 DPI，用于坐标转换（默认 200）
        force_no_header: 强制不识别表头（用于跨页接续的表格）

    Returns:
        字典包含:
            - html: HTML 格式的表格（主要输出）
            - markdown: Markdown 格式的表格（fallback）
            - rows: 行数
            - cols: 列数
            - strategy: 使用的检测策略
    """
    # ── 步骤1: 坐标转换 ──────────────────────────────────────────────
    if bbox is not None and bbox_is_jpg:
        # JPG 像素坐标 → PDF 点坐标: pdf = jpg * (72 / dpi)
        pdf_bbox = jpg_bbox_to_pdf_bbox(bbox, dpi)
        rect = fitz.Rect(pdf_bbox)
    elif bbox is not None:
        rect = fitz.Rect(bbox)
    else:
        rect = pdf_page.rect

    # 稍微扩大检测区域，避免边界截断导致的行/列丢失
    # 左右各扩大3个PDF点，顶部扩大3个点，底部扩大20个点（layout边界检测经常截断底部内容）
    if bbox is not None:
        expansion_x = 3.0
        expansion_y_top = 3.0
        expansion_y_bottom = 20.0
        rect.x0 = max(0, rect.x0 - expansion_x)
        rect.y0 = max(0, rect.y0 - expansion_y_top)
        rect.x1 = min(pdf_page.rect.x1, rect.x1 + expansion_x)
        rect.y1 = min(pdf_page.rect.y1, rect.y1 + expansion_y_bottom)

    # 边界检查
    if rect.is_empty or not rect.is_valid:
        logger.warning(f"Invalid table bbox: {bbox}")
        return {"html": "", "markdown": "", "rows": 0, "cols": 0, "strategy": "none"}

    # ── 步骤2: 使用多级策略检测有效表格 ────────────────────────────────
    table, cell_data, strategy = _find_valid_table(pdf_page, rect)

    # ── 步骤3: 处理检测结果 ─────────────────────────────────────────
    if table is None:
        # 未检测到有效表格，fallback 到纯文本解析
        logger.debug("No valid tables detected, trying text fallback")
        text = pdf_page.get_text("text", clip=rect)
        html = _text_to_html_table(text)
        # 粗略估算行列数
        lines = [l for l in text.split("\n") if l.strip()]
        cols = 0
        if lines:
            cols = max(len(l.split("|")) for l in lines)
        return {
            "html": html,
            "markdown": "",
            "rows": len(lines),
            "cols": cols,
            "strategy": "text_fallback",
        }

    # ── 步骤4: 生成 HTML ──
    try:
        html = _table_to_html(table, force_no_header=force_no_header)
    except Exception as e:
        logger.warning(f"Table to HTML conversion failed: {e}")
        html = ""

    # Markdown 作为 fallback（注意: 不支持 rowspan/colspan）
    try:
        markdown = table.to_markdown()
    except Exception as e:
        logger.debug(f"Table to Markdown failed: {e}")
        markdown = ""

    return {
        "html": html,
        "markdown": markdown,
        "rows": table.row_count,
        "cols": table.col_count,
        "strategy": strategy,
    }


def extract_table_from_scanned(image_path: str, bbox: tuple) -> dict:
    """
    从扫描件 PDF 提取表格（使用 PaddleOCR-VL GGUF 方案）。

    流程:
        1. 调用 llama-server API，使用 "Table Recognition:" 提示词
        2. 解析 PaddleOCR-VL 的 <fcel>/<nl>/<ucel> 结构化输出
        3. 生成支持 rowspan/colspan 的 HTML 表格

    Args:
        image_path: 页面 JPG 图片路径
        bbox: 表格区域在 JPG 图片中的坐标（像素）

    Returns:
        字典包含:
            - html: HTML 格式的表格
            - markdown: Markdown 格式的表格
            - rows: 行数
            - cols: 列数
    """
    try:
        result = extract_table_with_vl(image_path, bbox)
        if result.get("html") or result.get("rows", 0) > 0:
            return result
    except Exception as e:
        logger.warning(f"VL table extraction failed, falling back: {e}")

    text = ocr_region(image_path, bbox)
    if not text.strip():
        return {"html": "", "markdown": "", "rows": 0, "cols": 0}

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    md_lines = []
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.split() if c.strip()]
        if not cells:
            cells = [line]
        md_lines.append("| " + " | ".join(cells) + " |")
        if i == 0:
            md_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")

    markdown = "\n".join(md_lines)
    html = _text_to_html_table(text)
    rows = len(lines)
    cols = 0
    if md_lines:
        first_line_cells = [c for c in md_lines[0].split("|") if c.strip()]
        cols = len(first_line_cells)

    return {
        "html": html,
        "markdown": markdown,
        "rows": rows,
        "cols": cols,
    }
