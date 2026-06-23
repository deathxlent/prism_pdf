import os
import uuid
import asyncio
import logging
import io
import zipfile
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response

from backend.config import TMP_DIR
from backend import database as db
from backend.services.parse_service import (
    process_upload, process_document, get_parse_results,
    get_parse_progress, TEXT_TYPES,
)
from backend.services.layout_service import (
    get_raw_layout_data, generate_layout_annotation_image,
)
from backend.services.element_service import (
    update_element, delete_element, create_element, reorder_elements,
    describe_image_element,
)
from backend.services.document_service import (
    delete_document, reparse_document, translate_page, translate_document,
    get_model_status,
)
from backend.services.page_service import (
    surya_reorder_page, get_page_elements_with_order,
    get_all_reordering_pages, get_page_single_pdf,
)
from backend.services.export_service import (
    generate_document_html, generate_page_html, generate_page_markdown,
    generate_document_markdown, generate_rag_single_html, generate_rag_per_page_zip,
    generate_rag_single_page_html,
)

logger = logging.getLogger(__name__)

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
async def get_status():
    return await get_model_status()


@router.delete("/documents/{doc_id}")
async def delete_doc(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        await delete_document(doc_id)
    except Exception as e:
        logger.warning(f"Error deleting document {doc_id}: {e}")

    return {"message": "Deleted", "document_id": doc_id}


@router.post("/reparse/{doc_id}")
async def reparse_doc(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc["status"] == "processing":
        return {"message": "Already processing", "document_id": doc_id}

    try:
        await reparse_document(doc_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))

    task = asyncio.create_task(process_document(doc_id))
    _processing_tasks[doc_id] = task

    return {"message": "Reparsing started", "document_id": doc_id}


@router.put("/elements/{element_id}")
async def update_element_route(element_id: int, data: dict):
    element = await db.get_element(element_id)
    if not element:
        raise HTTPException(status_code=404, detail="Element not found")

    updated = await update_element(element_id, data)
    return updated


@router.put("/pages/{page_id}/elements/reorder")
async def reorder_elements_route(page_id: int, data: dict):
    element_order = data.get("element_order", [])
    if not element_order:
        raise HTTPException(status_code=400, detail="element_order is required")

    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    await reorder_elements(page_id, element_order)
    return {"message": "Elements reordered", "page_id": page_id}


@router.post("/pages/{page_id}/reorder")
async def surya_reorder_page_route(page_id: int):
    try:
        result = await surya_reorder_page(page_id)
        return {"message": "Page reordered with Surya", **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        if "正在重排序" in str(e):
            raise HTTPException(status_code=409, detail=str(e))
        if "GPU资源不足" in str(e):
            raise HTTPException(status_code=503, detail=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pages/reorder-status")
async def get_all_reorder_status():
    return {"reordering_pages": get_all_reordering_pages()}


@router.get("/pages/{page_id}/elements")
async def get_page_elements_route(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    return await get_page_elements_with_order(page_id)


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


@router.get("/pages/{page_id}/jpg")
async def get_page_jpg(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    jpg_path = page.get("jpg_path")
    if jpg_path and os.path.exists(jpg_path):
        return FileResponse(jpg_path)
    raise HTTPException(status_code=404, detail="Page image not found")


@router.get("/pages/{page_id}/pdf")
async def get_page_pdf(page_id: int):
    try:
        pdf_path = await get_page_single_pdf(page_id)
        if pdf_path:
            return FileResponse(pdf_path)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

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
async def delete_element_route(element_id: int):
    element = await db.get_element(element_id)
    if not element:
        raise HTTPException(status_code=404, detail="Element not found")

    await delete_element(element_id)
    return {"message": "Element deleted", "element_id": element_id}


@router.post("/pages/{page_id}/elements")
async def create_element_route(page_id: int, data: dict):
    try:
        return await create_element(page_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


@router.get("/documents/{doc_id}/search")
async def search_document(doc_id: int, q: str):
    document = await db.get_document(doc_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    if not q or not q.strip():
        return {"results": [], "total": 0}

    results = await db.search_elements(doc_id, q.strip())
    return {"results": results, "total": len(results)}


@router.get("/documents/{doc_id}/export/html")
async def export_document_html(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    html_content = generate_document_html(pages, doc)
    filename = f"{Path(doc['original_filename']).stem}_解析结果.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/export/markdown")
async def export_document_markdown(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    md_content = generate_document_markdown(pages, doc)
    filename = f"{Path(doc['original_filename']).stem}_解析结果.md"

    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/html")
async def export_page_html_route(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    html_content = generate_page_html(page, doc, elements)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


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
            html_content = generate_page_html(page, doc, elements)
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


@router.get("/documents/{doc_id}/export/rag-html")
async def export_document_rag_html(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    html_content = generate_rag_single_html(pages, doc, use_translated=False)
    filename = f"{Path(doc['original_filename']).stem}_RAG友好.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/export/rag-html-zip")
async def export_document_rag_html_zip(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await db.get_pages(doc_id)
    pages_elements = {}
    for page in pages:
        pages_elements[page["id"]] = await db.get_elements(page["id"])

    zip_bytes = generate_rag_per_page_zip(pages, doc, pages_elements, use_translated=False)
    zip_filename = f"{Path(doc['original_filename']).stem}_RAG友好_按页.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{zip_filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/export/translated/rag-html")
async def export_document_translated_rag_html(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    html_content = generate_rag_single_html(pages, doc, use_translated=True)
    filename = f"{Path(doc['original_filename']).stem}_译文_RAG友好.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/export/translated/rag-html-zip")
async def export_document_translated_rag_html_zip(doc_id: int):
    doc = await db.get_document(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    pages = await db.get_pages(doc_id)
    pages_elements = {}
    for page in pages:
        pages_elements[page["id"]] = await db.get_elements(page["id"])

    zip_bytes = generate_rag_per_page_zip(pages, doc, pages_elements, use_translated=True)
    zip_filename = f"{Path(doc['original_filename']).stem}_译文_RAG友好_按页.zip"

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{zip_filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/markdown")
async def export_page_markdown_route(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    md_content = generate_page_markdown(page, doc, elements, TEXT_TYPES)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页.md"

    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/export/translated/html")
async def export_document_translated_html(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    html_content = generate_document_html(pages, doc, use_translated=True)
    filename = f"{Path(doc['original_filename']).stem}_译文.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/translated/count")
async def get_translated_count(doc_id: int):
    pages = await db.get_pages(doc_id)
    count = 0
    for page in pages:
        elements = await db.get_elements(page["id"])
        for elem in elements:
            if elem.get("translated_content"):
                count += 1
    return {"count": count}


@router.get("/documents/{doc_id}/export/translated/markdown")
async def export_document_translated_markdown(doc_id: int):
    result = await get_parse_results(doc_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    pages = result["pages"]
    doc = result["document"]

    md_content = generate_document_markdown(pages, doc, use_translated=True)
    filename = f"{Path(doc['original_filename']).stem}_译文.md"

    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/translated/html")
async def export_page_translated_html(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    html_content = generate_page_html(page, doc, elements, use_translated=True)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页_译文.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/translated/markdown")
async def export_page_translated_markdown(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    md_content = generate_page_markdown(page, doc, elements, TEXT_TYPES, use_translated=True)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页_译文.md"

    return Response(
        content=md_content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/rag-html")
async def export_page_rag_html(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    html_content = generate_rag_single_page_html(page, doc, elements)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页_RAG友好.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/pages/{page_id}/export/translated-rag-html")
async def export_page_translated_rag_html(page_id: int):
    page = await db.get_page(page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    doc = await db.get_document(page["document_id"])
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    elements = await db.get_elements(page_id)
    html_content = generate_rag_single_page_html(page, doc, elements, use_translated=True)
    filename = f"{Path(doc['original_filename']).stem}_第{page['page_number']}页_译文_RAG友好.html"

    return Response(
        content=html_content,
        media_type="text/html; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/documents/{doc_id}/export/translated/html-zip")
async def export_document_translated_html_zip(doc_id: int):
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
            html_content = generate_page_html(page, doc, elements, use_translated=True)
            page_num_str = str(page["page_number"]).zfill(3)
            filename = f"page_{page_num_str}_译文.html"
            zf.writestr(filename, html_content)

    zip_buffer.seek(0)
    zip_filename = f"{Path(doc['original_filename']).stem}_pages_译文_html.zip"

    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{zip_filename.encode('utf-8').decode('latin-1')}"}
    )


@router.get("/llm-config/types")
async def get_llm_config_types():
    from backend.services.llm_config_service import get_model_types
    return {"model_types": get_model_types()}


@router.get("/llm-config")
async def get_all_llm_configs():
    from backend.services.llm_config_service import get_all_configs
    return get_all_configs()


@router.get("/llm-config/active")
async def get_active_llm_config():
    from backend.services.llm_config_service import get_active_config, get_active_type
    return {
        "active_type": get_active_type(),
        "active_config": get_active_config(),
    }


@router.put("/llm-config/active-type/{type_key}")
async def set_active_llm_type(type_key: str):
    from backend.services.llm_config_service import set_active_type
    try:
        set_active_type(type_key)
        return {"message": "Active type updated", "active_type": type_key}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/llm-config/{type_key}")
async def get_llm_configs_by_type(type_key: str):
    from backend.services.llm_config_service import get_configs_by_type
    try:
        configs = get_configs_by_type(type_key)
        return {"type": type_key, "configs": configs}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/llm-config/{type_key}")
async def create_llm_config(type_key: str, data: dict):
    from backend.services.llm_config_service import create_config
    try:
        config = create_config(type_key, data)
        return {"message": "Config created", "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/llm-config/{type_key}/{config_id}/activate")
async def activate_llm_config(type_key: str, config_id: str):
    from backend.services.llm_config_service import set_active_config
    try:
        ok = set_active_config(type_key, config_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"message": "Config activated", "type": type_key, "config_id": config_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/llm-config/{type_key}/{config_id}")
async def update_llm_config(type_key: str, config_id: str, data: dict):
    from backend.services.llm_config_service import update_config
    try:
        config = update_config(type_key, config_id, data)
        if config is None:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"message": "Config updated", "config": config}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/llm-config/{type_key}/{config_id}")
async def delete_llm_config(type_key: str, config_id: str):
    from backend.services.llm_config_service import delete_config
    try:
        ok = delete_config(type_key, config_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Config not found")
        return {"message": "Config deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/elements/{element_id}/describe-image")
async def describe_image_element_route(element_id: int):
    try:
        result = await describe_image_element(element_id)
        return {"element_id": element_id, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/elements/{element_id}/translate")
async def translate_element(element_id: int, data: dict):
    from backend.services.llm_service import translate_text

    element = await db.get_element(element_id)
    if not element:
        raise HTTPException(status_code=404, detail="Element not found")

    target_language = data.get("target_language", "en")
    etype = element.get("element_type", "")
    content = element.get("content", "") or ""
    image_desc = element.get("image_description", "") or ""

    text_to_translate = ""
    if etype == "Picture":
        if image_desc:
            text_to_translate = image_desc
        else:
            raise HTTPException(status_code=400, detail="图片元素无描述，请先生成图片描述")
    else:
        if not content.strip():
            raise HTTPException(status_code=400, detail="元素内容为空，无法翻译")
        text_to_translate = content

    try:
        translated = translate_text(text_to_translate, target_language)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"翻译失败: {str(e)}")

    await db.update_element(element_id, translated_content=translated)

    return {"element_id": element_id, "translated_content": translated}


@router.post("/pages/{page_id}/translate")
async def translate_page_route(page_id: int, data: dict):
    target_language = data.get("target_language", "en")

    try:
        result = await translate_page(page_id, target_language)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/documents/{doc_id}/translate")
async def translate_document_route(doc_id: int, data: dict):
    target_language = data.get("target_language", "en")

    try:
        result = await translate_document(doc_id, target_language)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
