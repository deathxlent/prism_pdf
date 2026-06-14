import fitz
import os
import re
import unicodedata
from pathlib import Path
from backend.config import TMP_DIR, SCAN_TEXT_THRESHOLD, SCAN_IMAGE_AREA_RATIO, GARBLE_CJK_THRESHOLD

DEFAULT_DPI = 200
PDF_DPI = 72


def jpg_bbox_to_pdf_bbox(bbox: tuple[float, float, float, float], dpi: int = DEFAULT_DPI) -> tuple[float, float, float, float]:
    scale = PDF_DPI / dpi
    return (
        bbox[0] * scale,
        bbox[1] * scale,
        bbox[2] * scale,
        bbox[3] * scale,
    )


def validate_pdf(file_path: str) -> dict:
    result = {"valid": False, "encrypted": False, "page_count": 0, "error": None}
    try:
        doc = fitz.open(file_path)
        if doc.is_encrypted:
            try:
                doc.authenticate("")
            except Exception:
                pass
            if doc.is_encrypted:
                result["encrypted"] = True
                result["error"] = "PDF is encrypted and cannot be opened"
                doc.close()
                return result
        result["page_count"] = len(doc)
        result["valid"] = True
        doc.close()
    except fitz.FileDataError as e:
        result["error"] = f"Invalid PDF file: {e}"
    except Exception as e:
        result["error"] = f"Error opening PDF: {e}"
    return result


def is_page_scanned(page: fitz.Page) -> bool:
    text = page.get_text("text").strip()
    if len(text) < SCAN_TEXT_THRESHOLD:
        images = page.get_images(full=True)
        if len(images) == 1 and len(text) == 0:
            page_area = page.rect.width * page.rect.height
            try:
                img_info = page.get_image_info(hashes=False)
                if len(img_info) == 1:
                    bbox = img_info[0]["bbox"]
                    img_area = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])
                    ratio = img_area / page_area if page_area > 0 else 0
                    if ratio >= SCAN_IMAGE_AREA_RATIO:
                        return True
            except Exception:
                pass
        return len(text) < SCAN_TEXT_THRESHOLD
    return False


def detect_garbled_text(text: str) -> dict:
    result = {
        "is_garbled": False,
        "garble_ratio": 0.0,
        "total_cjk": 0,
        "garbled_cjk": 0,
    }

    if not text:
        return result

    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]')
    garbled_chars = []

    for ch in text:
        if cjk_pattern.match(ch):
            result["total_cjk"] += 1
            if ord(ch) in (0xfffd, 0x25a1) or (0x0000 <= ord(ch) <= 0x001f) or (0x007f <= ord(ch) <= 0x009f):
                result["garbled_cjk"] += 1
                garbled_chars.append(ch)
            elif unicodedata.category(ch).startswith('C') and ch not in '\t\n\r':
                result["garbled_cjk"] += 1
                garbled_chars.append(ch)

    if result["total_cjk"] > 0:
        result["garble_ratio"] = result["garbled_cjk"] / result["total_cjk"]

    if result["garble_ratio"] >= GARBLE_CJK_THRESHOLD:
        result["is_garbled"] = True

    return result


def convert_page_to_jpg(page: fitz.Page, output_path: str, dpi: int = 200) -> tuple[str, int, int]:
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat)
    pix.save(output_path)
    return output_path, pix.width, pix.height


def save_single_page_pdf(doc: fitz.Document, page_idx: int, output_path: str) -> str:
    single_doc = fitz.open()
    single_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
    single_doc.save(output_path)
    single_doc.close()
    return output_path


def extract_text_in_region(page: fitz.Page, bbox: tuple[float, float, float, float],
                           bbox_is_jpg: bool = True, dpi: int = DEFAULT_DPI) -> str:
    if bbox_is_jpg:
        bbox = jpg_bbox_to_pdf_bbox(bbox, dpi)
    rect = fitz.Rect(bbox)
    if rect.is_empty or not rect.is_valid:
        return ""
    text_dict = page.get_text("dict", clip=rect)
    lines = []
    for block in text_dict.get("blocks", []):
        if block["type"] == 0:
            for line in block.get("lines", []):
                line_text = ""
                for span in line.get("spans", []):
                    line_text += span.get("text", "")
                if line_text.strip():
                    lines.append(line_text.strip())
    return "\n".join(lines)


def prepare_pages(file_path: str, doc_dir: str) -> list[dict]:
    doc = fitz.open(file_path)
    pages_info = []
    doc_dir_path = Path(doc_dir)
    doc_dir_path.mkdir(parents=True, exist_ok=True)

    for i in range(len(doc)):
        page = doc[i]
        rect = page.rect
        width, height = rect.width, rect.height

        jpg_path = str(doc_dir_path / f"page_{i + 1}.jpg")
        single_pdf_path = str(doc_dir_path / f"page_{i + 1}.pdf")

        _, jpg_width, jpg_height = convert_page_to_jpg(page, jpg_path)
        save_single_page_pdf(doc, i, single_pdf_path)

        scanned = is_page_scanned(page)

        pages_info.append({
            "page_number": i + 1,
            "width": width,
            "height": height,
            "jpg_width": jpg_width,
            "jpg_height": jpg_height,
            "is_scanned": scanned,
            "jpg_path": jpg_path,
            "single_pdf_path": single_pdf_path,
        })

    doc.close()
    return pages_info


def clip_region_as_image(page: fitz.Page, bbox: tuple[float, float, float, float],
                         output_path: str, bbox_is_jpg: bool = True, dpi: int = DEFAULT_DPI) -> str:
    if bbox_is_jpg:
        bbox = jpg_bbox_to_pdf_bbox(bbox, dpi)
    rect = fitz.Rect(bbox)
    if rect.is_empty or not rect.is_valid:
        return ""
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, clip=rect)
    pix.save(output_path)
    return output_path
