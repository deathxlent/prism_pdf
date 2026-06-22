import logging
import asyncio
from pathlib import Path

from backend import database as db
from backend.services.pdf_service import validate_pdf, prepare_pages
from backend.services.layout_service import detect_layout_batch, deduplicate_header_footer
from backend.services.order_service import assign_reading_order_batch, check_gpu_available_for_surya
from backend.services.progress_service import (
    set_parse_progress,
    get_parse_progress,
    clear_parse_progress,
)
from backend.services.page_parser_service import parse_page, TEXT_TYPES
from backend.services.export_service import build_markdown

logger = logging.getLogger(__name__)


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
        scanned_indices = []
        for page_idx, page in enumerate(pages):
            jpg_path = page["jpg_path"]
            all_jpg_paths.append(jpg_path)
            if page.get("is_scanned"):
                scanned_indices.append(page_idx)
            else:
                non_scanned_indices.append(page_idx)

        non_scanned_jpg_paths = [all_jpg_paths[i] for i in non_scanned_indices]
        scanned_jpg_paths = [all_jpg_paths[i] for i in scanned_indices]
        logger.info(f"Total pages: {len(pages)}, non-scanned: {len(non_scanned_indices)}, scanned: {len(scanned_indices)}")

        layouts_with_order = [[] for _ in range(len(pages))]
        page_is_ordered = [True] * len(pages)
        scanned_picture_elements = [[] for _ in range(len(pages))]
        scanned_ocr_elements = [[] for _ in range(len(pages))]

        surya_gpu_ok = await asyncio.to_thread(check_gpu_available_for_surya)

        if non_scanned_jpg_paths:
            set_parse_progress(doc_id, "parsing_layout", 30, f"批量检测布局（{len(non_scanned_indices)} 个非扫描页）...")
            logger.info("Batch detecting layouts for non-scanned pages...")
            non_scanned_layouts = await asyncio.to_thread(detect_layout_batch, non_scanned_jpg_paths)

            set_parse_progress(doc_id, "parsing_layout", 40, f"分配阅读顺序（{len(non_scanned_indices)} 个非扫描页）...")
            logger.info("Batch assigning reading orders for non-scanned pages...")
            non_scanned_with_order, non_scanned_surya_ordered = await asyncio.to_thread(
                assign_reading_order_batch, non_scanned_layouts, non_scanned_jpg_paths
            )

            for i, ns_idx in enumerate(non_scanned_indices):
                layouts_with_order[ns_idx] = non_scanned_with_order[i]
                page_is_ordered[ns_idx] = non_scanned_surya_ordered[i]
                if not non_scanned_surya_ordered[i]:
                    logger.info(f"Page {pages[ns_idx]['page_number']}: Surya not available, marked as unordered")

        if scanned_jpg_paths:
            set_parse_progress(doc_id, "parsing_layout", 30, f"扫描页批量YOLO布局检测（{len(scanned_indices)} 页）...")
            logger.info(f"Batch YOLO layout detection for {len(scanned_indices)} scanned pages...")
            scanned_layouts = await asyncio.to_thread(detect_layout_batch, scanned_jpg_paths)

            for i, s_idx in enumerate(scanned_indices):
                jpg_path = scanned_jpg_paths[i]
                jpg_w = pages[s_idx]["jpg_width"]
                jpg_h = pages[s_idx]["jpg_height"]
                page_area = jpg_w * jpg_h
                picture_elems = []
                for le in scanned_layouts[i]:
                    if le["element_type"] in ("Picture", "Figure"):
                        elem_bbox = le["bbox"]
                        elem_area = (elem_bbox[2] - elem_bbox[0]) * (elem_bbox[3] - elem_bbox[1])
                        if elem_area < page_area * 0.5:
                            picture_elems.append({
                                "element_type": le["element_type"],
                                "bbox": elem_bbox,
                                "confidence": le["confidence"],
                                "reading_order": 0,
                                "content": "",
                                "content_format": "image_path",
                                "_is_layout_picture": True,
                            })
                scanned_picture_elements[s_idx] = picture_elems
                logger.info(f"Page {pages[s_idx]['page_number']}: YOLO found {len(picture_elems)} Picture/Figure elements")

            set_parse_progress(doc_id, "parsing_layout", 45, f"扫描页批量OCR整页解析（{len(scanned_indices)} 页）...")
            logger.info(f"Batch full-page OCR for {len(scanned_indices)} scanned pages...")
            from backend.services.scanned_parse_service import parse_scanned_pages_batch
            scanned_page_info = []
            for s_idx in scanned_indices:
                scanned_page_info.append({
                    "jpg_path": pages[s_idx]["jpg_path"],
                    "page_width": pages[s_idx]["jpg_width"],
                    "page_height": pages[s_idx]["jpg_height"],
                })
            scanned_ocr_results = await asyncio.to_thread(
                parse_scanned_pages_batch, scanned_page_info
            )

            for i, s_idx in enumerate(scanned_indices):
                scanned_ocr_elements[s_idx] = scanned_ocr_results[i]
                logger.info(f"Page {pages[s_idx]['page_number']}: OCR found {len(scanned_ocr_results[i])} elements")

            set_parse_progress(doc_id, "parsing_layout", 50, f"扫描页批量分配阅读顺序（{len(scanned_indices)} 页）...")
            logger.info(f"Batch assigning reading orders for {len(scanned_indices)} scanned pages...")
            scanned_all_elements = []
            for s_idx in scanned_indices:
                all_elems = scanned_picture_elements[s_idx] + scanned_ocr_elements[s_idx]
                scanned_all_elements.append(all_elems)

            scanned_with_order, scanned_surya_ordered = await asyncio.to_thread(
                assign_reading_order_batch, scanned_all_elements, scanned_jpg_paths
            )

            for i, s_idx in enumerate(scanned_indices):
                pages[s_idx]["_scanned_picture_elements"] = scanned_picture_elements[s_idx]
                pages[s_idx]["_scanned_ocr_elements"] = scanned_ocr_elements[s_idx]
                pages[s_idx]["_scanned_all_elements"] = scanned_with_order[i]
                page_is_ordered[s_idx] = scanned_surya_ordered[i]
                if not scanned_surya_ordered[i]:
                    logger.info(f"Page {pages[s_idx]['page_number']}: Surya not available, marked as unordered")

        for page_idx, page in enumerate(pages):
            try:
                page["_is_ordered"] = page_is_ordered[page_idx]
                if not page.get("is_scanned"):
                    page["_elements"] = layouts_with_order[page_idx]
                else:
                    page["_elements"] = page.get("_scanned_all_elements", [])
            except Exception as e:
                logger.error(f"Failed to prepare elements for page {page['page_number']}: {e}")
                page["_elements"] = []
                page["_is_ordered"] = False

        prev_page_table_info = None
        cross_page_group_counter = 0

        for i, page in enumerate(pages):
            try:
                set_parse_progress(doc_id, "parsing_content", 55 + (i / total_pages) * 40,
                                  f"解析页面 {page['page_number']}/{total_pages}")
                current_page_table_info, cross_page_group_counter = await parse_page(
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


async def get_parse_results(doc_id: int) -> dict:
    doc = await db.get_document(doc_id)
    if not doc:
        return {"error": "Document not found"}

    pages = await db.get_pages(doc_id)
    result_pages = []

    for page in pages:
        elements = await db.get_elements(page["id"])
        page_data = {
            "id": page["id"],
            "page_number": page["page_number"],
            "width": page["width"],
            "height": page["height"],
            "jpg_width": page["jpg_width"],
            "jpg_height": page["jpg_height"],
            "is_scanned": bool(page["is_scanned"]),
            "is_ordered": bool(page.get("is_ordered", 1)),
            "status": page["status"],
            "jpg_path": page["jpg_path"],
            "single_pdf_path": page["single_pdf_path"],
            "thumbnail_path": page["thumbnail_path"],
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

    markdown = build_markdown(result_pages)

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
