import logging
import os
import tempfile
import base64
import json
import re
import urllib.request
from pathlib import Path
from PIL import Image

logger = logging.getLogger(__name__)

LLAMA_SERVER_URL = "http://127.0.0.1:8080"
LLAMA_MODEL_NAME = "PaddleOCR-VL-1.6.Q4_K_M.gguf"
DEFAULT_TIMEOUT = 180


def _encode_image(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')


def _call_llama_server(prompt: str, image_path: str, max_tokens: int = 800) -> str:
    base64_image = _encode_image(image_path)

    url = f"{LLAMA_SERVER_URL}/v1/chat/completions"
    headers = {"Content-Type": "application/json"}

    payload = {
        "model": LLAMA_MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}},
                    {"type": "text", "text": prompt}
                ]
            }
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        result = json.loads(resp.read().decode('utf-8'))

    if 'choices' in result and len(result['choices']) > 0:
        return result['choices'][0]['message']['content']
    return ""


def _crop_and_save_image(image_path: str, bbox: tuple = None) -> str:
    img = Image.open(image_path)

    if bbox is not None:
        x0, y0, x1, y1 = [int(v) for v in bbox]
        x0 = max(0, x0)
        y0 = max(0, y0)
        x1 = min(img.width, x1)
        y1 = min(img.height, y1)
        if x1 <= x0 or y1 <= y0:
            return ""
        img = img.crop((x0, y0, x1, y1))

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_path = tmp.name
    img.save(tmp_path, "PNG")
    tmp.close()

    return tmp_path


def _parse_fcel_to_text(text: str) -> str:
    if '<fcel>' not in text:
        return text.strip()

    lines = []
    rows_raw = re.split(r'<nl>', text)

    for row_text in rows_raw:
        row_text = row_text.strip()
        if not row_text:
            continue

        if row_text.startswith('<ucel>'):
            row_text = row_text[len('<ucel>'):]

        cells = []
        remaining = row_text
        while '<fcel>' in remaining:
            _, after = remaining.split('<fcel>', 1)
            next_pos = len(after)
            for tag in ['<fcel>', '<lcel>']:
                pos = after.find(tag)
                if pos >= 0 and pos < next_pos:
                    next_pos = pos
            content = after[:next_pos].strip()
            cells.append(content)
            remaining = after[next_pos:]

        non_empty = [c for c in cells if c and not c.startswith('<')]

        if len(non_empty) == 1 and '<lcel>' in row_text:
            lines.append(non_empty[0])
        elif non_empty:
            lines.append(' '.join(non_empty))

    return '\n'.join(lines)


def _parse_fcel_structured_to_html(text: str) -> tuple[str, int, int]:
    if '<fcel>' not in text:
        return text, 0, 0

    parts = text.split('<nl>')
    rows = []
    for part in parts:
        part = part.strip()
        if not part:
            continue

        is_ucel = part.startswith('<ucel>')
        if is_ucel:
            part = part[len('<ucel>'):]

        cells = []
        remaining = part
        while '<fcel>' in remaining:
            _, after = remaining.split('<fcel>', 1)
            next_pos = len(after)
            for tag in ['<fcel>', '<lcel>']:
                pos = after.find(tag)
                if pos >= 0 and pos < next_pos:
                    next_pos = pos
            content = after[:next_pos].strip()
            cells.append(content)
            remaining = after[next_pos:]

        has_lcel = '<lcel>' in part
        non_empty = [c for c in cells if c and not c.startswith('<')]
        is_table_row = len(non_empty) >= 2 and not (has_lcel and len(non_empty) == 1)

        rows.append({
            'cells': cells,
            'is_ucel': is_ucel,
            'is_table_row': is_table_row,
        })

    table_groups = []
    current = []
    for r in rows:
        if r['is_table_row']:
            current.append(r)
        else:
            if len(current) >= 2:
                table_groups.append(current)
            current = []
    if len(current) >= 2:
        table_groups.append(current)

    if not table_groups:
        return _parse_fcel_to_text(text), 0, 0

    max_cols = max(len(r['cells']) for g in table_groups for r in g)
    total_rows = sum(len(g) for g in table_groups)

    from html import escape
    out_parts = []
    row_idx = 0
    while row_idx < len(rows):
        r = rows[row_idx]
        if not r['is_table_row']:
            text_content = r['cells'][0] if r['cells'] else ''
            out_parts.append(f"<p>{escape(text_content)}</p>")
            row_idx += 1
            continue

        group = []
        gj = row_idx
        while gj < len(rows) and rows[gj]['is_table_row']:
            group.append(rows[gj])
            gj += 1

        if len(group) >= 2:
            group_cols = max(len(r['cells']) for r in group)
            html = "<table border='1' cellpadding='4' cellspacing='0'>\n"

            rowspan0 = 1
            if len(group) >= 2:
                span = 0
                for kg in range(2, len(group)):
                    if group[kg]['is_ucel']:
                        span += 1
                    else:
                        break
                if span > 0:
                    rowspan0 = 1 + span

            for gi, gr in enumerate(group):
                cells = list(gr['cells'])
                is_ucel = gr['is_ucel']
                is_header = (gi == 0)

                while len(cells) < group_cols:
                    cells.append('')

                html += '<tr>'
                for ci in range(group_cols):
                    if is_header:
                        html += f"<th>{escape(cells[ci])}</th>"
                    elif is_ucel:
                        if ci == 0:
                            html += '<td></td>'
                        else:
                            cell_idx = ci - 1
                            content = cells[cell_idx] if cell_idx < len(cells) else ''
                            html += f"<td>{escape(content)}</td>"
                    else:
                        if ci == 0 and gi > 0 and rowspan0 > 1:
                            html += f"<td rowspan='{rowspan0}'>{escape(cells[0])}</td>"
                        else:
                            content = cells[ci] if ci < len(cells) else ''
                            tag = "th" if is_header else "td"
                            html += f"<{tag}>{escape(content)}</{tag}>"
                html += '</tr>\n'

            html += '</table>'
            out_parts.append(html)
            row_idx = gj
        else:
            text_content = group[0]['cells'][0] if group[0]['cells'] else ''
            out_parts.append(f"<p>{escape(text_content)}</p>")
            row_idx += 1

    return '\n'.join(out_parts), total_rows, max_cols


