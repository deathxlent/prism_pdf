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

logger = logging.getLogger(__name__)

_parse_progress: dict[int, dict] = {}

TEXT_TYPES = {"Caption", "Footnote", "List-item", "Page-footer", "Page-header",
              "Section-header", "Text", "Title"}


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
        for page in pages:
            jpg_path = page["jpg_path"]
            all_jpg_paths.append(jpg_path)

        set_parse_progress(doc_id, "parsing_layout", 35, "批量检测布局...")
        logger.info("Batch detecting layouts for all pages...")
        layouts = await asyncio.to_thread(detect_layout_batch, all_jpg_paths)

        set_parse_progress(doc_id, "parsing_layout", 50, "分配阅读顺序...")
        logger.info("Batch assigning reading orders for all pages...")
        layouts_with_order = await asyncio.to_thread(
            assign_reading_order_batch, layouts, all_jpg_paths
        )

        for page_idx, page in enumerate(pages):
            try:
                page["_elements"] = layouts_with_order[page_idx]
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
    
    判断规则:
        1. 列数必须相同
        2. 第一列的内容风格相似（都是数据行，不是表头）
        3. 前一页最后一行和当前页第一行的非空单元格数量相似
    
    注意: 这是一个启发式判断，可能有误判，但可以处理大多数标准表格的跨页接续。
    """
    # 列数必须相同
    if curr_table_cols != prev_table_cols:
        return False
    
    # 检查第一列是否为空或包含数据（不是表头）
    # 如果第一列为空（常见于rowspan接续）或包含数字/普通文本，可能是接续
    curr_first_col = str(curr_first_row[0]).strip() if curr_first_row and curr_first_row[0] else ""
    prev_last_col = str(prev_last_row[0]).strip() if prev_last_row and prev_last_row[0] else ""
    
    # 如果前一页最后一行第一列是跨行的（空），且当前页第一行第一列也是空的，很可能是接续
    if not curr_first_col and not prev_last_col:
        return True
    
    # 如果前一页最后一行有数据，当前页第一行也有数据，且列数相同，可能是接续
    # 检查是否有数字（数据行特征）
    def has_digit(s: str) -> bool:
        return any(c.isdigit() for c in s)
    
    prev_has_digit = any(has_digit(str(c)) for c in prev_last_row if c)
    curr_has_digit = any(has_digit(str(c)) for c in curr_first_row if c)
    
    if prev_has_digit and curr_has_digit:
        return True
    
    return False


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

    for elem_idx, elem in enumerate(elements):
        elem_type = elem["element_type"]
        bbox = elem["bbox"]
        confidence = elem["confidence"]
        reading_order = elem["reading_order"]
        content = ""
        content_format = "markdown"

        if elem_type in ("Text", "Section-header", "List-item"):
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

            elif elem_type == "Picture":
                result = await asyncio.to_thread(
                    extract_picture, pdf_page, bbox, output_dir, page_id * 1000 + reading_order
                )
                content = result.get("image_path", "")
                content_format = "image_path"

            elif elem_type == "Table":
                force_no_header = False
                elem_cross_page_group = None
                need_retroactive_update = False
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
                else:
                    result = await asyncio.to_thread(
                        extract_table_from_native, pdf_page, bbox, 
                        True, DEFAULT_DPI, force_no_header
                    )
                content = result.get("html", "") or result.get("markdown", "")
                content_format = "html" if result.get("html") else "markdown"
                
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
