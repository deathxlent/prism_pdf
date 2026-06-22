import base64
import json
import sys
import urllib.request
import urllib.error
from pathlib import Path

IMAGE_PATH = r"G:\ws\Prism PDF\tmp\65adda9dc5874afcb0fd59a78574a942\page_1.jpg"
API_URL = "http://localhost:9092/v1/chat/completions"

OCR_PROMPT = """你是一个专业的文档OCR和结构分析专家。请仔细分析这张图片，提取其中的所有内容，并按文档结构进行分类。

要求：
1. 识别并区分以下结构类型：
   - page_header: 页头（页眉）
   - page_footer: 页脚（页脚）
   - title: 标题（包括各级标题）
   - heading: 子标题
   - paragraph: 正文段落
   - text: 普通文本
   - list: 列表（有序/无序）
   - image: 图片（描述图片内容和位置）
   - figure: 图表
   - table: 表格（必须完整还原，包括跨行跨列）
   - equation: 公式
   - code: 代码块
   - footnote: 脚注
   - citation: 引用

2. 对于表格(table)的特殊要求：
   - 识别表格的所有单元格内容
   - 识别跨行(row_span)和跨列(col_span)
   - 识别表头(header)和表体(body)
   - 用JSON数组形式表示，每行一个数组元素
   - 每个单元格包含: content, row_span(默认1), col_span(默认1), is_header(布尔值)

3. 输出格式要求：
   以严格的JSON格式输出，不要包含任何markdown标记或额外的说明文字。
   顶级结构为:
   {
     "page_info": {
       "page_number": 检测到的页码(如果有),
       "orientation": "portrait" 或 "landscape",
       "language": "主要语言"
     },
     "elements": [
       {
         "type": "结构类型",
         "content": "内容文本",
         "order": 阅读顺序序号(从1开始),
         "level": 标题级别(1-6，仅标题需要),
         "cells": [ 仅table类型需要，表格单元格数组
           [
             {"content": "单元格内容", "row_span": 1, "col_span": 2, "is_header": true},
             ...
           ],
           ...
         ],
         "image_description": "图片描述(仅image/figure类型需要)"
       },
       ...
     ]
   }

请确保：
- 所有文本内容准确提取，包括标点符号
- 阅读顺序正确，按从上到下、从左到右的自然阅读顺序
- 表格的跨行跨列准确识别
- JSON格式严格合法，没有语法错误
- 不要输出任何JSON以外的内容
"""


def encode_image(image_path: str) -> tuple[str, str]:
    with open(image_path, "rb") as f:
        base64_data = base64.b64encode(f.read()).decode("utf-8")
    
    ext = Path(image_path).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", 
                ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/jpeg")
    
    return base64_data, mime_type