def ocr_region(image_path: str, bbox: tuple[float, float, float, float] = None) -> str:
    tmp_path = _crop_and_save_image(image_path, bbox)
    if not tmp_path:
        return ""

    try:
        raw_output = _call_llama_server("OCR:", tmp_path, max_tokens=500)
        return _parse_fcel_to_text(raw_output)
    except Exception as e:
        logger.error(f"VL OCR failed: {e}")
        return ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def ocr_formula(image_path: str, bbox: tuple[float, float, float, float] = None) -> str:
    tmp_path = _crop_and_save_image(image_path, bbox)
    if not tmp_path:
        return ""

    try:
        raw_output = _call_llama_server("OCR:", tmp_path, max_tokens=300)
        latex = _parse_fcel_to_text(raw_output)
        latex = " ".join([t for t in latex.split("\n") if t.strip()])
        if latex and not latex.startswith("$"):
            latex = f"${latex}$"
        return latex
    except Exception as e:
        logger.error(f"VL Formula OCR failed: {e}")
        return ""
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def ocr_batch(image_path: str, bboxes: list[tuple]) -> list[str]:
    if not bboxes:
        return []

    results = []
    for bbox in bboxes:
        try:
            text = ocr_region(image_path, bbox)
            results.append(text)
        except Exception as e:
            logger.error(f"Batch VL OCR failed for a region: {e}")
            results.append("")

    return results


def ocr_batch_multi_image(image_bbox_pairs: list[tuple[str, tuple]]) -> list[str]:
    if not image_bbox_pairs:
        return []

    results = []
    for image_path, bbox in image_bbox_pairs:
        try:
            text = ocr_region(image_path, bbox)
            results.append(text)
        except Exception as e:
            logger.error(f"Multi-image batch VL OCR failed: {e}")
            results.append("")

    return results


def extract_table_with_vl(image_path: str, bbox: tuple) -> dict:
    tmp_path = _crop_and_save_image(image_path, bbox)
    if not tmp_path:
        return {"html": "", "markdown": "", "rows": 0, "cols": 0}

    try:
        raw_output = _call_llama_server("Table Recognition:", tmp_path, max_tokens=1000)
        html, rows, cols = _parse_fcel_structured_to_html(raw_output)

        plain_text = _parse_fcel_to_text(raw_output)
        lines = [line.strip() for line in plain_text.split("\n") if line.strip()]
        md_lines = []
        for i, line in enumerate(lines):
            cells = [c.strip() for c in line.split() if c.strip()]
            if not cells:
                cells = [line]
            md_lines.append("| " + " | ".join(cells) + " |")
            if i == 0:
                md_lines.append("| " + " | ".join(["---"] * len(cells)) + " |")
        markdown = "\n".join(md_lines)

        return {
            "html": html,
            "markdown": markdown,
            "rows": rows if rows > 0 else len(lines),
            "cols": cols
        }
    except Exception as e:
        logger.error(f"VL Table extraction failed: {e}")
        return {"html": "", "markdown": "", "rows": 0, "cols": 0}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
