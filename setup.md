# PaddleOCR-VL-1.6 GGUF 环境配置与使用指南

## 1. 环境要求

| 组件 | 要求 |
|------|------|
| OS | Windows 10/11 / Linux |
| GPU | **可选** — 见下方显存说明 |
| CUDA | CUDA 12+ / Driver 525+（有 GPU 时需要） |
| llama.cpp | b9571+（支持多模态） |
| Python | 3.10+（用于 Python API 调用） |

### 显存需求

以下为各量化等级在 Quadro P1000 (4GB) 上的实测/估算数据，包含模型权重 + mmproj(841MB) + KV Cache + CUDA 开销：

| 模型 | 大小 | n_ctx=4096 峰值 | n_ctx=131072 峰值 | 4GB 可用性 |
|------|------|----------------|-------------------|-----------|
| Q4_K_M | 286 MB | ~1.5 GB | ~2.6 GB | ✅ **实测可用** |
| Q8_0 | 475 MB | ~1.7 GB | ~2.8 GB | ✅ 理论可用 |
| F16 | 892 MB | ~2.1 GB | ~3.2 GB | ⚠️ 理论可装，但实测因 CUDA 开销可能溢出 |

> 峰值显存=权重 + mmproj + KV Cache + 计算缓冲区。mmproj 在图像编码完成后可释放，但 llama.cpp 默认持有一段时间。
> 若显存不足，可降 `n_ctx`（如 4096），或使用 `-ngl` 控制 GPU 卸载层数，剩余层走 CPU。

## 2. 目录结构（GPU 版）

```
G:\llamacpp\
├── llama-cli.exe          # llama.cpp 推理主程序（GPU+CPU）
├── llama-quantize.exe     # 模型量化工具
├── ggml-cuda.dll          # CUDA 后端
├── models\                # 模型文件目录
│   ├── PaddleOCR-VL-1.6.f16.gguf           # LLM 主干 (F16, 892MB)
│   ├── PaddleOCR-VL-1.6.Q8_0.gguf          # LLM 主干 (Q8_0, 475MB)
│   ├── PaddleOCR-VL-1.6.Q4_K_M.gguf        # LLM 主干 (Q4_K_M, 286MB)
│   └── PaddleOCR-VL-1.6-GGUF-mmproj.gguf   # 视觉编码器 (841MB)
```

### 无 GPU 目录结构（CPU-only）

```
C:\llamacpp-cpu\
├── llama-cli.exe          # llama.cpp CPU-only 版本
├── models\                # 模型文件目录
│   ├── PaddleOCR-VL-1.6.Q4_K_M.gguf        # LLM 主干
│   └── PaddleOCR-VL-1.6-GGUF-mmproj.gguf   # 视觉编码器
```

> CPU-only 版本不需要 `ggml-cuda.dll`，且 `llama-cli.exe` 体积更小（不包含 CUDA 后端）。
> 编译命令见第 8 节。

## 3. 模型下载

### 官方模型（HuggingFace）
- 仓库: https://huggingface.co/PaddlePaddle/PaddleOCR-VL-1.6-GGUF
- 文件: `PaddleOCR-VL-1.6-GGUF.gguf` (F16, 892MB) + `PaddleOCR-VL-1.6-GGUF-mmproj.gguf` (882MB)

```bash
# 使用 huggingface-cli（需先安装 huggingface_hub）
hf download PaddlePaddle/PaddleOCR-VL-1.6-GGUF PaddleOCR-VL-1.6-GGUF.gguf --local-dir G:\llamacpp\models\
hf download PaddlePaddle/PaddleOCR-VL-1.6-GGUF PaddleOCR-VL-1.6-GGUF-mmproj.gguf --local-dir G:\llamacpp\models\
```

### 国内镜像（ModelScope）
```bash
# 使用 Python
python -c "
import urllib.request
url = 'https://www.modelscope.cn/models/megemini/PaddleOCR-VL-GGUF/resolve/master/PaddleOCR-VL-GGUF.gguf'
urllib.request.urlretrieve(url, r'G:\llamacpp\models\PaddleOCR-VL-1.6.f16.gguf')
"
```

