"""
调试为什么关键词不匹配
"""
import sys, os, logging, tempfile, fitz, re
sys.path.insert(0, '.')

logging.basicConfig(level=logging.WARNING, format='%(message)s')

from backend.services.pdf_service import convert_page_to_jpg
from backend.services import ocr_service_vl as ocr_service
from backend.services.scanned_parse_service import (
    parse_scanned_page_full, _parse_table_html_to_2d, _supplement_table_missing_columns
)

pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"

pdf_doc = fitz.open(pdf_path)
page = pdf_doc[0]

tmp_dir = tempfile.mkdtemp()
jpg_path, jpg_w, jpg_h = convert_page_to_jpg(page, os.path.join(tmp_dir, "p1.jpg"), 300)

# 先调用 OCR
ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
plain_ocr_lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]

print(f"OCR 共 {len(plain_ocr_lines)} 行:")
for i, l in enumerate(plain_ocr_lines):
    print(f"  [{i:2d}] {l[:120]}")

# 调用 parse_scanned_page_full 拿到元素
elements = parse_scanned_page_full(jpg_path, jpg_w, jpg_h)

# 找到表格元素
for ei, e in enumerate(elements):
    if e.get('element_type') == 'Table':
        table_2d, has_header = _parse_table_html_to_2d(e.get('content', ''))
        # 只看数据行数 >= 5 的表格（公路资产表）
        n_rows = len(table_2d) - (1 if has_header else 0)
        if n_rows >= 4:
            print(f"\n=== 表格 #{ei} ({n_rows}数据行, header={has_header}) ===")
            for ri, row in enumerate(table_2d):
                print(f"  行{ri}: {row}")

            # 模拟 _supplement_table_missing_columns 中的关键词提取
            data_rows_start = 1 if has_header else 0
            n_data_rows = len(table_2d) - data_rows_start
            print(f"\n数据行数: {n_data_rows}")

            def _norm(s):
                return re.sub(r'[\s：:（）()、,，.。\-—]', '', s)

            for ri in range(data_rows_start, min(data_rows_start + n_data_rows, len(table_2d))):
                row = table_2d[ri]
                kws = []
                for cell in row:
                    if not cell or not isinstance(cell, str):
                        continue
                    c = cell.strip()
                    if not c or re.match(r'^[\d\.\-%—\-\s]+$', c):
                        continue
                    words = re.findall(r'[\u4e00-\u9fa5A-Za-z0-9]{2,}', c)
                    for w in words:
                        if w not in ('收费还贷', '起自', '止于', '公路', '高速'):
                            kws.append(w)
                seen = set()
                uniq_kws = []
                for k in kws:
                    if k not in seen:
                        seen.add(k)
                        uniq_kws.append(k)
                uniq_kws = uniq_kws[:6]

                print(f"\n数据行 {ri}: 关键词 = {uniq_kws}")
                # 在 OCR 中测试匹配
                for li, ocr_line in enumerate(plain_ocr_lines):
                    ocr_norm = _norm(ocr_line)
                    if not ocr_norm:
                        continue
                    score = 0
                    matched = []
                    for kw in uniq_kws:
                        if _norm(kw) in ocr_norm:
                            score += len(kw)
                            matched.append(kw)
                    if score >= 2:
                        # 必须有数字
                        nums = re.findall(r'\b\d+\.\d+\b', ocr_line)
                        nums_in_range = [float(n) for n in nums if 5.0 <= float(n) <= 300.0]
                        if 1 <= len(nums_in_range) <= 3:
                            print(f"  -> OCR行[{li}] score={score}, matched={matched}, nums={nums_in_range}: {ocr_line[:80]}")
            break
