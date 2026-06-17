import os
import uuid
import asyncio
import aiosqlite
import zipfile
import io
import logging
import re
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response, HTMLResponse
from backend.config import TMP_DIR, DB_PATH
from backend import database as db

from backend.services.parse_service import process_upload, process_document, get_parse_results, get_parse_progress, TEXT_TYPES
from backend.services.layout_service import get_raw_layout_data, generate_layout_annotation_image
from backend.services.order_service import assign_reading_order, check_gpu_available_for_surya, reset_surya_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api")

_processing_tasks: dict[int, asyncio.Task] = {}
_reordering_pages: set[int] = set()


@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    ext = Path(file.filename).suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    save_path = str(TMP_DIR / unique_name)

    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    result = await process_upload(save_path, file.filename)

    if "error" in result:
        try:
            os.unlink(save_path)
        except OSError:
            pass
        if result.get("encrypted"):
            raise HTTPException(status_code=422, detail=result["error"])
        raise HTTPException(status_code=422, detail=result["error"])

    return {"document_id": result["document_id"], "page_count": result["page_count"]}


@router.post("/parse/{doc_id}")
async def parse_document(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["status"] == "processing":
        return {"message": "Already processing", "document_id": doc_id}

    if doc["status"] == "completed":
        return {"message": "Already completed", "document_id": doc_id}

    task = asyncio.create_task(process_document(doc_id))
    _processing_tasks[doc_id] = task

    return {"message": "Parsing started", "document_id": doc_id}


@router.get("/status/{doc_id}")
async def get_status(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await db.get_pages(doc_id)
    page_statuses = [
        {
            "id": p["id"],
            "page_number": p["page_number"],
            "width": p["width"],
            "height": p["height"],
            "jpg_width": p["jpg_width"],
            "jpg_height": p["jpg_height"],
            "status": p["status"],
            "is_scanned": bool(p["is_scanned"]),
            "is_ordered": bool(p.get("is_ordered", 1)),
            "jpg_path": p["jpg_path"],
            "single_pdf_path": p["single_pdf_path"],
        }
        for p in pages
    ]

    progress = get_parse_progress(doc_id)

    unordered_count = sum(1 for p in page_statuses if not p["is_ordered"])

    return {
        "document_id": doc_id,
        "status": doc["status"],
        "page_count": doc["page_count"],
        "pages": page_statuses,
        "unordered_count": unordered_count,
        "progress": progress,
    }


@router.get("/progress/{doc_id}")
async def get_progress(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    progress = get_parse_progress(doc_id)
    return {
        "document_id": doc_id,
        "status": doc["status"],
        "progress": progress,
    }


@router.get("/results/{doc_id}")
async def results(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/documents")
async def list_docs():
    docs = await db.list_documents()
    return {"documents": docs}


@router.get("/model-status")
async def get_model_status():
    from backend.services.layout_service import (
        is_yolo_model_loaded, is_yolo_loaded_on_gpu, check_gpu_available_for_yolo
    )
    from backend.services.order_service import (
        is_surya_model_loaded, is_surya_loaded_on_gpu, check_gpu_available_for_surya
    )
    
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            free_vram = torch.cuda.mem_get_info()[0] / (1024 * 1024)
            total_vram = torch.cuda.mem_get_info()[1] / (1024 * 1024)
            gpu_info = {
                "cuda_available": True,
                "device_name": torch.cuda.get_device_name(0),
                "free_vram_mb": round(free_vram, 2),
                "total_vram_mb": round(total_vram, 2),
            }
        else:
            gpu_info = {"cuda_available": False}
    except Exception as e:
        gpu_info = {"cuda_available": False, "error": str(e)}
    
    return {
        "yolo": {
            "loaded": is_yolo_model_loaded(),
            "loaded_on_gpu": is_yolo_loaded_on_gpu(),
            "gpu_available": check_gpu_available_for_yolo(),
        },
        "surya_order": {
            "loaded": is_surya_model_loaded(),
            "loaded_on_gpu": is_surya_loaded_on_gpu(),
            "gpu_available": check_gpu_available_for_surya(),
        },
        "gpu": gpu_info,
    }


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    import shutil
    try:
        doc_dir = Path(doc["file_path"]).parent / Path(doc["file_path"]).stem
        if doc_dir.exists():
            shutil.rmtree(str(doc_dir), ignore_errors=True)
        if Path(doc["file_path"]).exists():
            os.unlink(doc["file_path"])
    except OSError:
        pass

    await db.delete_document(doc_id)
    return {"message": "Deleted", "document_id": doc_id}


@router.post("/reparse/{doc_id}")
async def reparse_document(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["status"] == "processing":
        return {"message": "Already processing", "document_id": doc_id}

    await db.execute_query("DELETE FROM page_elements WHERE page_id IN (SELECT id FROM pdf_pages WHERE document_id = ?)", (doc_id,))
    await db.execute_query("DELETE FROM pdf_pages WHERE document_id = ?", (doc_id,))

    await db.update_document(doc_id, status="uploaded", error_message=None)

    task = asyncio.create_task(process_document(doc_id))
    _processing_tasks[doc_id] = task

    return {"message": "Reparsing started", "document_id": doc_id}


@router.put("/elements/{element_id}")
async def update_element(element_id: int, data: dict):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Element not found")

        updates = {}
        if "content" in data:
            updates["content"] = data["content"]
        if "reading_order" in data:
            updates["reading_order"] = data["reading_order"]
        if "element_type" in data:
            updates["element_type"] = data["element_type"]

        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values()) + [element_id]
            await conn.execute(f"UPDATE page_elements SET {sets} WHERE id = ?", vals)
            await conn.commit()

        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        return dict(row)


@router.put("/pages/{page_id}/elements/reorder")
async def reorder_elements(page_id: int, data: dict):
    element_order = data.get("element_order", [])
    if not element_order:
        raise HTTPException(status_code=400, detail="element_order is required")

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        for idx, elem_id in enumerate(element_order):
            await conn.execute(
                "UPDATE page_elements SET reading_order = ? WHERE id = ? AND page_id = ?",
                (idx, elem_id, page_id)
            )
        await conn.execute(
            "UPDATE pdf_pages SET is_ordered = 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), page_id)
        )
        await conn.commit()

    return {"message": "Elements reordered", "page_id": page_id}


@router.post("/pages/{page_id}/reorder")
async def surya_reorder_page(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    if page["status"] != "completed":
        raise HTTPException(status_code=400, detail="Page must be completed before reordering")

    jpg_path = page.get("jpg_path")
    if not jpg_path or not Path(jpg_path).exists():
        raise HTTPException(status_code=400, detail="Page image not found")

    if page_id in _reordering_pages:
        raise HTTPException(status_code=409, detail="该页面正在重排序中，请稍候...")

    from backend.services.order_service import is_surya_loaded_on_gpu
    
    model_on_gpu = is_surya_loaded_on_gpu()
    
    if not model_on_gpu:
        reset_surya_state()
    gpu_ok = check_gpu_available_for_surya()
    
    if not gpu_ok:
        raise HTTPException(
            status_code=503,
            detail="GPU资源不足，无法加载Surya排序模型。请释放显存后重试。"
        )

    elements = await db.get_elements(page_id)
    if not elements:
        raise HTTPException(status_code=400, detail="No elements found on this page")

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

        if not surya_ok:
            raise HTTPException(
                status_code=503,
                detail="Surya排序模型加载失败，无法进行重排序。"
            )

        async with aiosqlite.connect(str(DB_PATH)) as conn:
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
    finally:
        _reordering_pages.discard(page_id)

    return {"message": "Page reordered with Surya", "page_id": page_id, "is_ordered": True}


@router.get("/pages/reorder-status")
async def get_all_reorder_status():
    return {
        "reordering_pages": list(_reordering_pages)
    }


@router.get("/pages/{page_id}/elements")
async def get_page_elements(page_id: int):
    elements = await db.get_elements(page_id)
    page = await db.get_page(page_id)
    is_ordered = bool(page.get("is_ordered", 1)) if page else True
    return {"elements": elements, "is_ordered": is_ordered}


@router.get("/documents/{doc_id}/thumbnail")
async def get_document_thumbnail(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await db.get_pages(doc_id)
    if pages and pages[0]["jpg_path"]:
        jpg_path = pages[0]["jpg_path"]
        if os.path.exists(jpg_path):
            return FileResponse(jpg_path)

    return {"error": "No thumbnail available"}, 404


@router.get("/pages/{page_id}/pdf")
async def get_page_pdf(page_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM pdf_pages WHERE id = ?", (page_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Page not found")

        if row["single_pdf_path"] and os.path.exists(row["single_pdf_path"]):
            return FileResponse(row["single_pdf_path"])

    return {"error": "No single PDF available"}, 404


@router.get("/pages/{page_id}/layout-raw")
async def get_page_raw_layout(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    jpg_path = page.get("jpg_path", "")
    raw_data = get_raw_layout_data(jpg_path)

    return {
        "page_id": page_id,
        "jpg_path": jpg_path,
        "raw_detections": raw_data,
        "count": len(raw_data)
    }


@router.delete("/elements/{element_id}")
async def delete_element(element_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Element not found")

        await conn.execute("DELETE FROM page_elements WHERE id = ?", (element_id,))
        await conn.commit()

    return {"message": "Element deleted", "element_id": element_id}


@router.post("/pages/{page_id}/elements")
async def create_element(page_id: int, data: dict):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    element_type = data.get("element_type", "Text")
    bbox = data.get("bbox")
    content = data.get("content", "")
    content_format = data.get("content_format", "markdown")
    confidence = data.get("confidence", 1.0)

    if not bbox or len(bbox) != 4:
        raise HTTPException(status_code=400, detail="bbox is required and must have 4 values")

    elements = await db.get_elements(page_id)
    reading_order = len(elements)

    element_id = await db.create_element(
        page_id, element_type, tuple(bbox), confidence, reading_order,
        content=content, content_format=content_format
    )

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        return dict(row)


@router.get("/pages/{page_id}/layout-annotation")
async def get_page_layout_annotation(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    jpg_path = page.get("jpg_path", "")
    raw_data = get_raw_layout_data(jpg_path)

    if not raw_data:
        raise HTTPException(status_code=404, detail="No raw layout data available")

    try:
        image_bytes = generate_layout_annotation_image(jpg_path, raw_data)
        return Response(content=image_bytes, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate annotation image: {str(e)}")


def _parse_html_table_to_matrix(html: str) -> list[list[dict]]:
    """
    解析 HTML 表格为二维单元格矩阵用于合并操作。
    
    与 parse_service._parse_html_table() 相同逻辑，但独立实现避免循环引用。
    每个单元格: {content, is_header, rowspan, colspan} 或 None (被覆盖)
    """
    if not html:
        return []
    from html import unescape
    rows_match = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    if not rows_match:
        return []
    
    temp_matrix = []
    max_cols = 0
    for row_html in rows_match:
        cells_match = re.findall(r'<(t[dh])[^>]*>(.*?)</\1>', row_html, re.DOTALL | re.IGNORECASE)
        row_cells = []
        for tag, cell_html in cells_match:
            tag = tag.lower()
            is_header = tag == 'th'
            rs_match = re.search(r"rowspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            rowspan = int(rs_match.group(1)) if rs_match else 1
            cs_match = re.search(r"colspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            colspan = int(cs_match.group(1)) if cs_match else 1
            content = re.sub(r'<[^>]+>', '', cell_html).strip()
            content = unescape(content)
            row_cells.append({
                'content': content,
                'is_header': is_header,
                'rowspan': rowspan,
                'colspan': colspan,
            })
        if row_cells:
            temp_matrix.append(row_cells)
            row_col_count = sum(c['colspan'] for c in row_cells)
            max_cols = max(max_cols, row_col_count)
    
    if not temp_matrix:
        return []
    
    full_matrix = [[None for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    covered = [[False for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    for ri, row_cells in enumerate(temp_matrix):
        col_pos = 0
        for cell in row_cells:
            while col_pos < max_cols and covered[ri][col_pos]:
                col_pos += 1
            if col_pos >= max_cols:
                break
            full_matrix[ri][col_pos] = {
                'content': cell['content'],
                'is_header': cell['is_header'],
                'rowspan': cell['rowspan'],
                'colspan': cell['colspan'],
            }
            for r in range(ri, min(ri + cell['rowspan'], len(temp_matrix))):
                for c in range(col_pos, min(col_pos + cell['colspan'], max_cols)):
                    if r != ri or c != col_pos:
                        covered[r][c] = True
            col_pos += cell['colspan']
    return full_matrix


def _matrix_to_html(matrix: list[list[dict]]) -> str:
    """将单元格矩阵转换回 HTML 表格字符串。"""
    if not matrix:
        return ""
    rows = len(matrix)
    cols = len(matrix[0]) if rows > 0 else 0
    if rows == 0 or cols == 0:
        return ""
    
    from html import escape
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
            tag = "th" if cell.get('is_header', False) else "td"
            rowspan = cell.get('rowspan', 1)
            colspan = cell.get('colspan', 1)
            content = escape(cell.get('content', ''))
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


def _build_merged_table(first_html: str, continuation_htmls: list[str]) -> str:
    """
    合并跨页表格，处理空单元格吸收和 colspan/rowspan 更新。
    
    策略:
    1. 将第一页表格解析为单元格矩阵
    2. 对每个续页表格:
       a. 解析为单元格矩阵
       b. 如果续页首行有空单元格，将它们吸收到累积矩阵的最后一行（扩展 rowspan）
       c. 如果首行所有单元格都被吸收，删除该行
       d. 将剩余行追加到累积矩阵
    3. 将最终矩阵转回 HTML
    """
    if not first_html:
        return ""
    
    # 解析第一页
    acc_matrix = _parse_html_table_to_matrix(first_html)
    if not acc_matrix:
        return first_html
    
    for cont_html in continuation_htmls:
        if not cont_html:
            continue
        cont_matrix = _parse_html_table_to_matrix(cont_html)
        if not cont_matrix:
            continue
        
        acc_cols = len(acc_matrix[0]) if acc_matrix else 0
        cont_cols = len(cont_matrix[0]) if cont_matrix else 0
        max_cols = max(acc_cols, cont_cols)
        
        # 确保累积矩阵列数足够
        for row in acc_matrix:
            while len(row) < max_cols:
                row.append(None)
        for row in cont_matrix:
            while len(row) < max_cols:
                row.append(None)
        
        # 检查续页第一行是否有空单元格
        first_cont_row = cont_matrix[0]
        empty_cols = []
        for ci in range(max_cols):
            if ci < len(first_cont_row):
                cell = first_cont_row[ci]
                if cell is None:
                    continue
                content = cell.get('content', '').strip()
                if not content:
                    empty_cols.append(ci)
        
        if empty_cols:
            # 将续页第一行的空单元格吸收到累积矩阵最后一行
            last_acc_row = acc_matrix[-1]
            for ci in empty_cols:
                # 找到累积矩阵最后一行中对应位置的单元格（或向左找到最近的非空单元格）
                target_ci = ci
                while target_ci >= 0 and (target_ci >= len(last_acc_row) or last_acc_row[target_ci] is None):
                    target_ci -= 1
                if target_ci >= 0 and target_ci < len(last_acc_row) and last_acc_row[target_ci] is not None:
                    existing_rs = last_acc_row[target_ci].get('rowspan', 1)
                    last_acc_row[target_ci]['rowspan'] = existing_rs + 1
            
            # 如果连续多列为空，合并 colspan
            # 注意：只有在该范围内的所有列在上一行中都是 None（已被现有 colspan 覆盖）时，
            # 才扩展 colspan。如果范围内有独立内容的单元格（如 [C, D] + cont [empty, E]），
            # 则不应扩展 colspan，否则会覆盖独立单元格的内容（D 消失）。
            first_non_empty_col = None
            for ci in range(max_cols):
                if ci >= len(first_cont_row):
                    break
                cell = first_cont_row[ci]
                if cell and cell.get('content', '').strip():
                    first_non_empty_col = ci
                    break
            
            if empty_cols and first_non_empty_col is not None and first_non_empty_col > 0:
                all_covered_by_colspan = True
                for ci in range(1, first_non_empty_col):
                    if (ci < len(last_acc_row) and last_acc_row[ci] is not None
                            and last_acc_row[ci].get('content', '').strip()):
                        all_covered_by_colspan = False
                        break
                
                if all_covered_by_colspan:
                    leftmost_target = None
                    for ci in range(first_non_empty_col):
                        if ci < len(last_acc_row) and last_acc_row[ci] and last_acc_row[ci].get('content', '').strip():
                            leftmost_target = ci
                            break
                    if leftmost_target is None:
                        leftmost_target = 0
                    if leftmost_target < len(last_acc_row) and last_acc_row[leftmost_target]:
                        total_empty_cols = first_non_empty_col - leftmost_target
                        existing_cs = last_acc_row[leftmost_target].get('colspan', 1)
                        last_acc_row[leftmost_target]['colspan'] = existing_cs + total_empty_cols
                        for ci in range(leftmost_target + 1, first_non_empty_col):
                            if ci < len(last_acc_row):
                                last_acc_row[ci] = None
        
        # 构建新的续页矩阵: 首行的空单元格被吸收后置 None，非空单元格保留
        new_cont_rows = []
        for ri, row in enumerate(cont_matrix):
            if ri == 0:
                # 首行: 空单元格被吸收，非空单元格保留为正常行
                new_row = []
                all_absorbed = True
                for ci, cell in enumerate(row):
                    if cell is None:
                        new_row.append(None)
                        continue
                    if ci in empty_cols:
                        new_row.append(None)  # 已被吸收
                    else:
                        new_row.append(cell.copy() if cell else None)
                        all_absorbed = False
                if not all_absorbed:
                    # 至少还有非空单元格，保留该行（只保留非吸收的单元格）
                    new_cont_rows.append(new_row)
                # 如果所有单元格都被吸收，跳过该行
            else:
                new_cont_rows.append([c.copy() if c else None for c in row])
        
        # 将处理后的续页行追加到累积矩阵
        if new_cont_rows:
            acc_matrix.extend(new_cont_rows)
    
    # 转换最终矩阵为 HTML
    return _matrix_to_html(acc_matrix)


def _merge_cross_page_tables(pages: list[dict]) -> list[dict]:
    """
    合并跨页表格组，更新首元素的内容为合并后的 HTML，
    同时标记被合并的组以便在导出时跳过非首元素。
    """
    group_tables = {}
    for page in pages:
        for elem in page["elements"]:
            cpg = elem.get("cross_page_group")
            if cpg is not None and elem["element_type"] == "Table":
                if cpg not in group_tables:
                    group_tables[cpg] = []
                group_tables[cpg].append(elem)

    merged_groups = set()
    for group_id, tables in group_tables.items():
        if len(tables) <= 1:
            continue
        first = tables[0]
        rest = tables[1:]
        first_html = first.get("content", "") or ""
        rest_htmls = [(t.get("content", "") or "") for t in rest]
        merged_html = _build_merged_table(first_html, rest_htmls)
        first["content"] = merged_html
        merged_groups.add(group_id)

    for page in pages:
        page["_skip_groups"] = merged_groups

    return pages


@router.get("/documents/{doc_id}/export/html")
async def export_document_html(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    pages = _merge_cross_page_tables(pages)

    first_elem_per_group = {}
    for page in pages:
        for elem in sorted(page["elements"], key=lambda e: e["reading_order"]):
            cpg = elem.get("cross_page_group")
            if cpg is not None and elem["element_type"] == "Table" and cpg not in first_elem_per_group:
                first_elem_per_group[cpg] = elem["id"]

    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "<meta charset='UTF-8'>",
        f"<title>{doc['original_filename']} - 解析结果</title>",
        "<style>",
        "body { font-family: 'Microsoft YaHei', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }",
        "h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; margin-top: 40px; page-break-before: always; }",
        "h1:first-child { page-break-before: auto; }",
        "h2 { color: #555; margin-top: 20px; }",
        "h3 { color: #666; }",
        "table { border-collapse: collapse; width: 100%; margin: 10px 0; }",
        "table, th, td { border: 1px solid #ddd; }",
        "th, td { padding: 8px 12px; text-align: left; }",
        "th { background-color: #f5f5f5; }",
        "img { max-width: 100%; height: auto; margin: 10px 0; }",
        "code { background-color: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; }",
        ".page-header, .page-footer { color: #888; font-size: 0.9em; font-style: italic; }",
        ".formula { text-align: center; font-size: 1.1em; margin: 15px 0; }",
        ".caption { font-style: italic; color: #666; text-align: center; }",
        "</style>",
        "</head>",
        "<body>",
    ]

    for page in pages:
        page_num = page["page_number"]
        html_parts.append(f"<h1>第 {page_num} 页</h1>")

        elements = sorted(page["elements"], key=lambda e: e["reading_order"])
        skip_groups = page.get("_skip_groups", set())

        for elem in elements:
            etype = elem["element_type"]
            content = elem.get("content", "") or ""
            content_format = elem.get("content_format", "") or ""
            cpg = elem.get("cross_page_group")

            if etype == "Table" and cpg in skip_groups and cpg is not None:
                if first_elem_per_group.get(cpg) != elem["id"]:
                    continue

            if etype == "Title":
                html_parts.append(f"<h1 style='color: #dc143c;'>{content}</h1>")
            elif etype == "Section-header":
                html_parts.append(f"<h2>{content}</h2>")
            elif etype == "Page-header":
                html_parts.append(f"<div class='page-header'>{content}</div>")
            elif etype == "Page-footer":
                html_parts.append(f"<div class='page-footer'>{content}</div>")
            elif etype == "Formula":
                html_parts.append(f"<div class='formula'>{content}</div>")
            elif etype == "Table":
                if content_format == "html":
                    html_parts.append(content)
                else:
                    html_parts.append(f"<pre>{content}</pre>")
            elif etype == "Picture":
                if content:
                    html_parts.append(f'<img src="file://{content}" alt="Picture">')
            elif etype == "Caption":
                html_parts.append(f"<div class='caption'>{content}</div>")
            elif etype == "List-item":
                html_parts.append(f"<li>{content}</li>")
            elif etype in TEXT_TYPES:
                if content.strip():
                    html_parts.append(f"<p>{content}</p>")
            else:
                if content.strip():
                    html_parts.append(f"<p>{content}</p>")

    html_parts.append("</body></html>")

    html_content = "\n".join(html_parts)
    filename = f"{Path(doc['original_filename']).stem}_解析结果.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/html")
async def export_page_html(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)

    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "<meta charset='UTF-8'>",
        f"<title>{doc['original_filename']} - 第 {page['page_number']} 页</title>",
        "<style>",
        "body { font-family: 'Microsoft YaHei', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }",
        "h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }",
        "h2 { color: #555; margin-top: 20px; }",
        "h3 { color: #666; }",
        "table { border-collapse: collapse; width: 100%; margin: 10px 0; }",
        "table, th, td { border: 1px solid #ddd; }",
        "th, td { padding: 8px 12px; text-align: left; }",
        "th { background-color: #f5f5f5; }",
        "img { max-width: 100%; height: auto; margin: 10px 0; }",
        "code { background-color: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; }",
        ".page-header, .page-footer { color: #888; font-size: 0.9em; font-style: italic; }",
        ".formula { text-align: center; font-size: 1.1em; margin: 15px 0; }",
        ".caption { font-style: italic; color: #666; text-align: center; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>第 {page['page_number']} 页</h1>",
    ]

    sorted_elements = sorted(elements, key=lambda e: e["reading_order"])

    for elem in sorted_elements:
        etype = elem["element_type"]
        content = elem.get("content", "") or ""
        content_format = elem.get("content_format", "") or ""

        if etype == "Title":
            html_parts.append(f"<h1 style='color: #dc143c;'>{content}</h1>")
        elif etype == "Section-header":
            html_parts.append(f"<h2>{content}</h2>")
        elif etype == "Page-header":
            html_parts.append(f"<div class='page-header'>{content}</div>")
        elif etype == "Page-footer":
            html_parts.append(f"<div class='page-footer'>{content}</div>")
        elif etype == "Formula":
            html_parts.append(f"<div class='formula'>{content}</div>")
        elif etype == "Table":
            if content_format == "html":
                html_parts.append(content)
            else:
                html_parts.append(f"<pre>{content}</pre>")
        elif etype == "Picture":
            if content:
                html_parts.append(f'<img src="file://{content}" alt="Picture">')
        elif etype == "Caption":
            html_parts.append(f"<div class='caption'>{content}</div>")
        elif etype == "List-item":
            html_parts.append(f"<li>{content}</li>")
        elif etype in TEXT_TYPES:
            if content.strip():
                html_parts.append(f"<p>{content}</p>")
        else:
            if content.strip():
                html_parts.append(f"<p>{content}</p>")

    html_parts.append("</body></html>")

    html_content = "\n".join(html_parts)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


def _generate_page_html(page: dict, doc: dict, elements: list) -> str:
    html_parts = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "<meta charset='UTF-8'>",
        f"<title>{doc['original_filename']} - 第 {page['page_number']} 页</title>",
        "<style>",
        "body { font-family: 'Microsoft YaHei', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }",
        "h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; }",
        "h2 { color: #555; margin-top: 20px; }",
        "h3 { color: #666; }",
        "table { border-collapse: collapse; width: 100%; margin: 10px 0; }",
        "table, th, td { border: 1px solid #ddd; }",
        "th, td { padding: 8px 12px; text-align: left; }",
        "th { background-color: #f5f5f5; }",
        "img { max-width: 100%; height: auto; margin: 10px 0; }",
        "code { background-color: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; }",
        ".page-header, .page-footer { color: #888; font-size: 0.9em; font-style: italic; }",
        ".formula { text-align: center; font-size: 1.1em; margin: 15px 0; }",
        ".caption { font-style: italic; color: #666; text-align: center; }",
        "</style>",
        "</head>",
        "<body>",
        f"<h1>第 {page['page_number']} 页</h1>",
    ]

    sorted_elements = sorted(elements, key=lambda e: e["reading_order"])

    for elem in sorted_elements:
        etype = elem["element_type"]
        content = elem.get("content", "") or ""
        content_format = elem.get("content_format", "") or ""

        if etype == "Title":
            html_parts.append(f"<h1 style='color: #dc143c;'>{content}</h1>")
        elif etype == "Section-header":
            html_parts.append(f"<h2>{content}</h2>")
        elif etype == "Page-header":
            html_parts.append(f"<div class='page-header'>{content}</div>")
        elif etype == "Page-footer":
            html_parts.append(f"<div class='page-footer'>{content}</div>")
        elif etype == "Formula":
            html_parts.append(f"<div class='formula'>{content}</div>")
        elif etype == "Table":
            if content_format == "html":
                html_parts.append(content)
            else:
                html_parts.append(f"<pre>{content}</pre>")
        elif etype == "Picture":
            if content:
                html_parts.append(f'<img src="file://{content}" alt="Picture">')
        elif etype == "Caption":
            html_parts.append(f"<div class='caption'>{content}</div>")
        elif etype == "List-item":
            html_parts.append(f"<li>{content}</li>")
        elif etype in TEXT_TYPES:
            if content.strip():
                html_parts.append(f"<p>{content}</p>")
        else:
            if content.strip():
                html_parts.append(f"<p>{content}</p>")

    html_parts.append("</body></html>")
    return "\n".join(html_parts)


@router.get("/documents/{doc_id}/export/html-zip")
async def export_document_html_zip(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await db.get_pages(doc_id)

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for page in pages:
            if page["status"] != "completed":
                continue
            elements = await db.get_elements(page["id"])
            if not elements:
                continue
            html_content = _generate_page_html(page, doc, elements)
            page_num_str = str(page["page_number"]).zfill(3)
            filename = f"page_{page_num_str}.html"
            zf.writestr(filename, html_content)

    zip_buffer.seek(0)
    zip_filename = f"{Path(doc['original_filename']).stem}_pages_html.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{zip_filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/markdown")
async def export_page_markdown(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    sorted_elements = sorted(elements, key=lambda e: e["reading_order"])

    md_parts = [f"# 第 {page['page_number']} 页\n"]

    for elem in sorted_elements:
        etype = elem["element_type"]
        content = elem.get("content", "") or ""
        content_format = elem.get("content_format", "") or ""

        if etype == "Title":
            md_parts.append(f"# {content}\n")
        elif etype == "Section-header":
            md_parts.append(f"## {content}\n")
        elif etype == "Formula":
            md_parts.append(f"\n{content}\n")
        elif etype == "Table":
            md_parts.append(f"\n{content}\n")
        elif etype == "Picture":
            if content:
                md_parts.append(f"\n![Picture]({content})\n")
        elif etype == "Caption":
            md_parts.append(f"*{content}*\n")
        elif etype in TEXT_TYPES:
            if content.strip():
                md_parts.append(f"{content}\n")
        else:
            if content.strip():
                md_parts.append(f"{content}\n")

    md_content = "\n".join(md_parts)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页.md"

    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )



