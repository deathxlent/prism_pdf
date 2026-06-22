import io
import zipfile
import logging
from pathlib import Path

from backend.services.cross_page_table_service import merge_cross_page_tables

logger = logging.getLogger(__name__)

TEXT_TYPES = {"Caption", "Footnote", "List-item", "Page-footer", "Page-header",
              "Section-header", "Text", "Title"}

HEADER_FOOTER_TYPES = {"Page-header", "Page-footer"}


def _is_header_footer_element(elem: dict) -> bool:
    hf_mark = elem.get("header_footer_mark")
    if hf_mark in ("header", "footer"):
        return True
    etype = elem.get("element_type", "")
    if etype in HEADER_FOOTER_TYPES:
        return True
    return False


def _filter_rag_elements(elements: list) -> list:
    return [e for e in elements if not _is_header_footer_element(e)]


def get_html_style() -> str:
    return """
body { font-family: 'Microsoft YaHei', Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; line-height: 1.6; }
h1 { color: #333; border-bottom: 3px solid #007bff; padding-bottom: 10px; margin-top: 40px; page-break-before: always; }
h1:first-child { page-break-before: auto; }
h2 { color: #555; margin-top: 20px; }
h3 { color: #666; }
table { border-collapse: collapse; width: 100%; margin: 10px 0; }
table, th, td { border: 1px solid #ddd; }
th, td { padding: 8px 12px; text-align: left; }
th { background-color: #f5f5f5; }
img { max-width: 100%; height: auto; margin: 10px 0; }
code { background-color: #f5f5f5; padding: 2px 6px; border-radius: 4px; font-family: Consolas, monospace; }
.page-header, .page-footer { color: #888; font-size: 0.9em; font-style: italic; }
.formula { text-align: center; font-size: 1.1em; margin: 15px 0; }
.caption { font-style: italic; color: #666; text-align: center; }
.figure-container { margin: 15px 0; text-align: center; }
.figure-container img { max-width: 100%; height: auto; }
.figure-caption { font-style: italic; color: #555; font-size: 0.95em; margin-top: 6px; text-align: center; }
"""


def element_to_html(elem: dict, use_translated: bool = False) -> str:
    etype = elem["element_type"]
    content = elem.get("content", "") or ""
    content_format = elem.get("content_format", "") or ""
    translated_content = elem.get("translated_content", "") or ""

    if use_translated and translated_content.strip():
        content = translated_content

    if etype == "Title":
        return f"<h1 style='color: #dc143c;'>{content}</h1>"
    elif etype == "Section-header":
        return f"<h2>{content}</h2>"
    elif etype == "Page-header":
        return f"<div class='page-header'>{content}</div>"
    elif etype == "Page-footer":
        return f"<div class='page-footer'>{content}</div>"
    elif etype == "Formula":
        return f"<div class='formula'>{content}</div>"
    elif etype == "Table":
        if content_format == "html":
            return content
        else:
            return f"<pre>{content}</pre>"
    elif etype == "Picture":
        if content:
            image_description = elem.get("image_description", "") or ""
            if use_translated:
                translated_desc = elem.get("translated_content", "") or ""
                if translated_desc.strip():
                    image_description = translated_desc
            if image_description:
                return (f'<div class="figure-container">'
                        f'<img src="file://{content}" alt="Picture">'
                        f'<div class="figure-caption">{image_description}</div>'
                        f'</div>')
            return f'<img src="file://{content}" alt="Picture">'
    elif etype == "Caption":
        return f"<div class='caption'>{content}</div>"
    elif etype == "List-item":
        return f"<li>{content}</li>"
    elif etype in TEXT_TYPES:
        if content.strip():
            return f"<p>{content}</p>"
    else:
        if content.strip():
            return f"<p>{content}</p>"
    return ""


def build_html_document(title: str, body_html: str) -> str:
    return "\n".join([
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "<meta charset='UTF-8'>",
        f"<title>{title}</title>",
        "<style>",
        get_html_style(),
        "</style>",
        "</head>",
        "<body>",
        body_html,
        "</body></html>",
    ])


def generate_page_html(page: dict, doc: dict, elements: list, use_translated: bool = False) -> str:
    sorted_elements = sorted(elements, key=lambda e: e["reading_order"])
    body_parts = [f"<h1>第 {page['page_number']} 页</h1>"]
    for elem in sorted_elements:
        html = element_to_html(elem, use_translated)
        if html:
            body_parts.append(html)
    body_html = "\n".join(body_parts)
    suffix = " - 译文" if use_translated else ""
    title = f"{doc['original_filename']} - 第 {page['page_number']} 页{suffix}"
    return build_html_document(title, body_html)


def generate_document_html(pages: list, doc: dict, use_translated: bool = False) -> str:
    pages = merge_cross_page_tables(pages)

    first_elem_per_group = {}
    for page in pages:
        for elem in sorted(page["elements"], key=lambda e: e["reading_order"]):
            cpg = elem.get("cross_page_group")
            if cpg is not None and elem["element_type"] == "Table" and cpg not in first_elem_per_group:
                first_elem_per_group[cpg] = elem["id"]

    body_parts = []
    for page in pages:
        page_num = page["page_number"]
        body_parts.append(f"<h1>第 {page_num} 页</h1>")

        elements = sorted(page["elements"], key=lambda e: e["reading_order"])
        skip_groups = page.get("_skip_groups", set())

        for elem in elements:
            cpg = elem.get("cross_page_group")
            if elem["element_type"] == "Table" and cpg in skip_groups and cpg is not None:
                if first_elem_per_group.get(cpg) != elem["id"]:
                    continue
            html = element_to_html(elem, use_translated)
            if html:
                body_parts.append(html)

    body_html = "\n".join(body_parts)
    suffix = " - 译文" if use_translated else " - 解析结果"
    title = f"{doc['original_filename']}{suffix}"
    return build_html_document(title, body_html)


def generate_document_zip_html(pages: list, doc: dict, pages_elements: dict) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for page in pages:
            if page["status"] != "completed":
                continue
            elements = pages_elements.get(page["id"], [])
            if not elements:
                continue
            html_content = generate_page_html(page, doc, elements)
            page_num_str = str(page["page_number"]).zfill(3)
            filename = f"page_{page_num_str}.html"
            zf.writestr(filename, html_content)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()


DEFAULT_TEXT_TYPES = {"Caption", "Footnote", "List-item", "Page-footer", "Page-header",
                        "Section-header", "Text", "Title"}


def generate_page_markdown(page: dict, doc: dict, elements: list, text_types: set | None = None, use_translated: bool = False) -> str:
    text_types = text_types or DEFAULT_TEXT_TYPES
    sorted_elements = sorted(elements, key=lambda e: e["reading_order"])
    suffix = " - 译文" if use_translated else ""
    md_parts = [f"# 第 {page['page_number']} 页{suffix}\n"]

    for elem in sorted_elements:
        etype = elem["element_type"]
        content = elem.get("content", "") or ""
        content_format = elem.get("content_format", "") or ""
        translated_content = elem.get("translated_content", "") or ""

        if use_translated and translated_content.strip():
            content = translated_content

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
                image_description = elem.get("image_description", "") or ""
                if use_translated:
                    translated_desc = elem.get("translated_content", "") or ""
                    if translated_desc.strip():
                        image_description = translated_desc
                if image_description:
                    md_parts.append(f"\n![{image_description}]({content})\n")
                else:
                    md_parts.append(f"\n![Picture]({content})\n")
        elif etype == "Caption":
            md_parts.append(f"*{content}*\n")
        elif etype in text_types:
            if content.strip():
                md_parts.append(f"{content}\n")
        else:
            if content.strip():
                md_parts.append(f"{content}\n")

    return "\n".join(md_parts)


def generate_document_markdown(pages: list, doc: dict, use_translated: bool = False) -> str:
    text_types = DEFAULT_TEXT_TYPES
    pages = merge_cross_page_tables(pages)
    suffix = " - 译文" if use_translated else ""
    md_parts = [f"# {doc['original_filename']}{suffix}\n"]

    first_elem_per_group = {}
    for page in pages:
        for elem in sorted(page["elements"], key=lambda e: e["reading_order"]):
            cpg = elem.get("cross_page_group")
            if cpg is not None and elem["element_type"] == "Table" and cpg not in first_elem_per_group:
                first_elem_per_group[cpg] = elem["id"]

    for page in pages:
        page_num = page["page_number"]
        md_parts.append(f"\n---\n## 第 {page_num} 页\n")

        elements = sorted(page["elements"], key=lambda e: e["reading_order"])
        skip_groups = page.get("_skip_groups", set())

        for elem in elements:
            etype = elem["element_type"]
            content = elem.get("content", "") or ""
            content_format = elem.get("content_format", "") or ""
            translated_content = elem.get("translated_content", "") or ""
            cpg = elem.get("cross_page_group")

            if use_translated and translated_content.strip():
                content = translated_content

            if elem["element_type"] == "Table" and cpg in skip_groups and cpg is not None:
                if first_elem_per_group.get(cpg) != elem["id"]:
                    continue

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
            elif etype in text_types:
                if content.strip():
                    md_parts.append(f"{content}\n")
            else:
                if content.strip():
                    md_parts.append(f"{content}\n")

    return "\n".join(md_parts)


def build_markdown(pages: list[dict]) -> str:
    text_types = DEFAULT_TEXT_TYPES
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
            elif etype in text_types:
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
                    image_description = elem.get("image_description", "") or ""
                    if image_description:
                        parts.append(f"\n![{image_description}]({content})\n")
                    else:
                        parts.append(f"\n![Picture]({content})\n")
            elif etype == "Caption":
                parts.append(f"*{content}*\n")

    return "\n".join(parts)


def generate_rag_single_html(pages: list, doc: dict) -> str:
    filtered_pages = []
    for page in pages:
        filtered_elements = _filter_rag_elements(page.get("elements", []))
        page_copy = dict(page)
        page_copy["elements"] = filtered_elements
        filtered_pages.append(page_copy)

    return generate_document_html(filtered_pages, doc)


def generate_rag_single_page_html(page: dict, doc: dict, elements: list) -> str:
    filtered_elements = _filter_rag_elements(elements)
    return generate_page_html(page, doc, filtered_elements)


def generate_rag_per_page_zip(pages: list, doc: dict, pages_elements: dict) -> bytes:
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for page in pages:
            if page["status"] != "completed":
                continue
            elements = pages_elements.get(page["id"], [])
            if not elements:
                continue
            filtered_elements = _filter_rag_elements(elements)
            if not filtered_elements:
                continue
            html_content = generate_page_html(page, doc, filtered_elements)
            page_num_str = str(page["page_number"]).zfill(3)
            filename = f"page_{page_num_str}.html"
            zf.writestr(filename, html_content)

    zip_buffer.seek(0)
    return zip_buffer.getvalue()
