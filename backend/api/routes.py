import os
import uuid
import asyncio
import aiosqlite
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response, HTMLResponse
from backend.config import TMP_DIR, DB_PATH
from backend import database as db
import re

from backend.services.parse_service import process_upload, process_document, get_parse_results, get_parse_progress, TEXT_TYPES
from backend.services.layout_service import get_raw_layout_data, generate_layout_annotation_image

router = APIRouter(prefix="/api")

_processing_tasks: dict[int, asyncio.Task] = {}


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
            "jpg_path": p["jpg_path"],
            "single_pdf_path": p["single_pdf_path"],
        }
        for p in pages
    ]

    progress = get_parse_progress(doc_id)

    return {
        "document_id": doc_id,
        "status": doc["status"],
        "page_count": doc["page_count"],
        "pages": page_statuses,
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
        await conn.commit()

    return {"message": "Elements reordered", "page_id": page_id}


@router.get("/pages/{page_id}/elements")
async def get_page_elements(page_id: int):
    elements = await db.get_elements(page_id)
    return {"elements": elements}


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


def _extract_table_rows(html: str) -> list[str]:
    if not html:
        return []
    tr_pattern = re.compile(r'<tr[^>]*>.*?</tr>', re.DOTALL | re.IGNORECASE)
    return tr_pattern.findall(html)


def _build_merged_table(first_html: str, continuation_htmls: list[str]) -> str:
    rows = _extract_table_rows(first_html)
    for cont_html in continuation_htmls:
        cont_rows = _extract_table_rows(cont_html)
        if cont_rows:
            rows.extend(cont_rows)

    if not rows:
        return first_html

    return "<table border='1' cellpadding='4' cellspacing='0'>\n" + "\n".join(rows) + "\n</table>"


def _merge_cross_page_tables(pages: list[dict]) -> list[dict]:
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