### 量化模型
Q8_0 和 Q4_K_M 可通过 `llama-quantize.exe` 从 F16 模型转换得到：
```bash
# F16 → Q8_0
llama-quantize.exe --allow-requantize model.f16.gguf model.q8_0.gguf Q8_0

# F16 → Q4_K_M
llama-quantize.exe --allow-requantize model.f16.gguf model.q4_k_m.gguf Q4_K_M
```

## 4. 命令行推理

### GPU 模式（有 NVIDIA 显卡）

使用 CUDA 后端，需确保 `ggml-cuda.dll` 与 `llama-cli.exe` 在同一目录。

```bash
# 通用文字识别（Q4_K_M 推荐）
llama-cli.exe -m G:\llamacpp\models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj G:\llamacpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --image page_1.jpg --temp 0 -p "OCR:" --no-display-prompt -ngl 99

# 表格识别（推荐，输出结构化 <fcel> 标签）
llama-cli.exe -m G:\llamacpp\models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj G:\llamacpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --image page_1.jpg --temp 0 -p "Table Recognition:" -n 500 --no-display-prompt -ngl 99
```

参数说明：
- `-ngl 99` — 全部层 GPU 卸载（0 为纯 CPU）
- `-n 500` — 最大生成 token 数
- `--temp 0` — 确定性输出

### CPU 模式（无 GPU）

使用 CPU 后端（OpenBLAS/CLBlast），完全不需要显卡。速度较慢但兼容任何机器。

```bash
# CPU-only 推理
llama-cli.exe -m C:\llamacpp-cpu\models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj C:\llamacpp-cpu\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --image page_1.jpg --temp 0 -p "OCR:" --no-display-prompt -ngl 0

# 若 CPU 支持 AVX2/AVX512，可添加线程数以加速
set OMP_NUM_THREADS=8
llama-cli.exe -m C:\llamacpp-cpu\models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj C:\llamacpp-cpu\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --image page_1.jpg --temp 0 -p "OCR:" --no-display-prompt -ngl 0 -t 8
```

参数说明：
- `-ngl 0` — 强制 CPU-only（不需要 CUDA dll）
- `-t 8` — CPU 线程数（建议设为物理核心数）
- `set OMP_NUM_THREADS=8` — OpenMP 线程环境变量

### 支持的提示词
| 提示词 | 用途 | 输出格式 |
|--------|------|---------|
| `OCR:` | 通用文本识别 | 纯文本（空格分隔） |
| `Table Recognition:` | **表格识别（推荐）** | 结构化 `<fcel>`/`<nl>` 标签 |
| `Formula Recognition:` | 公式识别 | — |
| `Chart Recognition:` | 图表识别 | — |
| `Seal Recognition:` | 印章识别 | — |
| `Spotting:` | 关键信息定位 | — |

> ⚠️ **重要**：`OCR:` 和 `Table Recognition:` 输出格式完全不同。`Table Recognition:` 输出含 `<fcel>`（单元格）、`<nl>`（换行）、`<ucel>`（跨行合并）等结构化标签，便于程序解析。`OCR:` 输出纯文本，表格以空格分隔。

### 结构化表格解析（Python）

使用 `Table Recognition:` 提示词时，模型输出 `<fcel>` 标签格式：

```python
import re
from html import escape

def parse_fcel_table(text: str) -> str:
    """将 <fcel>/<nl>/<ucel> 结构化输出转为 HTML 表格。"""
    if '<fcel>' not in text:
        return text  # 非结构化，原样返回
    
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
        while '<fcel>' in part:
            _, after = part.split('<fcel>', 1)
            end = len(after)
            for tag in ['<fcel>', '<lcel>']:
                pos = after.find(tag)
                if 0 <= pos < end:
                    end = pos
            cells.append(after[:end].strip())
            part = after[end:]
        rows.append((cells, is_ucel))
    
    # 构建 HTML table，处理 rowspan
    if len(rows) < 2:
        return escape(text)
    html = '<table>\n'
    for i, (cells, is_ucel) in enumerate(rows):
        tag = 'th' if i == 0 else 'td'
        html += '<tr>'
        for ci, content in enumerate(cells):
            if is_ucel and ci == 0:
                html += '<td></td>'  # 跨行合并列留空
            else:
                html += f'<{tag}>{escape(content)}</{tag}>'
        html += '</tr>\n'
    html += '</table>'
    return html
```

