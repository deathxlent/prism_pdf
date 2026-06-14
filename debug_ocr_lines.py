"""
调试: 看看 supplementary OCR 的纯文本到底是什么样的
"""
import sys
sys.path.insert(0, '.')

from backend.services.pdf_service import convert_page_to_jpg
from backend.services import ocr_service_vl as ocr_service
import fitz

pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"

doc = fitz.open(pdf_path)
page = doc[0]
import tempfile, os
tmp_dir = tempfile.mkdtemp()
jpg_path, w, h = convert_page_to_jpg(page, os.path.join(tmp_dir, "p1.jpg"), 300)

print(f"JPG: {jpg_path}")

ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]

print(f"\n共 {len(lines)} 行:")
for i, l in enumerate(lines):
    print(f"  [{i:2d}] {l[:100]}")
