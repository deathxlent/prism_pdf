import re
import logging
from html import unescape, escape

logger = logging.getLogger(__name__)


def extract_table_plain_text_from_html(html: str) -> str:
    if not html:
        return ""
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&amp;', '&', text)
    text = re.sub(r'&lt;', '<', text)
    text = re.sub(r'&gt;', '>', text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines)


def get_first_data_row_plain(table_plain: str) -> list:
    if not table_plain:
        return []
    lines = [l.strip() for l in table_plain.split('\n') if l.strip()]
    if not lines:
        return []
    first_line = lines[0] if len(lines) > 0 else ""
    return [c.strip() for c in first_line.split() if c.strip()]


def get_last_data_row_plain(table_plain: str) -> list:
    if not table_plain:
        return []
    lines = [l.strip() for l in table_plain.split('\n') if l.strip()]
    if not lines:
        return []
    last_line = lines[-1] if lines else ""
    return [c.strip() for c in last_line.split() if c.strip()]


def is_continuation_table(curr_table_cols: int, curr_first_row: list,
                          prev_table_cols: int, prev_last_row: list) -> bool:
    if curr_table_cols != prev_table_cols:
        return False

    curr_first_col = str(curr_first_row[0]).strip() if curr_first_row and curr_first_row[0] else ""
    prev_last_col = str(prev_last_row[0]).strip() if prev_last_row and prev_last_row[0] else ""

    if not curr_first_col and not prev_last_col:
        return True

    def has_digit(s: str) -> bool:
        return any(c.isdigit() for c in s)

    prev_has_digit = any(has_digit(str(c)) for c in prev_last_row if c)
    curr_has_digit = any(has_digit(str(c)) for c in curr_first_row if c)

    if prev_has_digit and curr_has_digit:
        return True

    return False