完整解析脚本见 `test/_gen_vl_report3.py`。

### 性能参数

| 模式 | 模型 | 大小 | 提示速度 | 生成速度 | 平台 |
|------|------|------|---------|---------|------|
| GPU | Q4_K_M | 286 MB | 71.4 t/s | 67.0 t/s | ✅ Quadro P1000 实测 |
| GPU | Q8_0 | 475 MB | 71.3 t/s | 65.1 t/s | ✅ Quadro P1000 实测 |
| GPU | F16 | 892 MB | — | — | ⚠️ 理论可装但 CUDA 开销易溢出 |
| CPU | Q4_K_M | 286 MB | ~2-5 t/s* | ~5-10 t/s* | 任意 x86_64 |

> Q4_K_M 和 Q8_0 均在 Quadro P1000 (4GB) 上实测通过。两者性能差异极小（< 3%），Q4_K_M 模型更小更稳妥，Q8_0 精度稍高。
> CPU 速度取决于核心数和内存带宽：8 核现代 CPU 约 5-10 t/s，老旧 CPU 更慢。

## 5. Python API 调用

### 安装 llama-cpp-python

```bash
# ── CPU 版（无 GPU，任何机器可用）──
pip install llama-cpp-python

# ── CUDA 版（需先安装 CUDA Toolkit）──
set CMAKE_ARGS="-DGGML_CUDA=on"
pip install llama-cpp-python

# ── 验证安装 ──
python -c "from llama_cpp import Llama; print('ok')"
```

### OCR 单图识别

```python
from llama_cpp import Llama
import time

MODEL_PATH = r"G:\llamacpp\models\PaddleOCR-VL-1.6.Q4_K_M.gguf"
MMPROJ_PATH = r"G:\llamacpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf"

# ── 加载模型 ──
# 有 GPU:
llm = Llama(
    model_path=MODEL_PATH,
    mmproj=MMPROJ_PATH,
    n_gpu_layers=-1,          # 全部 GPU 卸载
    n_ctx=4096,               # 上下文长度（默认 131072，降为 4096 省显存）
    temperature=0,
    verbose=False,
)

# 无 GPU（CPU-only）:
# llm = Llama(
#     model_path=MODEL_PATH,
#     mmproj=MMPROJ_PATH,
#     n_gpu_layers=0,         # 全部 CPU
#     n_ctx=4096,
#     n_threads=8,            # CPU 线程数
#     temperature=0,
#     verbose=False,
# )

# 执行 OCR
start = time.time()
output = llm.create_chat_completion(
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "page_1.jpg"}},
            {"type": "text", "text": "OCR:"},
        ],
    }],
    max_tokens=512,
)
elapsed = time.time() - start

text = output["choices"][0]["message"]["content"]
print(f"OCR 结果 ({len(text)} 字符, 耗时 {elapsed:.1f}s):")
print(text)
```

### 批量文档处理
```python
import os, glob, json

def ocr_image(llm, image_path: str) -> dict:
    """对单张图片执行 OCR，返回结果与耗时"""
    start = time.time()
    output = llm.create_chat_completion(
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": image_path}},
                {"type": "text", "text": "OCR:"},
            ],
        }],
        max_tokens=1024,
    )
    elapsed = time.time() - start
    return {
        "file": os.path.basename(image_path),
        "text": output["choices"][0]["message"]["content"],
        "elapsed_s": round(elapsed, 1),
    }

# 批量处理
results = []
for img in sorted(glob.glob("pages/*.jpg")):
    print(f"处理: {img}")
    result = ocr_image(llm, img)
    results.append(result)
    print(f"  → {len(result['text'])} 字符, {result['elapsed_s']}s")

# 保存结果
with open("ocr_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
```

### 启动 API 服务

