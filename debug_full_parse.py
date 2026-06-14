"""
直接测试 parse_scanned_page_full 并查看表格内容
"""
import sys, os, logging, tempfile, fitz
sys.path.insert(0, '.')

logging.basicConfig(level=logging.INFO, format='%(message)s')

from backend.services.pdf_service import convert_page_to_jpg
from backend.services import ocr_service_vl as ocr_service
from backend.services.scanned_parse_service import (
    parse_scanned_page_full, _parse_table_html_to_2d
)

pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"

pdf_doc = fitz.open(pdf_path)
page = pdf_doc[0]

tmp_dir = tempfile.mkdtemp()
jpg_path, jpg_w, jpg_h = convert_page_to_jpg(page, os.path.join(tmp_dir, "p1.jpg"), 300)

print(f"JPG: {jpg_path}, size={jpg_w}x{jpg_h}")

# 先单独调用 OCR，看看 parse_scanned_page_full 的 jpg_path 是否和这个一致
ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]
print(f"\n单独调用 OCR 得到 {len(lines)} 行:")
for i, l in enumerate(lines):
    if any(c.isdigit() and '.' in l for c in l):
        print(f"  [{i:2d}] {l[:100]}")

elements = parse_scanned_page_full(jpg_path, jpg_w, jpg_h)

print(f"\n=== 共 {len(elements)} 个元素 ===")
for ei, e in enumerate(elements):
    etype = e.get('element_type', '?')
    print(f"\n[{ei}] {etype}")
    if etype == 'Table':
        content = e.get('content', '')
        print(f"  HTML len: {len(content)}")
        m = _parse_table_html_to_2d(content)
        for ri, row in enumerate(m):
            print(f"  Row {ri}: {row}")
    else:
        preview = (e.get('content') or '')[:80]
        print(f"  {preview}")
