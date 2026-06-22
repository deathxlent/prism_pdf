import logging
import asyncio
import re
import fitz
from pathlib import Path

from backend import database as db
from backend.services.pdf_service import (
    extract_text_in_region, detect_garbled_text, jpg_bbox_to_pdf_bbox, DEFAULT_DPI
)
from backend.services.layout_service import deduplicate_header_footer, detect_layout
from backend.services.order_service import assign_reading_order
from backend.services.ocr_service_vl import ocr_region, ocr_formula, ocr_batch, ocr_batch_multi_image
from backend.services.table_service import extract_table_from_native, extract_table_from_scanned
from backend.services.picture_service import extract_picture
from backend.services.scanned_parse_service import parse_scanned_page_full
from backend.services.cross_page_table_service import (
    extract_table_plain_text_from_html,
    get_first_data_row_plain,
    get_last_data_row_plain,
    is_continuation_table,
    merge_cross_page_empty_cells,
    save_ocr_raw_output,
)

logger = logging.getLogger(__name__)

TEXT_TYPES = {"Caption", "Footnote", "List-item", "Page-footer", "Page-header",
              "Section-header", "Text", "Title"}


def _force_remove_table_header(html: str) -> str:
    """强制将表格第一行的 <th> 替换为 <td>（跨页接续表格使用）"""
    first_tr_match = re.search(
        r'(<tr[^>]*>)(.*?)(</tr>)',
        html,
        re.DOTALL | re.IGNORECASE
    )
    if not first_tr_match:
        return html
    tr_open = first_tr_match.group(1)
    tr_content = first_tr_match.group(2)
    tr_close = first_tr_match.group(3)
    modified_content = re.sub(r'<th\b', '<td', tr_content, flags=re.IGNORECASE)
    modified_content = re.sub(r'</th>', '</td>', modified_content, flags=re.IGNORECASE)
    return (
        html[:first_tr_match.start()]
        + tr_open + modified_content + tr_close
        + html[first_tr_match.end():]
    )