```bash
# GPU 模式（推荐）
llama-server.exe -m G:\llamacpp\models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj G:\llamacpp\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --host 0.0.0.0 --port 8080 -ngl 99 --temp 0

# CPU-only 模式（无 GPU）
llama-server.exe -m C:\llamacpp-cpu\models\PaddleOCR-VL-1.6.Q4_K_M.gguf ^
  --mmproj C:\llamacpp-cpu\models\PaddleOCR-VL-1.6-GGUF-mmproj.gguf ^
  --host 0.0.0.0 --port 8080 -ngl 0 -t 8
```

```python
# Python 客户端调用（OpenAI 兼容接口）
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8080/v1", api_key="sk-no-key-required")

response = client.chat.completions.create(
    model="paddleocr-vl",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": "page_1.jpg"}},
            {"type": "text", "text": "OCR:"},
        ],
    }],
    max_tokens=512,
)
print(response.choices[0].message.content)
```

## 6. 表格输出处理

PaddleOCR-VL 支持两种输出模式，取决于提示词：

### 模式 A（推荐）：`Table Recognition:` — 结构化标签

模型输出 `<fcel>`（单元格）、`<nl>`（行分隔）、`<ucel>`（跨行合并标记）标签：

```
<fcel>项目<fcel>2017年3月<fcel>2016年<fcel>2015年<fcel>2014年<nl>
<fcel>公路运营毛利率<fcel>83.06<fcel>80.56<fcel>39.28<fcel>47.38<nl>
<fcel>G75兰海高速<fcel>崇遵公路<fcel>起自桐梓县...<fcel>收费还贷<fcel>2005-2035<nl>
<ucel><fcel>贵遵公路<fcel>起自贵阳市...<fcel>收费还贷<fcel>2007-2035<nl>
```

解析脚本见 `test/_gen_vl_report3.py` 中的 `parse_fcel_structured()` 函数，支持跨行合并（rowspan）。

### 模式 B（备用）：`OCR:` — 空格分隔纯文本

```python
def is_table_row(line: str) -> bool:
    tokens = line.strip().split()
    if len(tokens) < 3: return False
    non_first = [t for i, t in enumerate(tokens) if i > 0]
    if len(non_first) >= 2:
        short = sum(1 for t in non_first if len(t) <= 20)
        return short >= len(non_first) * 0.5
    return False
```

## 7. 编译 llama.cpp

### GPU 版（CUDA）
```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build && cd build

cmake .. -DGGML_CUDA=ON
cmake --build . --config Release
# 产物: build/bin/Release/llama-cli.exe + ggml-cuda.dll
```

### CPU-only 版（无 GPU，推荐下载预编译）
```bash
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp
mkdir build && cd build

cmake .. -DGGML_CUDA=OFF -DGGML_BLAS=ON -DGGML_BLAS_VENDOR=OpenBLAS
cmake --build . --config Release
# 产物: build/bin/Release/llama-cli.exe（不依赖 CUDA dll）
```

> 也可直接下载官方 Release: https://github.com/ggml-org/llama.cpp/releases
> GPU 选 `llama-b9571-bin-win-cuda-x64.zip`，CPU-only 选 `llama-b9571-bin-win-cpu-x64.zip`。

## 8. 常见问题

**Q: CUDA out of memory**
- 换用 Q4_K_M 量化（模型仅 286MB，mmproj 841MB）
- 减少 `n_ctx`（默认 131072，可降至 4096）
- 使用 `-ngl` 控制 GPU 卸载层数，如 `-ngl 20` 只卸载 20 层

**Q: 没有 NVIDIA 显卡能跑吗？**
- 能。使用 CPU-only 版 llama-cli（`-ngl 0`），不需要任何 GPU。
- 速度慢但结果一致。建议 8 核以上 CPU，设置 `-t 8` 和 `set OMP_NUM_THREADS=8`。
- 推荐 Q4_K_M 量化（模型最小，CPU 推理负担最低）。
- 一张图 OCR 约需 30-120 秒（取决于 CPU 性能）。

**Q: 模型加载显示 "modalities: text, vision" 但输出为空**
- 确认 mmproj 文件与模型匹配
- F16 模型在 4GB VRAM GPU 上可能因显存不足静默崩溃

**Q: llama-cli 命令行卡住不动**
- 添加 `-n 200` 限制生成 token 数量
- 使用 `--no-display-prompt` 避免交互模式
- 确认图片路径正确
