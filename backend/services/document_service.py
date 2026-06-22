import os
import logging
import shutil
from pathlib import Path

from backend import database as db

logger = logging.getLogger(__name__)


async def delete_document(doc_id: int) -> None:
    doc = await db.get_document(doc_id)
    if not doc:
        raise ValueError("Document not found")

    try:
        doc_dir = Path(doc["file_path"]).parent / Path(doc["file_path"]).stem
        if doc_dir.exists():
            shutil.rmtree(str(doc_dir), ignore_errors=True)
        if Path(doc["file_path"]).exists():
            os.unlink(doc["file_path"])
    except OSError as e:
        logger.warning(f"Failed to delete files for doc {doc_id}: {e}")

    await db.delete_document(doc_id)


async def reparse_document(doc_id: int) -> None:
    doc = await db.get_document(doc_id)
    if not doc:
        raise ValueError("Document not found")

    if doc["status"] == "processing":
        raise RuntimeError("Document is already processing")

    await db.execute_query(
        "DELETE FROM page_elements WHERE page_id IN (SELECT id FROM pdf_pages WHERE document_id = ?)",
        (doc_id,)
    )
    await db.execute_query("DELETE FROM pdf_pages WHERE document_id = ?", (doc_id,))
    await db.update_document(doc_id, status="uploaded", error_message=None)


async def translate_page(page_id: int, target_language: str = "en") -> dict:
    from backend.services.llm_service import translate_page_content

    page = await db.get_page(page_id)
    if not page:
        raise ValueError("Page not found")

    elements = await db.get_elements(page_id)
    if not elements:
        raise ValueError("当前页面无解析元素")

    results = translate_page_content(elements, target_language)
    for item in results:
        await db.update_element(item["element_id"], translated_content=item["translated_content"])

    return {"page_id": page_id, "translated_count": len(results), "results": results}


async def translate_document(doc_id: int, target_language: str = "en") -> dict:
    from backend.services.llm_service import translate_page_content

    document = await db.get_document(doc_id)
    if not document:
        raise ValueError("Document not found")

    pages = await db.get_pages(doc_id)
    total_translated = 0
    page_results = []

    for page in pages:
        elements = await db.get_elements(page["id"])
        if not elements:
            continue

        try:
            results = translate_page_content(elements, target_language)
            for item in results:
                await db.update_element(item["element_id"], translated_content=item["translated_content"])
            total_translated += len(results)
            page_results.append({
                "page_id": page["id"],
                "page_number": page["page_number"],
                "translated_count": len(results)
            })
        except Exception as e:
            logger.error(f"Failed to translate page {page['page_number']}: {e}")
            page_results.append({
                "page_id": page["id"],
                "page_number": page["page_number"],
                "error": str(e)
            })

    return {
        "document_id": doc_id,
        "total_translated": total_translated,
        "pages": page_results
    }


async def get_model_status() -> dict:
    from backend.services.layout_service import (
        is_yolo_model_loaded, is_yolo_loaded_on_gpu, check_gpu_available_for_yolo,
        get_yolo_model_memory as _get_yolo_mem,
    )
    from backend.services.order_service import (
        is_surya_model_loaded, is_surya_loaded_on_gpu, check_gpu_available_for_surya,
        get_surya_model_memory as _get_surya_mem,
    )

    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            free_vram = torch.cuda.mem_get_info()[0] / (1024 * 1024)
            total_vram = torch.cuda.mem_get_info()[1] / (1024 * 1024)
            used_vram = total_vram - free_vram
            vram_percent = (used_vram / total_vram * 100) if total_vram > 0 else 0

            device_count = torch.cuda.device_count()
            devices = []
            for i in range(device_count):
                d_free = torch.cuda.mem_get_info(i)[0] / (1024 * 1024)
                d_total = torch.cuda.mem_get_info(i)[1] / (1024 * 1024)
                d_used = d_total - d_free
                devices.append({
                    "index": i,
                    "name": torch.cuda.get_device_name(i),
                    "free_vram_mb": round(d_free, 2),
                    "total_vram_mb": round(d_total, 2),
                    "used_vram_mb": round(d_used, 2),
                })

            gpu_info = {
                "cuda_available": True,
                "device_name": torch.cuda.get_device_name(0),
                "free_vram_mb": round(free_vram, 2),
                "total_vram_mb": round(total_vram, 2),
                "used_vram_mb": round(used_vram, 2),
                "vram_percent": round(vram_percent, 2),
                "device_count": device_count,
                "devices": devices,
            }
        else:
            gpu_info = {"cuda_available": False}
    except Exception as e:
        gpu_info = {"cuda_available": False, "error": str(e)}

    yolo_mem = None
    surya_mem = None
    try:
        yolo_mem = _get_yolo_mem()
    except Exception:
        pass
    try:
        surya_mem = _get_surya_mem()
    except Exception:
        pass

    return {
        "yolo": {
            "loaded": is_yolo_model_loaded(),
            "loaded_on_gpu": is_yolo_loaded_on_gpu(),
            "gpu_available": check_gpu_available_for_yolo(),
            "memory_mb": yolo_mem,
        },
        "surya_order": {
            "loaded": is_surya_model_loaded(),
            "loaded_on_gpu": is_surya_loaded_on_gpu(),
            "gpu_available": check_gpu_available_for_surya(),
            "memory_mb": surya_mem,
        },
        "gpu": gpu_info,
    }