async def parse_scanned_page(
    page_id: int,
    page_info: dict,
    jpg_path: str,
    jpg_w: int,
    jpg_h: int,
    pdf_page,
    output_dir: str,
    elements: list,
    is_ordered: bool,
    prev_page_table_info: dict | None,
    cross_page_group_counter: int,
) -> tuple[dict | None, int]:
    """
    扫描版 PDF 直接解析分支。
    返回: (current_page_last_table_info, cross_page_group_counter)
    """
    from PIL import Image
    with Image.open(jpg_path) as im:
        actual_w, actual_h = im.size
    jpg_w, jpg_h = actual_w, actual_h

    save_ocr_raw_output(jpg_path, page_info["page_number"], str(Path(output_dir).parent))

    all_elements = elements
    if not all_elements:
        logger.info(f"Page {page_info['page_number']}: No pre-processed elements, doing full page parse now...")

        picture_elements = []
        try:
            raw_layout = await asyncio.to_thread(detect_layout, jpg_path)
            for le in raw_layout:
                if le["element_type"] in ("Picture", "Figure"):
                    elem_bbox = le["bbox"]
                    elem_area = (elem_bbox[2] - elem_bbox[0]) * (elem_bbox[3] - elem_bbox[1])
                    page_area = jpg_w * jpg_h
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

        scanned_elements = await asyncio.to_thread(
            parse_scanned_page_full, jpg_path, jpg_w, jpg_h
        )

        all_elements, surya_ok = await asyncio.to_thread(
            assign_reading_order, picture_elements + scanned_elements, jpg_path
        )
        is_ordered = surya_ok
    else:
        logger.info(f"Page {page_info['page_number']}: Using pre-processed elements ({len(all_elements)} elements)")

    element_count = {
        "Text": 0, "Section-header": 0, "Title": 0, "Table": 0,
        "Figure": 0, "Picture": 0, "Formula": 0, "List-item": 0,
        "Page-header": 0, "Page-footer": 0, "Caption": 0,
    }

    NON_BODY_TYPES = {"Page-header", "Page-footer", "Caption"}

    def _is_corner_logo(elem_type, bbox, w, h):
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

    has_body_content_before_first_table = False
    first_table_elem_idx = None
    saved_element_ids = []

    current_page_last_table_info = None
    last_table_result_idx = None

    for elem_idx, elem in enumerate(all_elements):
        try:
            elem_type = elem.get("element_type", "Text")
            bbox = elem.get("bbox", (0, 0, 0, 0))
            confidence = elem.get("confidence", 0.8)
            reading_order = elem.get("reading_order", 0)
            content = elem.get("content", "") or ""
            content_format = elem.get("content_format", "markdown")
            is_layout_picture = elem.get("_is_layout_picture", False)

            if is_layout_picture and elem_type in ("Picture", "Figure"):
                try:
                    result = await asyncio.to_thread(
                        extract_picture, pdf_page, bbox, output_dir, page_id * 10000 + reading_order
                    )
                    content = result.get("image_path", "")
                    content_format = "image_path"
                except Exception as pic_e:
                    logger.warning(f"Failed to extract picture at {bbox}: {pic_e}")

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
                table_plain = extract_table_plain_text_from_html(content)

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

                        prev_table_element_id = prev_page_table_info.get("element_id")
                        prev_table_html_content = prev_page_table_info.get("table_html", "")
                        if prev_table_element_id and prev_table_html_content and table_html:
                            logger.info(f"Page {page_info['page_number']}: 开始处理跨页表格空单元格合并")
                            merged_prev_html, merged_curr_html, first_row_cells = merge_cross_page_empty_cells(
                                prev_table_html_content, table_html
                            )
                            if merged_prev_html != prev_table_html_content:
                                updated_prev_table_html = merged_prev_html
                                logger.info(f"Page {page_info['page_number']}: 已更新前一页表格HTML")
                            if merged_curr_html != table_html:
                                table_html = merged_curr_html
                                content = merged_curr_html
                                logger.info(f"Page {page_info['page_number']}: 已更新当前页表格HTML（合并空单元格）")

            if force_no_header_for_this_table and table_html:
                table_html = _force_remove_table_header(table_html)
                content = table_html

            if updated_prev_table_html and prev_page_table_info.get("element_id"):
                await db.update_element(
                    prev_page_table_info["element_id"], content=updated_prev_table_html
                )
                logger.info(f"Page {page_info['page_number']}: 已保存前一页更新后的表格HTML")

            eid = await db.create_element(
                page_id, elem_type, bbox, confidence, reading_order,
                content=content, content_format=content_format,
                cross_page_group=elem_cross_page_group
            )
            saved_element_ids.append(eid)

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
                        "last_row": get_last_data_row_plain(table_plain),
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

    await db.update_page(page_id, status="completed", is_ordered=1 if is_ordered else 0)
    logger.info(f"Page {page_info['page_number']}: scanned parse done -> {len(all_elements)} elements: {element_count}, ordered={'yes' if is_ordered else 'no'}")
    return (current_page_last_table_info, cross_page_group_counter)