def parse_html_table_to_matrix(html: str) -> list[list[dict]]:
    """
    解析 HTML 表格为二维单元格矩阵用于合并操作。
    每个单元格: {content, is_header, rowspan, colspan} 或 None (被覆盖)
    """
    if not html:
        return []
    rows_match = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    if not rows_match:
        return []

    temp_matrix = []
    max_cols = 0
    for row_html in rows_match:
        cells_match = re.findall(r'<(t[dh])[^>]*>(.*?)</\1>', row_html, re.DOTALL | re.IGNORECASE)
        row_cells = []
        for tag, cell_html in cells_match:
            tag = tag.lower()
            is_header = tag == 'th'
            rs_match = re.search(r"rowspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            rowspan = int(rs_match.group(1)) if rs_match else 1
            cs_match = re.search(r"colspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            colspan = int(cs_match.group(1)) if cs_match else 1
            content = re.sub(r'<[^>]+>', '', cell_html).strip()
            content = unescape(content)
            row_cells.append({
                'content': content,
                'is_header': is_header,
                'rowspan': rowspan,
                'colspan': colspan,
            })
        if row_cells:
            temp_matrix.append(row_cells)
            row_col_count = sum(c['colspan'] for c in row_cells)
            max_cols = max(max_cols, row_col_count)

    if not temp_matrix:
        return []

    full_matrix = [[None for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    covered = [[False for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    for ri, row_cells in enumerate(temp_matrix):
        col_pos = 0
        for cell in row_cells:
            while col_pos < max_cols and covered[ri][col_pos]:
                col_pos += 1
            if col_pos >= max_cols:
                break
            full_matrix[ri][col_pos] = {
                'content': cell['content'],
                'is_header': cell['is_header'],
                'rowspan': cell['rowspan'],
                'colspan': cell['colspan'],
            }
            for r in range(ri, min(ri + cell['rowspan'], len(temp_matrix))):
                for c in range(col_pos, min(col_pos + cell['colspan'], max_cols)):
                    if r != ri or c != col_pos:
                        covered[r][c] = True
            col_pos += cell['colspan']
    return full_matrix


def parse_html_table(html: str) -> list[list[dict]]:
    """
    解析 HTML 表格为二维单元格矩阵（带额外 row_idx 信息）。
    与 parse_html_table_to_matrix 类似，但解析时包含 row_idx。
    """
    if not html:
        return []

    rows_match = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL | re.IGNORECASE)
    if not rows_match:
        return []

    temp_matrix = []
    max_cols = 0

    for ri, row_html in enumerate(rows_match):
        cells_match = re.findall(r'<(t[dh])[^>]*>(.*?)</\1>', row_html, re.DOTALL | re.IGNORECASE)
        row_cells = []
        for tag, cell_html in cells_match:
            tag = tag.lower()
            is_header = tag == 'th'
            rs_match = re.search(r"rowspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            rowspan = int(rs_match.group(1)) if rs_match else 1
            cs_match = re.search(r"colspan\s*=\s*['\"]?(\d+)", cell_html, re.IGNORECASE)
            colspan = int(cs_match.group(1)) if cs_match else 1
            content = re.sub(r'<[^>]+>', '', cell_html).strip()
            content = unescape(content)
            row_cells.append({
                'content': content,
                'is_header': is_header,
                'rowspan': rowspan,
                'colspan': colspan,
                'row_idx': ri,
            })
        if row_cells:
            temp_matrix.append(row_cells)
            row_col_count = sum(c['colspan'] for c in row_cells)
            max_cols = max(max_cols, row_col_count)

    if not temp_matrix:
        return []

    full_matrix = [[None for _ in range(max_cols)] for _ in range(len(temp_matrix))]
    covered = [[False for _ in range(max_cols)] for _ in range(len(temp_matrix))]

    for ri, row_cells in enumerate(temp_matrix):
        col_pos = 0
        for cell in row_cells:
            while col_pos < max_cols and covered[ri][col_pos]:
                col_pos += 1
            if col_pos >= max_cols:
                break
            rs = cell['rowspan']
            cs = cell['colspan']
            full_matrix[ri][col_pos] = {
                'content': cell['content'],
                'is_header': cell['is_header'],
                'rowspan': rs,
                'colspan': cs,
            }
            for r in range(ri, min(ri + rs, len(temp_matrix))):
                for c in range(col_pos, min(col_pos + cs, max_cols)):
                    if r != ri or c != col_pos:
                        covered[r][c] = True
            col_pos += cs

    return full_matrix


def matrix_to_html(matrix: list[list[dict]]) -> str:
    """将单元格矩阵转换回 HTML 表格字符串。"""
    if not matrix:
        return ""
    rows = len(matrix)
    cols = len(matrix[0]) if rows > 0 else 0
    if rows == 0 or cols == 0:
        return ""

    covered = [[False for _ in range(cols)] for _ in range(rows)]
    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]
    for ri in range(rows):
        html_parts.append("  <tr>")
        for ci in range(cols):
            if covered[ri][ci]:
                continue
            cell = matrix[ri][ci]
            if cell is None:
                continue
            tag = "th" if cell.get('is_header', False) else "td"
            rowspan = cell.get('rowspan', 1)
            colspan = cell.get('colspan', 1)
            content = escape(cell.get('content', ''))
            attrs = ""
            if rowspan > 1:
                attrs += f" rowspan='{rowspan}'"
            if colspan > 1:
                attrs += f" colspan='{colspan}'"
            html_parts.append(f"    <{tag}{attrs}>{content}</{tag}>")
            for r in range(ri, min(ri + rowspan, rows)):
                for c in range(ci, min(ci + colspan, cols)):
                    if r != ri or c != ci:
                        covered[r][c] = True
        html_parts.append("  </tr>")
    html_parts.append("</table>")
    return "\n".join(html_parts)


def _build_html_from_matrix_with_firstrow_override(
    matrix: list[list[dict]],
    first_row_force_no_header: bool = False
) -> str:
    if not matrix:
        return ""
    rows = len(matrix)
    cols = len(matrix[0])
    covered = [[False for _ in range(cols)] for _ in range(rows)]

    html_parts = ["<table border='1' cellpadding='4' cellspacing='0'>"]
    for ri in range(rows):
        html_parts.append("  <tr>")
        for ci in range(cols):
            if covered[ri][ci]:
                continue
            cell = matrix[ri][ci]
            if cell is None:
                continue
            is_header = cell.get('is_header', False)
            if first_row_force_no_header and ri == 0:
                is_header = False
            rowspan = cell.get('rowspan', 1)
            colspan = cell.get('colspan', 1)
            content = escape(cell.get('content', ''))
            tag = "th" if is_header else "td"
            attrs = ""
            if rowspan > 1:
                attrs += f" rowspan='{rowspan}'"
            if colspan > 1:
                attrs += f" colspan='{colspan}'"
            html_parts.append(f"    <{tag}{attrs}>{content}</{tag}>")
            for r in range(ri, min(ri + rowspan, rows)):
                for c in range(ci, min(ci + colspan, cols)):
                    if r != ri or c != ci:
                        covered[r][c] = True
        html_parts.append("  </tr>")
    html_parts.append("</table>")
    return "\n".join(html_parts)


def merge_cross_page_empty_cells(prev_html: str, curr_html: str) -> tuple[str, str, list]:
    """
    处理跨页表格接续：将当前页表格第一行的空单元格合并到上一页最后一行。
    Returns:
        (updated_prev_html, updated_curr_html, curr_first_row_non_empty_cells)
    """
    if not prev_html or not curr_html:
        return (prev_html, curr_html, [])

    prev_matrix = parse_html_table(prev_html)
    curr_matrix = parse_html_table(curr_html)

    if not prev_matrix or not curr_matrix:
        return (prev_html, curr_html, [])

    prev_rows = len(prev_matrix)
    curr_rows = len(curr_matrix)
    if prev_rows == 0 or curr_rows == 0:
        return (prev_html, curr_html, [])

    max_cols = max(len(prev_matrix[0]), len(curr_matrix[0]))

    curr_first_row = curr_matrix[0]
    prev_last_row = prev_matrix[-1]

    empty_cols_in_first_row = []
    non_empty_cells = []

    for ci in range(min(max_cols, len(curr_first_row))):
        cell = curr_first_row[ci]
        if cell is None:
            continue
        content = cell.get('content', '').strip()
        if not content:
            empty_cols_in_first_row.append(ci)
        else:
            non_empty_cells.append(cell.get('content', ''))

    if not empty_cols_in_first_row:
        return (prev_html, curr_html, non_empty_cells)

    first_non_empty_col = None
    for ci in range(len(curr_first_row)):
        cell = curr_first_row[ci]
        if cell and cell.get('content', '').strip():
            first_non_empty_col = ci
            break

    new_prev_matrix = [row[:] for row in prev_matrix]
    for ci in empty_cols_in_first_row:
        target_ci = ci
        while target_ci >= 0 and prev_last_row[target_ci] is None:
            target_ci -= 1
        if target_ci >= 0 and prev_last_row[target_ci]:
            if new_prev_matrix[-1][target_ci]:
                existing_rs = new_prev_matrix[-1][target_ci].get('rowspan', 1)
                new_prev_matrix[-1][target_ci]['rowspan'] = existing_rs + 1

    if (empty_cols_in_first_row and first_non_empty_col is not None and first_non_empty_col > 0):
        all_covered_by_colspan = True
        for ci in range(1, first_non_empty_col):
            if (ci < len(prev_last_row) and prev_last_row[ci] is not None
                    and prev_last_row[ci].get('content', '').strip()):
                all_covered_by_colspan = False
                break

        if all_covered_by_colspan:
            leftmost_target = None
            for ci in range(first_non_empty_col):
                if ci < len(prev_last_row) and prev_last_row[ci] and prev_last_row[ci].get('content', '').strip():
                    leftmost_target = ci
                    break

            if leftmost_target is None:
                leftmost_target = 0

            if new_prev_matrix[-1][leftmost_target]:
                total_empty_cols = first_non_empty_col - leftmost_target
                existing_cs = new_prev_matrix[-1][leftmost_target].get('colspan', 1)
                new_prev_matrix[-1][leftmost_target]['colspan'] = existing_cs + total_empty_cols

                for ci in range(leftmost_target + 1, first_non_empty_col):
                    if ci < len(new_prev_matrix[-1]):
                        new_prev_matrix[-1][ci] = None

    new_curr_matrix = []
    for ri, row in enumerate(curr_matrix):
        if ri == 0:
            new_row = []
            for ci, cell in enumerate(row):
                if cell is None:
                    new_row.append(None)
                    continue
                if ci in empty_cols_in_first_row:
                    new_row.append(None)
                else:
                    new_row.append(cell.copy() if cell else None)
            new_curr_matrix.append(new_row)
        else:
            new_curr_matrix.append([c.copy() if c else None for c in row])

    new_prev_html = _build_html_from_matrix_with_firstrow_override(new_prev_matrix)
    new_curr_html = _build_html_from_matrix_with_firstrow_override(new_curr_matrix, first_row_force_no_header=True)

    return (new_prev_html, new_curr_html, non_empty_cells)


def build_merged_table(first_html: str, continuation_htmls: list[str]) -> str:
    """
    合并跨页表格，处理空单元格吸收和 colspan/rowspan 更新。
    """
    if not first_html:
        return ""

    acc_matrix = parse_html_table_to_matrix(first_html)
    if not acc_matrix:
        return first_html

    for cont_html in continuation_htmls:
        if not cont_html:
            continue
        cont_matrix = parse_html_table_to_matrix(cont_html)
        if not cont_matrix:
            continue

        acc_cols = len(acc_matrix[0]) if acc_matrix else 0
        cont_cols = len(cont_matrix[0]) if cont_matrix else 0
        max_cols = max(acc_cols, cont_cols)

        for row in acc_matrix:
            while len(row) < max_cols:
                row.append(None)
        for row in cont_matrix:
            while len(row) < max_cols:
                row.append(None)

        first_cont_row = cont_matrix[0]
        empty_cols = []
        for ci in range(max_cols):
            if ci < len(first_cont_row):
                cell = first_cont_row[ci]
                if cell is None:
                    continue
                content = cell.get('content', '').strip()
                if not content:
                    empty_cols.append(ci)

        if empty_cols:
            last_acc_row = acc_matrix[-1]
            for ci in empty_cols:
                target_ci = ci
                while target_ci >= 0 and (target_ci >= len(last_acc_row) or last_acc_row[target_ci] is None):
                    target_ci -= 1
                if target_ci >= 0 and target_ci < len(last_acc_row) and last_acc_row[target_ci] is not None:
                    existing_rs = last_acc_row[target_ci].get('rowspan', 1)
                    last_acc_row[target_ci]['rowspan'] = existing_rs + 1

            first_non_empty_col = None
            for ci in range(max_cols):
                if ci >= len(first_cont_row):
                    break
                cell = first_cont_row[ci]
                if cell and cell.get('content', '').strip():
                    first_non_empty_col = ci
                    break

            if empty_cols and first_non_empty_col is not None and first_non_empty_col > 0:
                all_covered_by_colspan = True
                for ci in range(1, first_non_empty_col):
                    if (ci < len(last_acc_row) and last_acc_row[ci] is not None
                            and last_acc_row[ci].get('content', '').strip()):
                        all_covered_by_colspan = False
                        break

                if all_covered_by_colspan:
                    leftmost_target = None
                    for ci in range(first_non_empty_col):
                        if ci < len(last_acc_row) and last_acc_row[ci] and last_acc_row[ci].get('content', '').strip():
                            leftmost_target = ci
                            break
                    if leftmost_target is None:
                        leftmost_target = 0
                    if leftmost_target < len(last_acc_row) and last_acc_row[leftmost_target]:
                        total_empty_cols = first_non_empty_col - leftmost_target
                        existing_cs = last_acc_row[leftmost_target].get('colspan', 1)
                        last_acc_row[leftmost_target]['colspan'] = existing_cs + total_empty_cols
                        for ci in range(leftmost_target + 1, first_non_empty_col):
                            if ci < len(last_acc_row):
                                last_acc_row[ci] = None

        new_cont_rows = []
        for ri, row in enumerate(cont_matrix):
            if ri == 0:
                new_row = []
                all_absorbed = True
                for ci, cell in enumerate(row):
                    if cell is None:
                        new_row.append(None)
                        continue
                    if ci in empty_cols:
                        new_row.append(None)
                    else:
                        new_row.append(cell.copy() if cell else None)
                        all_absorbed = False
                if not all_absorbed:
                    new_cont_rows.append(new_row)
            else:
                new_cont_rows.append([c.copy() if c else None for c in row])

        if new_cont_rows:
            acc_matrix.extend(new_cont_rows)

    return matrix_to_html(acc_matrix)


def merge_cross_page_tables(pages: list[dict]) -> list[dict]:
    """
    合并跨页表格组，更新首元素的内容为合并后的 HTML，
    同时标记被合并的组以便在导出时跳过非首元素。
    """
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
        merged_html = build_merged_table(first_html, rest_htmls)
        first["content"] = merged_html
        merged_groups.add(group_id)

    for page in pages:
        page["_skip_groups"] = merged_groups

    return pages


def save_ocr_raw_output(jpg_path: str, page_number: int, doc_dir: str):
    try:
        import json
        from datetime import datetime
        ocr_raw_dir = Path(doc_dir) / "ocr_raw_output"
        ocr_raw_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = ocr_raw_dir / f"page_{page_number}_{timestamp}.txt"

        log_content = []
        log_content.append(f"=== OCR Raw Output for Page {page_number} ===")
        log_content.append(f"Timestamp: {datetime.now().isoformat()}")
        log_content.append(f"Image Path: {jpg_path}")
        log_content.append("")

        try:
            from backend.services.ocr_service_vl import _get_last_raw_response
            raw_response = _get_last_raw_response()
            if raw_response:
                log_content.append("--- Llama Server Raw Response ---")
                if isinstance(raw_response, (dict, list)):
                    log_content.append(json.dumps(raw_response, ensure_ascii=False, indent=2))
                else:
                    log_content.append(str(raw_response))
            else:
                log_content.append("(No raw response captured)")
        except Exception as e:
            log_content.append(f"(Failed to get raw response: {e})")

        log_content.append("")
        log_content.append("=== END ===")

        with open(log_file, "w", encoding="utf-8") as f:
            f.write("\n".join(log_content))

        logger.info(f"OCR raw output saved to: {log_file}")
    except Exception as e:
        logger.warning(f"Failed to save OCR raw output for page {page_number}: {e}")


from pathlib import Path
