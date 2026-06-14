"""
测试扫描版 PDF 直接解析流程
===========================

直接调用新的 scanned_parse_service 解析 tmp/table-t1images.pdf，
然后与数据库中 id=10 的基准结果（tables-t1.pdf 原生版）进行对比。
"""
import sys
import os
import asyncio
import difflib
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fitz
from PIL import Image
from backend.services.scanned_parse_service import parse_scanned_page_full
from backend.services.pdf_service import jpg_bbox_to_pdf_bbox, DEFAULT_DPI, convert_page_to_jpg
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.db")


def normalize_text(s: str) -> str:
    """标准化文本：去掉多余空格、全角半角差异，便于比较"""
    if not s:
        return ""
    s = s.replace('\u3000', ' ')  # 全角空格
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def extract_table_cells_from_html(html: str) -> list[list[str]]:
    """从表格 HTML 中提取纯文本单元格（2D 列表）"""
    cells_2d = []
    if not html:
        return cells_2d

    from html.parser import HTMLParser

    class TableParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_td = False
            self.current_row = []
            self.current_cell = ""
            self.rows = []

        def handle_starttag(self, tag, attrs):
            if tag in ('td', 'th'):
                self.in_td = True
                self.current_cell = ""
                # 处理 rowspan
                rowspan = 1
                for name, val in attrs:
                    if name == 'rowspan':
                        try:
                            rowspan = int(val)
                        except:
                            pass
                self._rowspan = rowspan
                # 处理 colspan
                colspan = 1
                for name, val in attrs:
                    if name == 'colspan':
                        try:
                            colspan = int(val)
                        except:
                            pass
                self._colspan = colspan
            elif tag == 'tr':
                self.current_row = []

        def handle_endtag(self, tag):
            if tag in ('td', 'th'):
                self.in_td = False
                cell = normalize_text(self.current_cell)
                # colspan 扩展
                for _ in range(self._colspan):
                    self.current_row.append(cell)
                # rowspan 会在处理下一行时补偿，这里简化处理
            elif tag == 'tr':
                if self.current_row:
                    self.rows.append(list(self.current_row))

        def handle_data(self, data):
            if self.in_td:
                self.current_cell += data

    parser = TableParser()
    try:
        parser.feed(html)
    except Exception:
        pass
    return parser.rows


def cells_to_str(cells_2d: list[list[str]]) -> str:
    """将 2D 单元格列表转为可读字符串，便于 diff"""
    lines = []
    for r in cells_2d:
        lines.append(" | ".join(c or '(空)' for c in r))
    return "\n".join(lines)


def get_doc10_baseline():
    """从数据库获取 id=10 的基准数据"""
    print("\n" + "=" * 80)
    print("获取文档 id=10 (tables-t1.pdf) 基准结果...")
    print("=" * 80)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("SELECT * FROM pdf_documents WHERE id = ?", (10,))
    doc_row = cur.fetchone()
    doc = dict(doc_row) if doc_row else None
    print(f"\n[文档] id=10: {doc['filename']}, 状态={doc['status']}")
    print(f"       is_encrypted={doc.get('is_encrypted')}, 页数={doc.get('page_count')}")

    cur.execute("SELECT * FROM pdf_pages WHERE document_id = ? ORDER BY page_number", (10,))
    pages = cur.fetchall()
    pages_list = [dict(p) for p in pages]
    print(f"[页面] 共 {len(pages_list)} 页")

    all_elements = []
    for page in pages_list:
        cur.execute(
            "SELECT * FROM page_elements WHERE page_id = ? ORDER BY reading_order, bbox_y0",
            (page["id"],)
        )
        elems = cur.fetchall()
        elems_list = [dict(e) for e in elems]
        print(f"\n  第 {page['page_number']} 页: {len(elems_list)} 个元素")
        for e in elems_list:
            etype = e["element_type"]
            bbox_str = f"({e['bbox_x0']:.0f},{e['bbox_y0']:.0f})-({e['bbox_x1']:.0f},{e['bbox_y1']:.0f})"
            content_preview = (e.get('content') or '')[:60].replace('\n', '\\n')
            extra = ""
            if etype == "Table":
                extra = f", 表格 {e.get('table_rows')}x{e.get('table_cols')}"
                cells = extract_table_cells_from_html(e.get('table_html') or e.get('content') or '')
                extra += f", 实际解析行数={len(cells)}"
            print(f"    [{etype:15s}] ro={e['reading_order']:2d} {bbox_str} {extra}")
            print(f"      内容: {content_preview}...")
            elem_dict = {
                "page_number": page["page_number"],
                "element_type": etype,
                "bbox": (e["bbox_x0"], e["bbox_y0"], e["bbox_x1"], e["bbox_y1"]),
                "confidence": e["confidence"],
                "reading_order": e["reading_order"],
                "content": e.get("content") or "",
                "content_format": e.get("content_format") or "markdown",
                "table_html": e.get("table_html"),
                "table_plain": e.get("table_plain"),
                "table_rows": e.get("table_rows"),
                "table_cols": e.get("table_cols"),
            }
            all_elements.append(elem_dict)

    conn.close()
    return dict(doc) if doc else None, pages_list, all_elements