def call_llamacpp_vision(prompt: str, image_path: str, max_tokens: int = 16384) -> str:
    base64_image, mime_type = encode_image(image_path)
    file_size = Path(image_path).stat().st_size
    
    print(f"图片: {image_path}")
    print(f"大小: {file_size/1024:.1f} KB")
    print(f"MIME类型: {mime_type}")
    print(f"Base64长度: {len(base64_image)} 字符")
    print(f"API地址: {API_URL}")
    print("-" * 70)
    
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
            ],
        }
    ]
    
    payload = {
        "model": "qwen-vl",
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    print(f"请求体大小: {len(data)/1024:.1f} KB")
    print("发送请求... (超时: 3600秒)")
    
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")
    
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')[:1000]}")
        raise
    except Exception as e:
        print(f"请求异常: {type(e).__name__}: {e}")
        raise
    
    print(f"响应接收完成，原始大小: {len(raw)} 字符")
    
    result = json.loads(raw)
    if "choices" in result and len(result["choices"]) > 0:
        choice = result["choices"][0]
        finish_reason = choice.get("finish_reason", "")
        print(f"finish_reason: {finish_reason}")
        
        if finish_reason == "length":
            print("⚠️ 输出被截断！")
        
        message = choice.get("message", {})
        content = message.get("content", "")
        
        usage = result.get("usage", {})
        if usage:
            print(f"Token使用: {usage}")
        
        return content
    
    print(f"LLM返回异常: {json.dumps(result, ensure_ascii=False, indent=2)[:500]}")
    raise ValueError(f"异常返回格式: {list(result.keys())}")


def parse_ocr_result(content: str) -> dict:
    content = content.strip()
    
    if content.startswith("```json"):
        content = content[7:]
    if content.startswith("```"):
        content = content[3:]
    if content.endswith("```"):
        content = content[:-3]
    
    content = content.strip()
    
    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        print(f"尝试提取JSON部分...")
        
        start = content.find('{')
        end = content.rfind('}')
        if start != -1 and end != -1:
            json_str = content[start:end+1]
            try:
                return json.loads(json_str)
            except json.JSONDecodeError as e2:
                print(f"提取后仍解析失败: {e2}")
        
        print(f"原始内容:\n{content[:2000]}")
        raise


def print_structured_result(data: dict):
    print("\n" + "=" * 70)
    print("📄 页面信息")
    print("=" * 70)
    page_info = data.get("page_info", {})
    print(f"  页码: {page_info.get('page_number', '未检测到')}")
    print(f"  方向: {page_info.get('orientation', '未检测到')}")
    print(f"  语言: {page_info.get('language', '未检测到')}")
    
    elements = data.get("elements", [])
    print(f"\n共识别到 {len(elements)} 个结构元素")
    
    type_counts = {}
    for elem in elements:
        etype = elem.get("type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1
    
    print("\n按类型统计:")
    for etype, count in sorted(type_counts.items()):
        print(f"  {etype}: {count} 个")
    
    print("\n" + "=" * 70)
    print("📋 详细内容")
    print("=" * 70)
    
    for i, elem in enumerate(elements, 1):
        etype = elem.get("type", "unknown")
        order = elem.get("order", i)
        content = elem.get("content", "")
        
        type_emojis = {
            "page_header": "📌",
            "page_footer": "📌",
            "title": "🔴",
            "heading": "🟠",
            "paragraph": "📝",
            "text": "📄",
            "list": "📋",
            "image": "🖼️",
            "figure": "📊",
            "table": "📊",
            "equation": "🔢",
            "code": "💻",
            "footnote": "📑",
            "citation": "📚",
        }
        
        emoji = type_emojis.get(etype, "❓")
        
        print(f"\n{emoji} [{order}] {etype.upper()}")
        print("-" * 50)
        
        if etype == "table":
            cells = elem.get("cells", [])
            if cells:
                print(f"  表格行数: {len(cells)}")
                print("  表格内容:")
                for row_idx, row in enumerate(cells):
                    row_str = []
                    for cell in row:
                        cell_content = cell.get("content", "").strip()
                        rs = cell.get("row_span", 1)
                        cs = cell.get("col_span", 1)
                        ih = cell.get("is_header", False)
                        cell_str = f"{cell_content}"
                        if rs > 1 or cs > 1:
                            cell_str += f" [×{rs}×{cs}]"
                        if ih:
                            cell_str = f"*{cell_str}*"
                        row_str.append(cell_str)
                    print(f"    行{row_idx+1}: {' | '.join(row_str)}")
        elif etype in ("image", "figure"):
            desc = elem.get("image_description", content)
            if desc:
                print(f"  描述: {desc[:200]}{'...' if len(desc) > 200 else ''}")
        elif etype in ("title", "heading"):
            level = elem.get("level", "?")
            print(f"  级别: H{level}")
            if content:
                print(f"  内容: {content[:200]}{'...' if len(content) > 200 else ''}")
        else:
            if content:
                preview = content[:300].replace('\n', '\n    ')
                print(f"  内容:\n    {preview}{'...' if len(content) > 300 else ''}")


def main():
    print("=" * 70)
    print("🔍 Qwen-VL 结构化OCR 测试脚本")
    print("=" * 70)
    
    if not Path(IMAGE_PATH).exists():
        print(f"❌ 图片不存在: {IMAGE_PATH}")
        return 1
    
    try:
        print("\n📤 发送OCR请求...")
        result = call_llamacpp_vision(OCR_PROMPT, IMAGE_PATH)
        
        print("\n📥 解析结果...")
        data = parse_ocr_result(result)
        
        print_structured_result(data)
        
        output_file = Path(__file__).parent / "ocr_result.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 结果已保存到: {output_file}")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ 测试失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