async def parse_page(
    doc_id: int,
    page_info: dict,
    doc_dir: str,
    prev_page_table_info: dict = None,
    cross_page_group_counter: int = 0,
) -> tuple[dict | None, int]:
    page_id = page_info["id"]
    jpg_path = page_info["jpg_path"]
    single_pdf_path = page_info["single_pdf_path"]
    is_scanned = page_info["is_scanned"]
    is_ordered = page_info.get("_is_ordered", True)
    elements = page_info.get("_elements", [])

    current_page_last_table_info = None
    current_cross_page_group = None
    last_table_result_idx = None

    await db.update_page(page_id, status="parsing_content")

    pdf_doc = fitz.open(single_pdf_path)
    pdf_page = pdf_doc[0]

    output_dir = str(Path(doc_dir) / "output")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    if is_scanned:
        logger.info(f"Page {page_info['page_number']}: SCANNED PAGE -> processing scanned page")
        try:
            result = await parse_scanned_page(
                page_id, page_info, jpg_path,
                page_info.get("jpg_width", 0), page_info.get("jpg_height", 0),
                pdf_page, output_dir, elements, is_ordered,
                prev_page_table_info, cross_page_group_counter
            )
            pdf_doc.close()
            return result
        except Exception as e:
            logger.error(f"Scanned page direct parse FAILED for page {page_info['page_number']}: {e}. Falling back to normal flow.", exc_info=True)

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

                                prev_table_element_id = prev_page_table_info.get("element_id")
                                prev_table_html_content = prev_page_table_info.get("table_html", "")
                                if prev_table_element_id and prev_table_html_content and scanned_html:
                                    logger.info(f"Page {page_info['page_number']}: 开始处理跨页表格空单元格合并")
                                    merged_prev_html, merged_curr_html, _ = merge_cross_page_empty_cells(
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
                                is_cont = is_continuation_table(
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
                        modified_html = _force_remove_table_header(result["html"])
                        result = dict(result)
                        result["html"] = modified_html
                else:
                    result = await asyncio.to_thread(
                        extract_table_from_native, pdf_page, bbox,
                        True, DEFAULT_DPI, force_no_header
                    )
                content = result.get("html", "") or result.get("markdown", "")
                content_format = "html" if result.get("html") else "markdown"

                if (not force_ocr and force_no_header and
                    prev_page_table_info and prev_page_table_info.get("element_id") and
                    prev_page_table_info.get("table_html") and content):
                    logger.info(f"Page {page_info['page_number']}: 处理非扫描版跨页表格空单元格合并")
                    merged_prev_html, merged_curr_html, _ = merge_cross_page_empty_cells(
                        prev_page_table_info["table_html"], content
                    )
                    if merged_prev_html != prev_page_table_info["table_html"]:
                        updated_prev_table_html = merged_prev_html
                    if merged_curr_html != content:
                        content = merged_curr_html
                        result["html"] = merged_curr_html

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
            if idx == last_table_result_idx and current_page_last_table_info:
                current_page_last_table_info["element_id"] = element_id
            if (result.get("need_retroactive_update") and
                prev_page_table_info and prev_page_table_info.get("element_id")):
                await db.update_element_cross_page_group(
                    prev_page_table_info["element_id"], result["cross_page_group"]
                )
                prev_page_table_info["cross_page_group"] = result["cross_page_group"]

    pdf_doc.close()
    await db.update_page(page_id, status="completed", is_ordered=1 if is_ordered else 0)
    logger.info(f"Page {page_info['page_number']}: parsing completed, ordered={'yes' if is_ordered else 'no'}")

    return current_page_last_table_info, cross_page_group_counter


HEADER_TYPES = {"page-header", "header"}
FOOTER_TYPES = {"page-footer", "footer", "footnote"}


async def mark_header_footer(page_id: int):
    elements = await db.get_elements(page_id)
    if not elements:
        return

    header_y_threshold = None
    footer_y_threshold = None

    for elem in elements:
        etype_lower = (elem.get("element_type") or "").lower()
        y0 = elem.get("bbox_y0", 0)
        y1 = elem.get("bbox_y1", 0)

        if etype_lower in HEADER_TYPES:
            if header_y_threshold is None or y1 > header_y_threshold:
                header_y_threshold = y1

        if etype_lower in FOOTER_TYPES:
            if footer_y_threshold is None or y0 < footer_y_threshold:
                footer_y_threshold = y0

    page_updates = {}
    if header_y_threshold is not None:
        page_updates["header_y_threshold"] = header_y_threshold
    if footer_y_threshold is not None:
        page_updates["footer_y_threshold"] = footer_y_threshold
    if page_updates:
        await db.update_page(page_id, **page_updates)

    if header_y_threshold is None and footer_y_threshold is None:
        return

    marked_count = 0
    for elem in elements:
        etype_lower = (elem.get("element_type") or "").lower()
        if etype_lower in HEADER_TYPES or etype_lower in FOOTER_TYPES:
            continue

        y0 = elem.get("bbox_y0", 0)
        y1 = elem.get("bbox_y1", 0)
        mark = None

        if header_y_threshold is not None and y0 < header_y_threshold:
            mark = "header"
        elif footer_y_threshold is not None and y1 > footer_y_threshold:
            mark = "footer"

        if mark:
            await db.update_element(elem["id"], header_footer_mark=mark)
            marked_count += 1

    if marked_count > 0:
        logger.info(f"Page {page_id}: marked {marked_count} elements as header/footer zone")