def run_scanned_parse_test():
    """对 tmp/table-t1images.pdf 执行扫描版直接解析"""
    pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"
    work_dir = r"g:\ws\Prism PDF\tmp\scanned_parse_test"
    os.makedirs(work_dir, exist_ok=True)

    print("\n" + "=" * 80)
    print("步骤1: 转 JPG (300dpi - 提高清晰度，表格列更多更清晰)")
    print("=" * 80)
    jpg_paths = []
    os.makedirs(work_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        jpg_path = os.path.join(work_dir, f"page_{i+1}.jpg")
        convert_page_to_jpg(page, jpg_path, dpi=300)
        jpg_paths.append(jpg_path)
    doc.close()
    print(f"转换成功，共 {len(jpg_paths)} 张图片")

    # 获取 PDF 页面尺寸（用于后续坐标转换）
    pdf_doc = fitz.open(pdf_path)
    pdf_page = pdf_doc[0]

    # 取第一页测试（与 id=10 一样，1 页）
    jpg_path = jpg_paths[0]
    with Image.open(jpg_path) as im:
        jpg_w, jpg_h = im.size
    print(f"图片尺寸: {jpg_w}x{jpg_h} px")

    print("\n" + "=" * 80)
    print("步骤2: 调用 scanned_parse_service.parse_scanned_page_full (整页 Table Recognition)")
    print("=" * 80)

    elements = parse_scanned_page_full(jpg_path, jpg_w, jpg_h)

    print(f"\n解析完成，共生成 {len(elements)} 个元素:")
    print(f"{'类型':15s} {'ro':>3s}  {'bbox (jpg coords)':28s}  内容预览")
    print("-" * 80)

    for e in elements:
        etype = e["element_type"]
        ro = e.get("reading_order", 0)
        bbox = e["bbox"]
        bbox_str = f"({bbox[0]:.0f},{bbox[1]:.0f})-({bbox[2]:.0f},{bbox[3]:.0f})"
        content = e.get("content") or ""
        preview = content[:80].replace("\n", "\\n")
        extra = ""
        if etype == "Table":
            cells = extract_table_cells_from_html(content)
            extra = f" [Table: {len(cells)} 行, {e.get('table_cols', '?')} 列]"
        print(f"{etype:15s} {ro:3d}  {bbox_str:28s}  {preview}...{extra}")

    pdf_doc.close()
    return elements, jpg_path, pdf_page


def compare_results(baseline_elements, test_elements):
    """对比基准结果和测试结果"""
    print("\n" + "=" * 80)
    print("步骤3: 对比 id=10 基准 vs 扫描版解析结果")
    print("=" * 80)

    # --- 1. 统计对比 ---
    def count_types(elems):
        from collections import Counter
        return Counter(e["element_type"] for e in elems)

    base_counts = count_types(baseline_elements)
    test_counts = count_types(test_elements)

    print("\n【元素类型数量对比】")
    all_types = sorted(set(list(base_counts.keys()) + list(test_counts.keys())))
    print(f"{'类型':15s}  {'id=10基准':>6s}  {'扫描版测试':>8s}  {'差异':>6s}")
    print("-" * 45)
    for t in all_types:
        b = base_counts.get(t, 0)
        tst = test_counts.get(t, 0)
        diff = tst - b
        diff_str = f"{'+' if diff > 0 else ''}{diff}" if diff != 0 else ""
        mark = " ***" if abs(diff) > 0 else ""
        print(f"{t:15s}  {b:6d}  {tst:8d}  {diff_str:>6s}{mark}")

    # --- 2. 表格详细对比 ---
    print("\n【表格详细对比】")
    base_tables = [e for e in baseline_elements if e["element_type"] == "Table"]
    test_tables = [e for e in test_elements if e["element_type"] == "Table"]

    print(f"  id=10 基准表格数: {len(base_tables)}")
    print(f"  扫描版解析表格数: {len(test_tables)}")

    for i, (bt, tt) in enumerate(zip(base_tables, test_tables)):
        print(f"\n  --- 表格 {i+1} 对比 ---")

        b_html = bt.get("table_html") or bt.get("content") or ""
        t_html = tt.get("content") or ""

        b_cells = extract_table_cells_from_html(b_html)
        t_cells = extract_table_cells_from_html(t_html)

        print(f"    基准尺寸: {bt.get('table_rows')}x{bt.get('table_cols')}  (解析 {len(b_cells)} 行, 每行最大 {max((len(r) for r in b_cells), default=0)} 列)")
        print(f"    测试尺寸: {tt.get('table_rows', '?')}x{tt.get('table_cols', '?')}  (解析 {len(t_cells)} 行, 每行最大 {max((len(r) for r in t_cells), default=0)} 列)")

        b_str = cells_to_str(b_cells)
        t_str = cells_to_str(t_cells)

        print(f"\n    基准表格内容:")
        for line in b_str.split("\n"):
            print(f"      {line}")
        print(f"\n    测试表格内容:")
        for line in t_str.split("\n"):
            print(f"      {line}")

        if b_str and t_str:
            # 单元格级别相似度
            all_b = [normalize_text(c) for row in b_cells for c in row]
            all_t = [normalize_text(c) for row in t_cells for c in row]
            match_count = 0
            for bc in all_b:
                if not bc:
                    continue
                for tc in all_t:
                    if bc == tc or (bc and tc and difflib.SequenceMatcher(None, bc, tc).ratio() > 0.9):
                        match_count += 1
                        break
            non_empty_b = [x for x in all_b if x]
            sim = match_count / len(non_empty_b) if non_empty_b else 0
            print(f"\n    单元格内容相似度: {sim:.1%} ({match_count}/{len(non_empty_b)} 非空单元格匹配)")

            if sim < 0.9:
                print("\n    详细差异:")
                diff = list(difflib.unified_diff(
                    b_str.splitlines(keepends=True),
                    t_str.splitlines(keepends=True),
                    fromfile="id=10 基准",
                    tofile="扫描版测试",
                    lineterm=""
                ))
                for d in diff[:50]:
                    print(f"      {d}")

    # --- 3. 文本内容整体对比（按 reading_order 拼接） ---
    print("\n【整体文本内容相似度】")

    def concat_texts(elems):
        parts = []
        for e in sorted(elems, key=lambda x: x.get("reading_order", 0)):
            et = e["element_type"]
            c = e.get("content") or ""
            if et == "Table":
                cells = extract_table_cells_from_html(c)
                parts.append(cells_to_str(cells))
            else:
                parts.append(c)
        return normalize_text("\n".join(parts))

    base_full = concat_texts(baseline_elements)
    test_full = concat_texts(test_elements)

    sim = difflib.SequenceMatcher(None, base_full, test_full).ratio()
    print(f"  整体内容相似度: {sim:.1%}")
    print(f"  基准文本长度: {len(base_full)} 字符")
    print(f"  测试文本长度: {len(test_full)} 字符")

    if sim < 0.85:
        print("\n  文本内容 diff (前 80 行差异):")
        diff = list(difflib.unified_diff(
            base_full.splitlines(keepends=True),
            test_full.splitlines(keepends=True),
            fromfile="id=10 基准",
            tofile="扫描版测试",
            lineterm=""
        ))
        for d in diff[:80]:
            print(f"  {d}")

    return sim


def main():
    print("=" * 80)
    print("扫描版 PDF 直接解析 测试")
    print("=" * 80)

    # 1. 获取基准结果
    doc10, pages10, base_elems = get_doc10_baseline()

    # 2. 执行扫描版解析测试
    test_elems, jpg_path, pdf_page = run_scanned_parse_test()

    # 3. 对比
    compare_results(base_elems, test_elems)

    # 4. 保存详细结果
    output_dir = r"g:\ws\Prism PDF\tmp\scanned_parse_test"
    report_path = os.path.join(output_dir, "comparison_report.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=== 扫描版解析 对比报告 ===\n\n")
        f.write(f"基准文档: id=10 ({doc10['filename']}, 原生 PDF)\n")
        f.write(f"测试文档: table-t1images.pdf (扫描版)\n\n")

        f.write("--- 基准元素 ---\n")
        for e in base_elems:
            f.write(f"[{e['element_type']}] ro={e['reading_order']} {e['bbox']}\n")
            if e["element_type"] == "Table":
                cells = extract_table_cells_from_html(e.get("table_html") or e.get("content") or "")
                f.write(cells_to_str(cells) + "\n")
            else:
                f.write((e.get("content") or "")[:500] + "\n")
            f.write("-" * 60 + "\n")

        f.write("\n--- 扫描版测试元素 ---\n")
        for e in test_elems:
            bbox_pdf = jpg_bbox_to_pdf_bbox(e["bbox"], DEFAULT_DPI)
            f.write(f"[{e['element_type']}] ro={e.get('reading_order')} jpg_bbox={e['bbox']} pdf_bbox={tuple(round(x,1) for x in bbox_pdf)}\n")
            if e["element_type"] == "Table":
                cells = extract_table_cells_from_html(e.get("content") or "")
                f.write(cells_to_str(cells) + "\n")
            else:
                f.write((e.get("content") or "")[:500] + "\n")
            f.write("-" * 60 + "\n")

    print(f"\n详细对比报告已保存至: {report_path}")


if __name__ == "__main__":
    main()
