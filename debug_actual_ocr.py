"""
查看 parse_scanned_page_full 中的 plain_ocr_lines
"""
import sys, os, logging, tempfile, fitz
sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='%(message)s')

from backend.services.pdf_service import convert_page_to_jpg
from backend.services import ocr_service_vl as ocr_service

pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"

pdf_doc = fitz.open(pdf_path)
page = pdf_doc[0]

tmp_dir = tempfile.mkdtemp()
jpg_path, jpg_w, jpg_h = convert_page_to_jpg(page, os.path.join(tmp_dir, "p1.jpg"), 300)

# 和 parse_scanned_page_full 完全一样的调用
ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
plain_ocr_lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]

print(f"共 {len(plain_ocr_lines)} 行:")
for i, l in enumerate(plain_ocr_lines):
    print(f"  [{i:2d}] {l[:100]}")
