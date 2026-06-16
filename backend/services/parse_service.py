import logging
import asyncio
import re
import fitz
from pathlib import Path
from backend import database as db
from backend.services.pdf_service import (
    validate_pdf, prepare_pages, extract_text_in_region, detect_garbled_text
)
from backend.services.layout_service import detect_layout_batch, deduplicate_header_footer
from backend.services.order_service import assign_reading_order, assign_reading_order_batch
from backend.services.ocr_service_vl import ocr_region, ocr_formula, ocr_batch, ocr_batch_multi_image
from backend.services.table_service import extract_table_from_native, extract_table_from_scanned
from backend.services.picture_service import extract_picture
from backend.services.scanned_parse_service import parse_scanned_page_full

logger = logging.getLogger(__name__)

_parse_progress: dict[int, dict] = {}

TEXT_TYPES = {"Caption", "Footnote", "List-item", "Page-footer", "Page-header",
              "Section-header", "Text", "Title"}


def _extract_table_plain_text_from_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


def _get_first_data_row_plain(table_plain: str) -> list:
    if not table_plain:
        return []
    lines = [l.strip() for l in table_plain.split('\n') if l.strip()]
    if not lines:
        return []
    first_line = lines[0] if len(lines) > 0 else ""
    return [c.strip() for c in first_line.split() if c.strip()]


def _get_last_data_row_plain(table_plain: str) -> list:
    if not table_plain:
        return []
    lines = [l.strip() for l in table_plain.split('\n') if l.strip()]
    if not lines:
        return []
    last_line = lines[-1] if lines else ""
    return [c.strip() for c in last_line.split() if c.strip()]


def _save_ocr_raw_output(jpg_path: str, page_number: int, doc_dir: str):
    try:
        import json
        from datetime import datetime
        ocr_raw_dir = Path(doc_dir) / "ocr_raw_output"
        ocr_raw_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = ocr_raw_dir / f"page_{page_number}_{timestamp}.txt"

        log_content = []
        log_content.append(f"=== OCR Raw Output for Page {page_number} ===")
        log_content.append(f"Timestamp: {datetime.now().isoformat()}")
        log_content.append(f"Image Path: {jpg_path}")
        log_content.append("")

        try:
            from backend.services.ocr_service_vl import _get_last_raw_response
            raw_response = _get_last_raw_response()
            if raw_response:
                log_content.append("--- Llama Server Raw Response ---")
                if isinstance(raw_response, (dict, list)):
                    log_content.append(json.dumps(raw_response, ensure_ascii=False, indent=2))
                else:
                    log_content.append(str(raw_response))
            else:
                log_content.append("(No raw response captured)")
        except Exception as e:
            log_content.append(f"(Failed to get raw response: {e})")

        log_content.append("")
        log_content.append("=== END ===")

        with open(log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(log_content))

        logger.info(f"OCR raw output saved to: {log_file}")
    except Exception as e:
        logger.warning(f"Failed to save OCR raw output for page {page_number}: {e}")


def set_parse_progress(doc_id: int, stage: str, percent: float, message: str = ""):
    _parse_progress[doc_id] = {
        "stage": stage,
        "percent": round(percent, 1),
        "message": message,
        "updated_at": _get_progress_time()
    }
    logger.info(f"Parse progress for doc {doc_id}: {percent:.1f}% - {stage} - {message}")


def get_parse_progress(doc_id: int) -> dict:
    return _parse_progress.get(doc_id, {"stage": "idle", "percent": 0, "message": ""})


def clear_parse_progress(doc_id: int):
    if doc_id in _parse_progress:
        del _parse_progress[doc_id]


def _get_progress_time() -> str:
    from datetime import datetime
    return datetime.now().isoformat()


async def process_upload(file_path: str, original_filename: str) -> dict:
    validation = validate_pdf(file_path)
    if not validation["valid"]:
        return {"error": validation["error"], "encrypted": validation["encrypted"]}

    if validation["encrypted"]:
        return {"error": "PDF is encrypted", "encrypted": True}

    import os
    file_size = os.path.getsize(file_path)
    filename = Path(file_path).name

    doc_id = await db.create_document(filename, original_filename, file_path, file_size)
    await db.update_document(doc_id, page_count=validation["page_count"], status="validated")

    return {"document_id": doc_id, "page_count": validation["page_count"]}


