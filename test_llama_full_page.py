import fitz
import base64
import json
import urllib.request
import os
from pathlib import Path

LLAMA_SERVER_URL = "http://127.0.0.1:8080"
LLAMA_MODEL_NAME = "PaddleOCR-VL-1.6.Q4_K_M.gguf"

def convert_to_jpg(pdf_path, output_dir, dpi=200):
    doc = fitz.open(pdf_path)
    jpg_paths = []
    os.makedirs(output_dir, exist_ok=True)
    
    for i in range(len(doc)):
        page = doc[i]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        jpg_path = os.path.join(output_dir, f"page_{i+1}.jpg")
        pix.save(jpg_path)
        jpg_paths.append(jpg_path)
        print(f"Converted page {i+1}: {pix.width}x{pix.height} -> {jpg_path}")
    
    doc.close()
    return jpg_paths

def encode_image(image_path):
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode('utf-8')

def call_llama(prompt, image_path, max_tokens=4000):
    base64_image = encode_image(image_path)
    
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
    
    print(f"Calling llama-server with prompt: '{prompt[:50]}...'")
    print(f"Image: {os.path.basename(image_path)}, size: {os.path.getsize(image_path)/1024:.1f} KB")
    
    with urllib.request.urlopen(req, timeout=600) as resp:
        result = json.loads(resp.read().decode('utf-8'))
    
    if 'choices' in result and len(result['choices']) > 0:
        content = result['choices'][0]['message']['content']
        print(f"Response length: {len(content)} chars")
        return content
    return ""

def main():
    pdf_path = r"g:\ws\Prism PDF\tmp\table-t1images.pdf"
    test_dir = r"g:\ws\Prism PDF\tmp\test_scanned_parse"
    
    print("=" * 80)
    print("STEP 1: Convert PDF to images")
    print("=" * 80)
    jpg_paths = convert_to_jpg(pdf_path, test_dir)
    
    for jpg_path in jpg_paths:
        print(f"\n{'=' * 80}")
        print(f"Processing: {os.path.basename(jpg_path)}")
        print("=" * 80)
        
        # 测试1: OCR: 提示词 - 看原始输出
        print("\n--- Test 1: 'OCR:' prompt ---")
        result_ocr = call_llama("OCR:", jpg_path, max_tokens=3000)
        print("Result:")
        print(result_ocr[:3000])
        if len(result_ocr) > 3000:
            print(f"... (truncated, total {len(result_ocr)} chars)")
        
        # 测试2: Table Recognition: 提示词
        print("\n--- Test 2: 'Table Recognition:' prompt ---")
        result_table = call_llama("Table Recognition:", jpg_path, max_tokens=3000)
        print("Result:")
        print(result_table[:3000])
        if len(result_table) > 3000:
            print(f"... (truncated, total {len(result_table)} chars)")
        
        # 测试3: 自定义提示词，要求结构化输出
        custom_prompt = """请对这张PDF页面图片进行完整解析。
请输出页面中所有内容，使用以下标签：
- 标题或章节用 <title>...</title>
- 普通段落用 <p>...</p>
- 表格用 <table>标签包裹，每个单元格用 <fcel>内容 标记，每行结束用 <nl> 标记，跨行用 <ucel> 标记（与 PaddleOCR-VL 的格式一致）。
- 页眉用 <header>...</header>
- 页脚用 <footer>...</footer>
- 图片用 <picture>描述</picture>

请按阅读顺序从上到下输出所有内容，不要遗漏。"""
        
        print("\n--- Test 3: Custom structured prompt ---")
        result_custom = call_llama(custom_prompt, jpg_path, max_tokens=4000)
        print("Result:")
        print(result_custom[:4000])
        if len(result_custom) > 4000:
            print(f"... (truncated, total {len(result_custom)} chars)")
        
        # 保存所有结果
        with open(os.path.join(test_dir, f"page_1_results.txt"), "w", encoding="utf-8") as f:
            f.write("=== TEST 1: OCR: ===\n\n")
            f.write(result_ocr)
            f.write("\n\n=== TEST 2: Table Recognition: ===\n\n")
            f.write(result_table)
            f.write("\n\n=== TEST 3: Custom Structured Prompt ===\n\n")
            f.write(result_custom)
        print(f"\nAll results saved to {os.path.join(test_dir, 'page_1_results.txt')}")

if __name__ == "__main__":
    main()
