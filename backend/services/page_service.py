import logging
import asyncio
import aiosqlite
from datetime import datetime
from pathlib import Path

from backend.config import DB_PATH
from backend import database as db
from backend.services.order_service import (
    assign_reading_order, check_gpu_available_for_surya,
    reset_surya_state, is_surya_loaded_on_gpu, reset_cuda_corrupted_state
)

logger = logging.getLogger(__name__)

_reordering_pages: set[int] = set()


def is_reordering_page(page_id: int) -> bool:
    return page_id in _reordering_pages


def get_all_reordering_pages() -> list[int]:
    return list(_reordering_pages)


async def surya_reorder_page(page_id: int) -> dict:
    page = await db.get_page(page_id)
    if not page:
        raise ValueError("Page not found")

    if page["status"] != "completed":
        raise ValueError("Page must be completed before reordering")

    jpg_path = page.get("jpg_path")
    if not jpg_path or not Path(jpg_path).exists():
        raise ValueError("Page image not found")

    if page_id in _reordering_pages:
        raise RuntimeError("该页面正在重排序中，请稍候...")

    reset_cuda_corrupted_state()

    model_on_gpu = is_surya_loaded_on_gpu()

    if not model_on_gpu:
        reset_surya_state()
    gpu_ok = check_gpu_available_for_surya()

    if not gpu_ok:
        async with aiosqlite.connect(str(DB_PATH)) as conn:
            await conn.execute(
                "UPDATE pdf_pages SET is_ordered = 0, updated_at = ? WHERE id = ?",
                (datetime.now().isoformat(), page_id)
            )
            await conn.commit()
        raise RuntimeError(
            "GPU资源不足，无法加载Surya排序模型。请释放显存后重试。该页已标记为未排序。"
        )

    elements = await db.get_elements(page_id)
    if not elements:
        raise ValueError("No elements found on this page")

    elem_dicts = []
    for elem in elements:
        elem_dicts.append({
            "_id": elem["id"],
            "element_type": elem["element_type"],
            "bbox": (elem["bbox_x0"], elem["bbox_y0"], elem["bbox_x1"], elem["bbox_y1"]),
            "confidence": elem.get("confidence", 1.0),
            "reading_order": elem.get("reading_order", 0),
            "content": elem.get("content", ""),
            "content_format": elem.get("content_format", ""),
        })

    _reordering_pages.add(page_id)
    try:
        reordered, surya_ok = await asyncio.to_thread(
            assign_reading_order, elem_dicts, jpg_path
        )

        async with aiosqlite.connect(str(DB_PATH)) as conn:
            if surya_ok:
                for idx, elem in enumerate(reordered):
                    elem_id = elem.get("_id")
                    if elem_id is not None:
                        await conn.execute(
                            "UPDATE page_elements SET reading_order = ? WHERE id = ? AND page_id = ?",
                            (idx, elem_id, page_id)
                        )
                await conn.execute(
                    "UPDATE pdf_pages SET is_ordered = 1, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), page_id)
                )
                await conn.commit()
            else:
                await conn.execute(
                    "UPDATE pdf_pages SET is_ordered = 0, updated_at = ? WHERE id = ?",
                    (datetime.now().isoformat(), page_id)
                )
                await conn.commit()
                raise RuntimeError("Surya排序失败（可能是CUDA错误）。该页已标记为未排序。")
    finally:
        _reordering_pages.discard(page_id)

    return {"page_id": page_id, "is_ordered": True}


async def get_page_elements_with_order(page_id: int) -> dict:
    elements = await db.get_elements(page_id)
    page = await db.get_page(page_id)
    is_ordered = bool(page.get("is_ordered", 1)) if page else True
    return {"elements": elements, "is_ordered": is_ordered}


async def get_page_single_pdf(page_id: int) -> str | None:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM pdf_pages WHERE id = ?", (page_id,))
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Page not found")

        if row["single_pdf_path"] and os.path.exists(row["single_pdf_path"]):
            return row["single_pdf_path"]
        return None


import os