async def process_document(doc_id: int):
    doc_info = await db.get_document(doc_id)
    if not doc_info:
        logger.error(f"Document {doc_id} not found")
        clear_parse_progress(doc_id)
        return

    try:
        set_parse_progress(doc_id, "initializing", 5, "开始处理文档")
        await db.update_document(doc_id, status="processing")

        file_path = doc_info["file_path"]
        doc_dir = str(Path(file_path).parent / Path(file_path).stem)
        
        set_parse_progress(doc_id, "preparing_pages", 10, "准备页面数据")
        pages_info = await asyncio.to_thread(prepare_pages, file_path, doc_dir)
        total_pages = len(pages_info)

        for i, page_info in enumerate(pages_info):
            page_id = await db.create_page(
                doc_id,
                page_info["page_number"],
                page_info["width"],
                page_info["height"],
                page_info["jpg_width"],
                page_info["jpg_height"],
                page_info["jpg_path"],
                page_info["single_pdf_path"],
            )
            await db.update_page(page_id, is_scanned=1 if page_info["is_scanned"] else 0)
            set_parse_progress(doc_id, "preparing_pages", 10 + (i + 1) / total_pages * 20, 
                              f"创建页面 {page_info['page_number']}/{total_pages}")

        await db.update_document(doc_id, status="pages_ready")

        pages = await db.get_pages(doc_id)

        all_jpg_paths = []
        non_scanned_indices = []
        for page_idx, page in enumerate(pages):
            jpg_path = page["jpg_path"]
            all_jpg_paths.append(jpg_path)
            if not page.get("is_scanned"):
                non_scanned_indices.append(page_idx)

        non_scanned_jpg_paths = [all_jpg_paths[i] for i in non_scanned_indices]
        logger.info(f"Total pages: {len(pages)}, non-scanned: {len(non_scanned_indices)}, scanned: {len(pages) - len(non_scanned_indices)}")

        layouts_with_order = [[] for _ in range(len(pages))]

        if non_scanned_jpg_paths:
            set_parse_progress(doc_id, "parsing_layout", 35, f"批量检测布局（{len(non_scanned_indices)} 个非扫描页）...")
            logger.info("Batch detecting layouts for non-scanned pages...")
            non_scanned_layouts = await asyncio.to_thread(detect_layout_batch, non_scanned_jpg_paths)

            set_parse_progress(doc_id, "parsing_layout", 50, f"分配阅读顺序（{len(non_scanned_indices)} 个非扫描页）...")
            logger.info("Batch assigning reading orders for non-scanned pages...")
            non_scanned_with_order = await asyncio.to_thread(
                assign_reading_order_batch, non_scanned_layouts, non_scanned_jpg_paths
            )

            for i, ns_idx in enumerate(non_scanned_indices):
                layouts_with_order[ns_idx] = non_scanned_with_order[i]

        for page_idx, page in enumerate(pages):
            try:
                page["_elements"] = layouts_with_order[page_idx]
                if page.get("is_scanned"):
                    logger.info(f"Page {page['page_number']}: scanned page, will use direct PaddleOCR-VL full-page parse (skip YOLO+Surya)")
            except Exception as e:
                    logger.error(f"Failed to assign reading order for page {page['page_number']}: {e}")
                    page["_elements"] = []

        # 用于跨页表格检测：记录前一页最后一个表格的特征
        prev_page_table_info = None
        cross_page_group_counter = 0
        
        for i, page in enumerate(pages):
            try:
                set_parse_progress(doc_id, "parsing_content", 55 + (i / total_pages) * 40, 
                                  f"解析页面 {page['page_number']}/{total_pages}")
                current_page_table_info, cross_page_group_counter = await _parse_page(
                    doc_id, page, doc_dir, prev_page_table_info, cross_page_group_counter
                )
                prev_page_table_info = current_page_table_info
            except Exception as e:
                logger.error(f"Failed to parse page {page['page_number']}: {e}")
                prev_page_table_info = None
                await db.update_page(page["id"], status="failed", error_message=str(e))

        set_parse_progress(doc_id, "completed", 100, "解析完成")
        await db.update_document(doc_id, status="completed")
        clear_parse_progress(doc_id)

    except Exception as e:
        logger.error(f"Failed to process document {doc_id}: {e}")
        set_parse_progress(doc_id, "failed", 0, f"解析失败: {str(e)}")
        await db.update_document(doc_id, status="failed", error_message=str(e))


def _is_continuation_table(curr_table_cols: int, curr_first_row: list, 
                          prev_table_cols: int, prev_last_row: list) -> bool:
    """
    判断当前表格是否是前一页表格的接续。
    """
    if curr_table_cols != prev_table_cols:
        return False
    
    curr_first_col = str(curr_first_row[0]).strip() if curr_first_row and curr_first_row[0] else ""
    prev_last_col = str(prev_last_row[0]).strip() if prev_last_row and prev_last_row[0] else ""
    
    if not curr_first_col and not prev_last_col:
        return True
    
    def has_digit(s: str) -> bool:
        return any(c.isdigit() for c in s)
    
    prev_has_digit = any(has_digit(str(c)) for c in prev_last_row if c)
    curr_has_digit = any(has_digit(str(c)) for c in curr_first_row if c)
    
    if prev_has_digit and curr_has_digit:
        return True
    
    return False


