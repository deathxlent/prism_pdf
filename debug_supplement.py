"""
调试 supplement 函数调用
"""
import sys
sys.path.insert(0, '.')

from backend.services.pdf_service import convert_page_to_jpg
from backend.services import ocr_service_vl as ocr_service
from backend.services.scanned_parse_service import (
    _supplement_table_missing_columns, _parse_table_html_to_2d
)
import fitz, logging, os, tempfile

logging.basicConfig(level=logging.INFO, format='%(message)s')

pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"

doc = fitz.open(pdf_path)
page = doc[0]
tmp_dir = tempfile.mkdtemp()
jpg_path, w, h = convert_page_to_jpg(page, os.path.join(tmp_dir, "p1.jpg"), 300)

# 做 OCR
ocr_plain = ocr_service._call_llama_server("OCR:", jpg_path, max_tokens=8000)
plain_ocr_lines = [l.strip() for l in ocr_plain.split('\n') if l.strip()]
print(f"OCR plain: {len(plain_ocr_lines)} lines")
for i, l in enumerate(plain_ocr_lines):
    print(f"  [{i:2d}] {l[:90]}")

# 模拟第 9 个元素（Table 2）
elem = {
    'type': 'Table',
    'content': '<table border="1" cellpadding="4" cellspacing="0">\n'
        '  <tr>\n    <th>所属干线</th>\n    <th>公路名称</th>\n    <th>公路起止</th>\n    <th>路产属性</th>\n    <th>收费年限</th>\n  </tr>\n'
        '  <tr>\n    <td>G75 兰海高速</td>\n    <td>覃遵公路</td>\n    <td>起自桐梓县松坎镇, 止于红花岗区中庄镇</td>\n    <td>收费还贷</td>\n    <td>2005-2035</td>\n  </tr>\n'
        '  <tr>\n    <td>覃遵公路（不含扎南）</td>\n    <td></td>\n    <td>起自贵阳市老客车站, 止于红花岗区中庄镇</td>\n    <td>收费还贷</td>\n    <td>2007-2035</td>\n  </tr>\n'
        '  <tr>\n    <td>扎南公路</td>\n    <td></td>\n    <td>起自贵阳市扎佐, 止于遵义县南白镇</td>\n    <td>收费还贷</td>\n    <td>2007-2035</td>\n  </tr>\n'
        '  <tr>\n    <td>贵阳东北绕城公路</td>\n    <td></td>\n    <td>起自罗子林, 止于尖坡</td>\n    <td>收费还贷</td>\n    <td>1998-2024</td>\n  </tr>\n'
        '  <tr>\n    <td>贵新公路</td>\n    <td></td>\n    <td>起自小碧乡下坝, 止于独山县麻尾镇</td>\n    <td>收费还贷</td>\n    <td>2000-2021</td>\n  </tr>\n'
        '</table>\n'
}

# 前面有 Caption + Text
prev_elems = [
    {'element_type': 'Caption', 'content': '表 5-10: 发行人 2017 年 3 月末主要公路资产统计表'},
    {'element_type': 'Text', 'content': '（单位：公里）'},
]
# 把 elem 也改成 element_type
elem['element_type'] = elem.pop('type')
elements = prev_elems + [elem]

print("\n--- 调用 _supplement_table_missing_columns ---")
new_elements = _supplement_table_missing_columns(elements, plain_ocr_lines)

print(f"\n返回元素数: {len(new_elements)}")
for ei, e in enumerate(new_elements):
    if e.get('element_type') == 'Table':
        print(f"\n[Table #{ei}]")
        m = _parse_table_html_to_2d(e['content'])
        for row in m:
            print("  | ".join(str(c) for c in row))