def _parse_html_table(html: str) -> list[list[dict]]:
    """
    解析 HTML 表格为二维单元格矩阵。
    
    返回: list[list[dict]]，每个单元格包含:
        - content: str
        - is_header: bool 
        - rowspan: int
        - colspan: int
        - covered: bool (是否被其他单元格的 rowspan/colspan 覆盖)
    """
    if not html:
        return []
    
    from html import unescape
    rows_match = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    if not rows_match:
        return []
    
    temp_matrix = []  # 临时矩阵，存储实际输出的单元格
    max_cols = 0
    
    for ri, row_html in enumerate(rows_match):
        # 提取所有 td/th
        cells_match = re.findall(r'<(t[dh])[^>]*>(.*?)</\1>', row_html, re.DOTALL | re.IGNORECASE)
        
        row_cells = []
        for tag, cell_html in cells_match:
            tag = tag.lower()
            is_header = tag == 'th'
            
            # 提取 rowspan
            rs_match = re.search(r"rowspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            rowspan = int(rs_match.group(1)) if rs_match else 1
            
            # 提取 colspan
            cs_match = re.search(r"colspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            colspan = int(cs_match.group(1)) if cs_match else 1
            
            # 提取文本内容（去除HTML标签）
            content = re.sub(r'<[^>]+>', '', cell_html).strip()
            content = unescape(content)
            
            row_cells.append({
                'content': content,
                'is_header': is_header,
                'rowspan': rowspan,
                'colspan': colspan,
                'row_idx': ri,
            })
        
        if row_cells:
            temp_matrix.append(row_cells)
            row_col_count = sum(c['colspan'] for c in row_cells)
            max_cols = max(max_cols, row_col_count)
    
    # 构建完整的矩阵（包含被覆盖的位置）
    if not temp_matrix:
        return []
    
    full_matrix = [[None for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    covered = [[False for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    
    for ri, row_cells in enumerate(temp_matrix):
        col_pos = 0
        for cell in row_cells:
            # 跳过已被覆盖的位置
            while col_pos < max_cols and covered[ri][col_pos]:
                col_pos += 1
            if col_pos >= max_cols:
                break
            
            rs = cell['rowspan']
            cs = cell['colspan']
            
            full_matrix[ri][col_pos] = {
                'content': cell['content'],
                'is_header': cell['is_header'],
                'rowspan': rs,
                'colspan': cs,
            }
            
            # 标记覆盖区域
            for r in range(ri, min(ri + rs, len(temp_matrix))):
                for c in range(col_pos, min(col_pos + cs, max_cols)):
                    if r != ri or c != col_pos:
                        covered[r][c] = True
            
            col_pos += cs
    
    return full_matrix


def _merge_cross_page_empty_cells(prev_html: str, curr_html: str) -> tuple[str, str, list]:
    """
    处理跨页表格接续：将当前页表格第一行的空单元格合并到上一页最后一行。
    
    规则:
    - 当前页第一行的空单元格（空格或空字符串）向上合并到上一页最后一行对应列
    - 如果连续左侧多列为空，则还需要处理向左合并（增加上一行单元格的 colspan）
    - 合并后更新 rowspan 和 colspan
    
    Returns:
        (updated_prev_html, updated_curr_html, curr_first_row_non_empty_cells)
    """
    if not prev_html or not curr_html:
        return (prev_html, curr_html, [])
    
    from html import escape
    
    prev_matrix = _parse_html_table(prev_html)
    curr_matrix = _parse_html_table(curr_html)
    
    if not prev_matrix or not curr_matrix:
        return (prev_html, curr_html, [])
    
    prev_rows = len(prev_matrix)
    curr_rows = len(curr_matrix)
    if prev_rows == 0 or curr_rows == 0:
        return (prev_html, curr_html, [])
    
    max_cols = max(len(prev_matrix[0]), len(curr_matrix[0]))
    
    # 获取当前页第一行所有单元格，检查哪些是空的
    curr_first_row = curr_matrix[0]
    prev_last_row = prev_matrix[-1]
    
    empty_cols_in_first_row = []
    non_empty_cells = []
    
    for ci in range(min(max_cols, len(curr_first_row))):
        cell = curr_first_row[ci]
        if cell is None:
            continue
        content = cell.get('content', '').strip()
        if not content:
            empty_cols_in_first_row.append(ci)
        else:
            non_empty_cells.append(cell.get('content', ''))
    
    if not empty_cols_in_first_row:
        return (prev_html, curr_html, non_empty_cells)
    
    # 计算需要合并的列：连续的空列向左合并到上一行
    # 策略：从左到右找第一个非空列之前的所有空列，合并到上一行最左边的非空单元格
    first_non_empty_col = None
    for ci in range(len(curr_first_row)):
        cell = curr_first_row[ci]
        if cell and cell.get('content', '').strip():
            first_non_empty_col = ci
            break
    
    # 修改前一页最后一行：增加对应单元格的 rowspan
    # 修改当前页：将第一行空单元格标记为 covered（通过 rowspan 从 prev 延伸）
    # 实际操作：重新生成 HTML
    
    def _build_html_from_matrix(matrix, first_row_force_no_header=False):
        if not matrix:
            return ""
        rows = len(matrix)
        cols = len(matrix[0])
        covered = [[False for _ in range(cols)] for _ in range(rows)]
        
        html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]
        for ri in range(rows):
            html_parts.append("  <tr>")
            for ci in range(cols):
                if covered[ri][ci]:
                    continue
                cell = matrix[ri][ci]
                if cell is None:
                    continue
                
                is_header = cell.get('is_header', False)
                if first_row_force_no_header and ri == 0:
                    is_header = False
                rowspan = cell.get('rowspan', 1)
                colspan = cell.get('colspan', 1)
                content = escape(cell.get('content', ''))
                
                tag = "th" if is_header else "td"
                attrs = ""
                if rowspan > 1:
                    attrs += f" rowspan='{rowspan}'"
                if colspan > 1:
                    attrs += f" colspan='{colspan}'"
                
                html_parts.append(f"    <{tag}{attrs}>{content}</{tag}>")
                
                for r in range(ri, min(ri + rowspan, rows)):
                    for c in range(ci, min(ci + colspan, cols)):
                        if r != ri or c != ci:
                            covered[r][c] = True
            html_parts.append("  </tr>")
        html_parts.append("</table>")
        return "\n".join(html_parts)
    
    # 构建新的 prev_matrix：增加最后一行对应空列位置的 rowspan
    new_prev_matrix = [row[:] for row in prev_matrix]
    for ci in empty_cols_in_first_row:
        # 找到上一页最后一行中，这个位置的单元格或者左边最近的非空单元格
        target_ci = ci
        while target_ci >= 0 and prev_last_row[target_ci] is None:
            target_ci -= 1
        if target_ci >= 0 and prev_last_row[target_ci]:
            # 如果这个单元格还没被扩展，增加 rowspan
            # 同时也要处理 colspan（如果连续多个空列）
            if new_prev_matrix[-1][target_ci]:
                existing_rs = new_prev_matrix[-1][target_ci].get('rowspan', 1)
                new_prev_matrix[-1][target_ci]['rowspan'] = existing_rs + 1
    
    # 如果连续多个空列，需要合并到最左边非空单元格的 colspan
    # 注意：只有在该范围内的所有列在上一行中都是 None（已被现有 colspan 覆盖）时，
    # 才扩展 colspan。如果范围内有独立内容的单元格（如 [C, D] + cont [empty, E]），
    # 则不应扩展 colspan，否则会覆盖独立单元格的内容（D 消失）。
    if (empty_cols_in_first_row and first_non_empty_col is not None and first_non_empty_col > 0):
        # 检查范围内是否所有列在 prev_last_row 中都是 None（已被 colspan 覆盖）
        all_covered_by_colspan = True
        for ci in range(1, first_non_empty_col):
            if (ci < len(prev_last_row) and prev_last_row[ci] is not None
                    and prev_last_row[ci].get('content', '').strip()):
                all_covered_by_colspan = False
                break
        
        if all_covered_by_colspan:
            leftmost_target = None
            for ci in range(first_non_empty_col):
                if ci < len(prev_last_row) and prev_last_row[ci] and prev_last_row[ci].get('content', '').strip():
                    leftmost_target = ci
                    break
            
            if leftmost_target is None:
                leftmost_target = 0
            
            # 增加这个单元格的 colspan 以覆盖所有空列
            if new_prev_matrix[-1][leftmost_target]:
                total_empty_cols = first_non_empty_col - leftmost_target
                existing_cs = new_prev_matrix[-1][leftmost_target].get('colspan', 1)
                new_prev_matrix[-1][leftmost_target]['colspan'] = existing_cs + total_empty_cols
                
                # 标记被覆盖的空列位置为 None（在 prev 最后一行中）
                for ci in range(leftmost_target + 1, first_non_empty_col):
                    if ci < len(new_prev_matrix[-1]):
                        new_prev_matrix[-1][ci] = None
    
    # 构建新的 curr_matrix：移除第一行中被合并的空单元格（它们将从 prev 延伸）
    new_curr_matrix = []
    for ri, row in enumerate(curr_matrix):
        if ri == 0:
            # 处理第一行：保留非空单元格，移除被合并的空单元格
            new_row = []
            for ci, cell in enumerate(row):
                if cell is None:
                    new_row.append(None)
                    continue
                if ci in empty_cols_in_first_row:
                    # 这个空单元格被上一行覆盖，跳过
                    new_row.append(None)
                else:
                    new_row.append(cell.copy() if cell else None)
            new_curr_matrix.append(new_row)
        else:
            new_curr_matrix.append([c.copy() if c else None for c in row])
    
    new_prev_html = _build_html_from_matrix(new_prev_matrix)
    new_curr_html = _build_html_from_matrix(new_curr_matrix, first_row_force_no_header=True)
    
    return (new_prev_html, new_curr_html, non_empty_cells)


async def _parse_page(doc_id: int, page_info: dict, doc_dir: str, 
                      prev_page_table_info: dict = None,
                      cross_page_group_counter: int = 0):
    page_id = page_info["id"]
    jpg_path = page_info["jpg_path"]
    single_pdf_path = page_info["single_pdf_path"]
    is_scanned = page_info["is_scanned"]
    elements = page_info.get("_elements", [])
    
    from backend.services.pdf_service import jpg_bbox_to_pdf_bbox, DEFAULT_DPI
    
    current_page_last_table_info = None
    current_cross_page_group = None
    last_table_result_idx = None

    await db.update_page(page_id, status="parsing_content")

    pdf_doc = fitz.open(single_pdf_path)
    pdf_page = pdf_doc[0]

    output_dir = str(Path(doc_dir) / "output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # ==================== 扫描版 PDF 直接解析分支 ====================
    # 先做 YOLO layout 提取 Picture/Figure (logo 等)，
    # 再调用 PaddleOCR-VL 1.6 Table Recognition 整页解析文本/表格，
    # 最后按坐标合并两部分结果
    if is_scanned and not elements:
        logger.info(f"Page {page_info['page_number']}: SCANNED PAGE -> using YOLO layout + PaddleOCR-VL full-page parse")
        try:
            from PIL import Image
            with Image.open(jpg_path) as im:
                jpg_w, jpg_h = im.size

            _save_ocr_raw_output(jpg_path, page_info["page_number"], doc_dir)

            # Step A: 先做 YOLO layout，专门提取 Picture/Figure (logo 等 OCR 不识别的元素)
            picture_elements = []
            try:
                from backend.services.layout_service import detect_layout
                raw_layout = await asyncio.to_thread(detect_layout, jpg_path)
                for le in raw_layout:
                    if le["element_type"] in ("Picture", "Figure"):
                        elem_bbox = le["bbox"]
                        elem_area = (elem_bbox[2] - elem_bbox[0]) * (elem_bbox[3] - elem_bbox[1])
                        page_area = jpg_w * jpg_h
                        # 过滤掉过大的 Picture (可能是误检的整页背景)
                        if elem_area < page_area * 0.5:
                            picture_elements.append({
                                "element_type": le["element_type"],
                                "bbox": elem_bbox,
                                "confidence": le["confidence"],
                                "reading_order": 0,
                                "content": "",
                                "content_format": "image_path",
                                "_is_layout_picture": True,
                            })
                logger.info(f"Page {page_info['page_number']}: YOLO layout found {len(picture_elements)} Picture/Figure elements")
            except Exception as layout_e:
                logger.warning(f"Page {page_info['page_number']}: YOLO layout failed (non-critical): {layout_e}")

            # Step B: 调用 PaddleOCR-VL 整页解析文本/表格
            # 注意: 跨页表头和空单元格合并在后续保存元素时处理
            scanned_elements = await asyncio.to_thread(
                parse_scanned_page_full, jpg_path, jpg_w, jpg_h
            )

            # Step C: 合并 Picture/Figure 和 OCR 解析结果，用 Surya 模型分配阅读顺序
            all_elements = picture_elements + scanned_elements
            all_elements = await asyncio.to_thread(
                assign_reading_order, all_elements, jpg_path
            )

            element_count = {
                "Text": 0, "Section-header": 0, "Title": 0, "Table": 0,
                "Figure": 0, "Picture": 0, "Formula": 0, "List-item": 0,
                "Page-header": 0, "Page-footer": 0, "Caption": 0,
            }

            # 跨页表格判断辅助: 统计表格之前是否有"有效主体内容"
            # 跳过: Page-header / Page-footer / 角落的小Picture(logo) / Caption
            NON_BODY_TYPES = {"Page-header", "Page-footer", "Caption"}
            def _is_corner_logo(elem_type, bbox, w, h):
                if elem_type not in ("Picture", "Figure"):
                    return False
                x0, y0, x1, y1 = bbox
                bw, bh = x1 - x0, y1 - y0
                # 四个角落 15% 区域内的小图片
                corner_region_w = w * 0.25
                corner_region_h = h * 0.20
                max_size = max(w, h) * 0.20
                if bw > max_size or bh > max_size:
                    return False
                in_top = y1 < corner_region_h
                in_bottom = y0 > h - corner_region_h
                in_left = x1 < corner_region_w
                in_right = x0 > w - corner_region_w
                return (in_top or in_bottom) and (in_left or in_right)

            has_body_content_before_first_table = False
            first_table_elem_idx = None
            saved_element_ids = []

            for elem_idx, elem in enumerate(all_elements):
                try:
                    elem_type = elem.get("element_type", "Text")
                    bbox = elem.get("bbox", (0, 0, 0, 0))
                    confidence = elem.get("confidence", 0.8)
                    reading_order = elem.get("reading_order", 0)
                    content = elem.get("content", "") or ""
                    content_format = elem.get("content_format", "markdown")
                    is_layout_picture = elem.get("_is_layout_picture", False)

                    # 如果是 layout 检测到的 Picture，需要从 PDF 中裁剪图片
                    if is_layout_picture and elem_type in ("Picture", "Figure"):
                        try:
                            result = await asyncio.to_thread(
                                extract_picture, pdf_page, bbox, output_dir, page_id * 10000 + reading_order
                            )
                            content = result.get("image_path", "")
                            content_format = "image_path"
                        except Exception as pic_e:
                            logger.warning(f"Failed to extract picture at {bbox}: {pic_e}")

                    # 跨页表格判断: 统计表格前的有效主体内容
                    if elem_type == "Table" and first_table_elem_idx is None:
                        first_table_elem_idx = elem_idx
                    if first_table_elem_idx is None:
                        if elem_type not in NON_BODY_TYPES and not _is_corner_logo(elem_type, bbox, jpg_w, jpg_h):
                            if elem_type not in ("Picture", "Figure") or not _is_corner_logo(elem_type, bbox, jpg_w, jpg_h):
                                has_body_content_before_first_table = True

                    table_rows = elem.get("table_rows", 0)
                    table_cols = elem.get("table_cols", 0)
                    table_html = content if elem_type == "Table" and content_format == "html" else None
                    table_plain = None
                    if table_html:
                        table_plain = _extract_table_plain_text_from_html(content)

                    # ========== 跨页表格接续判断 (针对扫描版) ==========
                    force_no_header_for_this_table = False
                    elem_cross_page_group = None
                    need_retroactive_update = False
                    updated_prev_table_html = None
                    if elem_type == "Table" and prev_page_table_info is not None:
                        prev_at_page_bottom = prev_page_table_info.get("at_page_bottom", True)
                        is_at_page_top = (bbox[1] < jpg_h * 0.3)
                        if (table_cols > 0 and prev_page_table_info.get("col_count", 0) > 0
                                and is_at_page_top and prev_at_page_bottom
                                and not has_body_content_before_first_table):
                            if abs(table_cols - prev_page_table_info["col_count"]) <= 1:
                                logger.info(f"Page {page_info['page_number']}: 扫描版检测到跨页接续表格 "
                                            f"(cols={table_cols}, prev={prev_page_table_info['col_count']})，强制不识别表头")
                                force_no_header_for_this_table = True
                                if prev_page_table_info.get("cross_page_group") is not None:
                                    elem_cross_page_group = prev_page_table_info["cross_page_group"]
                                else:
                                    cross_page_group_counter += 1
                                    elem_cross_page_group = cross_page_group_counter
                                    need_retroactive_update = True
                                
                                # 处理跨页空单元格合并
                                prev_table_element_id = prev_page_table_info.get("element_id")
                                prev_table_html_content = prev_page_table_info.get("table_html", "")
                                if prev_table_element_id and prev_table_html_content and table_html:
                                    logger.info(f"Page {page_info['page_number']}: 开始处理跨页表格空单元格合并")
                                    merged_prev_html, merged_curr_html, first_row_cells = _merge_cross_page_empty_cells(
                                        prev_table_html_content, table_html
                                    )
                                    if merged_prev_html != prev_table_html_content:
                                        updated_prev_table_html = merged_prev_html
                                        logger.info(f"Page {page_info['page_number']}: 已更新前一页表格HTML")
                                    if merged_curr_html != table_html:
                                        table_html = merged_curr_html
                                        content = merged_curr_html
                                        logger.info(f"Page {page_info['page_number']}: 已更新当前页表格HTML（合并空单元格）")
                    
                    # 强制不识别表头：将第一行所有 <th> 替换为 <td>
                    if force_no_header_for_this_table and table_html:
                        first_tr_match = re.search(
                            r'(<tr[^>]*>)(.*?)(</tr>)',
                            table_html,
                            re.DOTALL | re.IGNORECASE
                        )
                        if first_tr_match:
                            tr_open = first_tr_match.group(1)
                            tr_content = first_tr_match.group(2)
                            tr_close = first_tr_match.group(3)
                            modified_content = re.sub(
                                r'<th\b', '<td', tr_content,
                                flags=re.IGNORECASE
                            )
                            modified_content = re.sub(
                                r'</th>', '</td>', modified_content,
                                flags=re.IGNORECASE
                            )
                            modified_html = (
                                table_html[:first_tr_match.start()]
                                + tr_open + modified_content + tr_close
                                + table_html[first_tr_match.end():]
                            )
                            table_html = modified_html
                            content = modified_html

                    # 追溯更新前一页表格的 HTML（如果有跨页合并）
                    if updated_prev_table_html and prev_page_table_info.get("element_id"):
                        await db.update_element(
                            prev_page_table_info["element_id"], content=updated_prev_table_html
                        )
                        logger.info(f"Page {page_info['page_number']}: 已保存前一页更新后的表格HTML")

                    eid = await db.create_element(page_id, elem_type, bbox, confidence, reading_order,
                                                  content=content, content_format=content_format,
                                                  cross_page_group=elem_cross_page_group)
                    saved_element_ids.append(eid)

                    # 追溯更新前一页表格的 cross_page_group
                    if need_retroactive_update and eid and prev_page_table_info and prev_page_table_info.get("element_id"):
                        await db.update_element_cross_page_group(
                            prev_page_table_info["element_id"], elem_cross_page_group
                        )
                        prev_page_table_info["cross_page_group"] = elem_cross_page_group

                    if eid and elem_type in element_count:
                        element_count[elem_type] += 1
                        if elem_type == "Table":
                            current_page_last_table_info = {
                                "element_id": eid,
                                "col_count": table_cols,
                                "last_row": _get_last_data_row_plain(table_plain),
                                "page_number": page_info["page_number"],
                                "cross_page_group": elem_cross_page_group,
                                "bbox_y1": bbox[3],
                                "at_page_bottom": bbox[3] > jpg_h * 0.7,
                                "table_html": table_html,
                            }
                            last_table_result_idx = len(saved_element_ids)

                except Exception as e:
                    logger.warning(f"Failed to save scanned element [{elem.get('element_type')}]: {e}", exc_info=True)
                    saved_element_ids.append(None)
                    continue

            await db.update_page(page_id, status="completed")
            pdf_doc.close()
            logger.info(f"Page {page_info['page_number']}: scanned parse done -> {len(all_elements)} elements: {element_count}")
            return (current_page_last_table_info, cross_page_group_counter)

        except Exception as e:
            logger.error(f"Scanned page direct parse FAILED for page {page_info['page_number']}: {e}. Falling back to normal flow.", exc_info=True)
            # fallback: 后面走正常流程

    # ==================== 正常流程（非扫描版 / 扫描版解析失败 fallback） ====================

    page_text = pdf_page.get_text("text")
    garble_result = detect_garbled_text(page_text)
    has_garbled = garble_result["is_garbled"]
    force_ocr = is_scanned or has_garbled

    if has_garbled:
        logger.info(f"Page {page_info['page_number']}: text is garbled (ratio: {garble_result['garble_ratio']:.2f}), forcing OCR")

    ocr_tasks = []
    ocr_indices = []
    formula_tasks = []
    formula_indices = []
    table_tasks = []
    table_indices = []

    for elem_idx, elem in enumerate(elements):
        elem_type = elem["element_type"]
        bbox = elem["bbox"]

        if elem_type in TEXT_TYPES and force_ocr:
            ocr_tasks.append(bbox)
            ocr_indices.append(elem_idx)
        elif elem_type == "Formula":
            formula_tasks.append(bbox)
            formula_indices.append(elem_idx)
        elif elem_type == "Table" and force_ocr:
            table_tasks.append(bbox)
            table_indices.append(elem_idx)

    ocr_results = {}
    formula_results = {}
    table_results = {}

    if ocr_tasks:
        logger.info(f"Page {page_info['page_number']}: batch OCR for {len(ocr_tasks)} text regions")
        texts = await asyncio.to_thread(ocr_batch, jpg_path, ocr_tasks)
        for idx, text in zip(ocr_indices, texts):
            ocr_results[idx] = text

    if formula_tasks:
        logger.info(f"Page {page_info['page_number']}: batch OCR for {len(formula_tasks)} formula regions")
        formulas = await asyncio.to_thread(ocr_batch, jpg_path, formula_tasks)
        for idx, text in zip(formula_indices, formulas):
            latex = " ".join([t for t in text.split("\n") if t.strip()])
            if latex and not latex.startswith("$"):
                latex = f"${latex}$"
            formula_results[idx] = latex

    if table_tasks:
        logger.info(f"Page {page_info['page_number']}: batch OCR for {len(table_tasks)} table regions")
        for idx, bbox in zip(table_indices, table_tasks):
            result = await asyncio.to_thread(extract_table_from_scanned, jpg_path, bbox)
            table_results[idx] = result

    parsed_results = []
    element_contents = {}
    has_body_content_before_table = False

    # 跨页表格判断辅助: 判断是否是角落的小logo(会被过滤掉不影响表格接续判断)
    _NON_BODY_FOR_TABLE_CONT = {"Page-header", "Page-footer", "Caption", "Footnote"}
    def _is_corner_logo_for_normal(elem_type, bbox, w, h):
        if elem_type not in ("Picture", "Figure"):
            return False
        x0, y0, x1, y1 = bbox
        bw, bh = x1 - x0, y1 - y0
        corner_region_w = w * 0.25
        corner_region_h = h * 0.20
        max_size = max(w, h) * 0.20
        if bw > max_size or bh > max_size:
            return False
        in_top = y1 < corner_region_h
        in_bottom = y0 > h - corner_region_h
        in_left = x1 < corner_region_w
        in_right = x0 > w - corner_region_w
        return (in_top or in_bottom) and (in_left or in_right)

    _jpg_w = page_info.get("jpg_width", 1)
    _jpg_h = page_info.get("jpg_height", 1)

    for elem_idx, elem in enumerate(elements):
        elem_type = elem["element_type"]
        bbox = elem["bbox"]
        confidence = elem["confidence"]
        reading_order = elem["reading_order"]
        content = ""
        content_format = "markdown"

        # 跨页表格接续判断: 过滤掉 header/footer/caption 和角落的logo，不视为"有效主体内容"
        if not has_body_content_before_table:
            is_body_for_table = True
            if elem_type in _NON_BODY_FOR_TABLE_CONT:
                is_body_for_table = False
            elif elem_type in ("Picture", "Figure") and _is_corner_logo_for_normal(elem_type, bbox, _jpg_w, _jpg_h):
                is_body_for_table = False
            if is_body_for_table:
                has_body_content_before_table = True

        try:
            if elem_type in TEXT_TYPES:
                if elem_idx in ocr_results:
                    content = ocr_results[elem_idx]
                else:
                    content = await asyncio.to_thread(extract_text_in_region, pdf_page, bbox)
                content_format = "markdown"

            elif elem_type == "Formula":
                if elem_idx in formula_results:
                    content = formula_results[elem_idx]
                else:
                    content = await asyncio.to_thread(ocr_formula, jpg_path, bbox)
                content_format = "latex"

            elif elem_type in ("Picture", "Figure"):
                result = await asyncio.to_thread(
                    extract_picture, pdf_page, bbox, output_dir, page_id * 1000 + reading_order
                )
                content = result.get("image_path", "")
                content_format = "image_path"

            elif elem_type == "Table":
                force_no_header = False
                elem_cross_page_group = None
                need_retroactive_update = False
                updated_prev_table_html = None
                if prev_page_table_info is not None:
                    prev_at_page_bottom = prev_page_table_info.get("at_page_bottom", True)
                    if force_ocr and elem_idx in table_results:
                        scanned_result = table_results[elem_idx]
                        scanned_cols = scanned_result.get("cols", 0)
                        is_at_page_top = (bbox[1] < page_info["jpg_height"] * 0.3)
                        scanned_html = scanned_result.get("html", "") or scanned_result.get("markdown", "")
                        first_tr_match = re.search(r'<tr[^>]*>(.*?)</tr>', scanned_html, re.DOTALL | re.IGNORECASE)
                        first_row_has_empty_cell = False
                        if first_tr_match:
                            first_row = first_tr_match.group(1)
                            empty_cells = re.findall(r'<t[dh]>\s*</t[dh]>', first_row, re.IGNORECASE)
                            first_row_has_empty_cell = len(empty_cells) > 0
                        if (scanned_cols > 0 and prev_page_table_info.get("col_count", 0) > 0 
                            and is_at_page_top and prev_at_page_bottom
                            and not has_body_content_before_table):
                            if abs(scanned_cols - prev_page_table_info["col_count"]) <= 1:
                                logger.info(f"Page {page_info['page_number']}: 扫描版检测到跨页接续表格(列数匹配 cols={scanned_cols})，强制不识别表头")
                                force_no_header = True
                                if prev_page_table_info.get("cross_page_group") is not None:
                                    elem_cross_page_group = prev_page_table_info["cross_page_group"]
                                    current_cross_page_group = elem_cross_page_group
                                else:
                                    cross_page_group_counter += 1
                                    elem_cross_page_group = cross_page_group_counter
                                    current_cross_page_group = cross_page_group_counter
                                    need_retroactive_update = True
                                
                                # 处理跨页空单元格合并
                                prev_table_element_id = prev_page_table_info.get("element_id")
                                prev_table_html_content = prev_page_table_info.get("table_html", "")
                                if prev_table_element_id and prev_table_html_content and scanned_html:
                                    logger.info(f"Page {page_info['page_number']}: 开始处理跨页表格空单元格合并")
                                    merged_prev_html, merged_curr_html, _ = _merge_cross_page_empty_cells(
                                        prev_table_html_content, scanned_html
                                    )
                                    if merged_prev_html != prev_table_html_content:
                                        updated_prev_table_html = merged_prev_html
                                    if merged_curr_html != scanned_html:
                                        table_results[elem_idx] = dict(scanned_result)
                                        table_results[elem_idx]["html"] = merged_curr_html
                    else:
                        try:
                            from backend.services.table_service import _find_valid_table

                            pdf_bbox = jpg_bbox_to_pdf_bbox(bbox, DEFAULT_DPI)
                            rect = fitz.Rect(pdf_bbox)
                            preview_table, preview_data, _ = _find_valid_table(pdf_page, rect)
                            
                            if preview_table and preview_data:
                                is_cont = _is_continuation_table(
                                    preview_table.col_count,
                                    preview_data[0],
                                    prev_page_table_info["col_count"],
                                    prev_page_table_info["last_row"]
                                )
                                if is_cont:
                                    logger.info(f"Page {page_info['page_number']}: 检测到跨页接续表格，强制不识别表头")
                                    force_no_header = True
                                    if prev_page_table_info.get("cross_page_group") is not None:
                                        elem_cross_page_group = prev_page_table_info["cross_page_group"]
                                        current_cross_page_group = elem_cross_page_group
                                    else:
                                        cross_page_group_counter += 1
                                        elem_cross_page_group = cross_page_group_counter
                                        current_cross_page_group = cross_page_group_counter
                                        need_retroactive_update = True
                        except Exception as e:
                            logger.debug(f"跨页表格检测失败: {e}")
                
                if elem_idx in table_results:
                    result = table_results[elem_idx]
                    if force_ocr and force_no_header and result.get("html"):
                        first_tr_match = re.search(
                            r'(<tr[^>]*>)(.*?)(</tr>)',
                            result["html"],
                            re.DOTALL | re.IGNORECASE
                        )
                        if first_tr_match:
                            tr_open = first_tr_match.group(1)
                            tr_content = first_tr_match.group(2)
                            tr_close = first_tr_match.group(3)
                            modified_content = re.sub(
                                r'<th\b', '<td', tr_content,
                                flags=re.IGNORECASE
                            )
                            modified_content = re.sub(
                                r'</th>', '</td>', modified_content,
                                flags=re.IGNORECASE
                            )
                            modified_html = (
                                result["html"][:first_tr_match.start()]
                                + tr_open + modified_content + tr_close
                                + result["html"][first_tr_match.end():]
                            )
                            result = dict(result)
                            result["html"] = modified_html
                else:
                    result = await asyncio.to_thread(
                        extract_table_from_native, pdf_page, bbox, 
                        True, DEFAULT_DPI, force_no_header
                    )
                content = result.get("html", "") or result.get("markdown", "")
                content_format = "html" if result.get("html") else "markdown"
                
                # 处理非扫描版（force_ocr=False）的跨页空单元格合并
                if (not force_ocr and force_no_header and 
                    prev_page_table_info and prev_page_table_info.get("element_id") and 
                    prev_page_table_info.get("table_html") and content):
                    logger.info(f"Page {page_info['page_number']}: 处理非扫描版跨页表格空单元格合并")
                    merged_prev_html, merged_curr_html, _ = _merge_cross_page_empty_cells(
                        prev_page_table_info["table_html"], content
                    )
                    if merged_prev_html != prev_page_table_info["table_html"]:
                        updated_prev_table_html = merged_prev_html
                    if merged_curr_html != content:
                        content = merged_curr_html
                        result["html"] = merged_curr_html
                
                # 追溯更新前一页表格的 HTML
                if updated_prev_table_html and prev_page_table_info.get("element_id"):
                    await db.update_element(
                        prev_page_table_info["element_id"], content=updated_prev_table_html
                    )
                    logger.info(f"Page {page_info['page_number']}: 已保存前一页更新后的表格HTML")
                
                if force_ocr and elem_idx in table_results:
                    scanned_res = table_results[elem_idx]
                    scanned_cols = scanned_res.get("cols", 0)
                    if scanned_cols > 0:
                        if (current_page_last_table_info is None or 
                            bbox[3] > current_page_last_table_info.get("bbox_y1", 0)):
                            html_content = scanned_res.get("html", "") or scanned_res.get("markdown", "")
                            lines = [l.strip() for l in html_content.split("\n") if l.strip()]
                            last_row = lines[-1] if lines else ""
                            at_page_bottom = (bbox[3] > page_info["jpg_height"] * 0.7)
                            current_page_last_table_info = {
                                "col_count": scanned_cols,
                                "last_row": last_row,
                                "page_number": page_info["page_number"],
                                "cross_page_group": current_cross_page_group,
                                "bbox_y1": bbox[3],
                                "at_page_bottom": at_page_bottom,
                                "table_html": html_content,
                            }
                            last_table_result_idx = len(parsed_results)
                else:
                    try:
                        from backend.services.table_service import _find_valid_table
                        
                        pdf_bbox = jpg_bbox_to_pdf_bbox(bbox, DEFAULT_DPI)
                        rect = fitz.Rect(pdf_bbox)
                        info_table, info_data, _ = _find_valid_table(pdf_page, rect)
                        
                        if info_table and info_data:
                            if (current_page_last_table_info is None or 
                                bbox[3] > current_page_last_table_info.get("bbox_y1", 0)):
                                current_page_last_table_info = {
                                    "col_count": info_table.col_count,
                                    "last_row": info_data[-1],
                                    "page_number": page_info["page_number"],
                                    "cross_page_group": current_cross_page_group,
                                    "bbox_y1": bbox[3],
                                    "at_page_bottom": True,
                                    "table_html": content,
                                }
                                last_table_result_idx = len(parsed_results)
                    except Exception as e:
                        logger.debug(f"记录表格信息失败: {e}")

            parsed_results.append({
                "elem_type": elem_type,
                "bbox": bbox,
                "confidence": confidence,
                "reading_order": reading_order,
                "content": content,
                "content_format": content_format,
                "cross_page_group": elem_cross_page_group if elem_type == "Table" else None,
                "need_retroactive_update": need_retroactive_update if elem_type == "Table" else False,
            })
            element_contents[elem_idx] = content

        except Exception as e:
            logger.error(f"Failed to parse element {elem_type} at {bbox}: {e}")
            parsed_results.append({
                "elem_type": elem_type,
                "bbox": bbox,
                "confidence": confidence,
                "reading_order": reading_order,
                "content": f"[ERROR: {str(e)}]",
                "content_format": "error",
            })
            element_contents[elem_idx] = ""

    elements = deduplicate_header_footer(elements, element_contents)
    
    kept_bboxes = {(elem["bbox"], elem["element_type"]) for elem in elements}
    
    for idx, result in enumerate(parsed_results):
        result_key = (result["bbox"], result["elem_type"])
        if result_key in kept_bboxes:
            element_id = await db.create_element(
                page_id, result["elem_type"], result["bbox"], 
                result["confidence"], result["reading_order"],
                content=result["content"], content_format=result["content_format"],
                cross_page_group=result.get("cross_page_group"),
            )
            if idx == last_table_result_idx:
                current_page_last_table_info["element_id"] = element_id
            if (result.get("need_retroactive_update") and 
                prev_page_table_info and prev_page_table_info.get("element_id")):
                await db.update_element_cross_page_group(
                    prev_page_table_info["element_id"], result["cross_page_group"]
                )
                prev_page_table_info["cross_page_group"] = result["cross_page_group"]

    pdf_doc.close()
    await db.update_page(page_id, status="completed")
    logger.info(f"Page {page_info['page_number']}: parsing completed")
    
    return current_page_last_table_info, cross_page_group_counter


async def get_parse_results(doc_id: int) -> dict:
    doc = await db.get_document(doc_id)
    if not doc:
        return {"error": "Document not found"}

    pages = await db.get_pages(doc_id)
    result_pages = []

    for page in pages:
        elements = await db.get_elements(page["id"])
        page_data = {
            "page_number": page["page_number"],
            "width": page["width"],
            "height": page["height"],
            "jpg_width": page["jpg_width"],
            "jpg_height": page["jpg_height"],
            "is_scanned": bool(page["is_scanned"]),
            "status": page["status"],
            "elements": [],
        }

        for elem in elements:
            page_data["elements"].append({
                "id": elem["id"],
                "element_type": elem["element_type"],
                "bbox_x0": elem["bbox_x0"],
                "bbox_y0": elem["bbox_y0"],
                "bbox_x1": elem["bbox_x1"],
                "bbox_y1": elem["bbox_y1"],
                "confidence": elem["confidence"],
                "reading_order": elem["reading_order"],
                "content": elem["content"],
                "content_format": elem["content_format"],
                "cross_page_group": elem.get("cross_page_group"),
            })

        result_pages.append(page_data)

    markdown = _build_markdown(result_pages)

    return {
        "document": {
            "id": doc["id"],
            "original_filename": doc["original_filename"],
            "page_count": doc["page_count"],
            "status": doc["status"],
        },
        "pages": result_pages,
        "markdown": markdown,
    }


def _build_markdown(pages: list[dict]) -> str:
    parts = []

    for page in pages:
        parts.append(f"\n---\n**Page {page['page_number']}**\n")

        elements = sorted(page["elements"], key=lambda e: e["reading_order"])

        for elem in elements:
            etype = elem["element_type"]
            content = elem.get("content", "") or ""
            content_format = elem.get("content_format", "") or ""

            if etype == "Title":
                parts.append(f"# {content}\n")
            elif etype == "Section-header":
                parts.append(f"## {content}\n")
            elif etype in TEXT_TYPES:
                if content.strip():
                    parts.append(f"{content}\n")
            elif etype == "Formula":
                parts.append(f"\n{content}\n")
            elif etype == "Table":
                if content_format == "html":
                    parts.append(f"\n{content}\n")
                else:
                    parts.append(f"\n{content}\n")
            elif etype == "Picture":
                if content:
                    parts.append(f"\n![Picture]({content})\n")
            elif etype == "Caption":
                parts.append(f"*{content}*\n")

    return "\n".join(parts)
