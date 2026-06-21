import base64
import json
import logging
import re
import urllib.request
from pathlib import Path
from backend.services.llm_config_service import get_active_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 1800
VISION_TIMEOUT = 3600


def _encode_image_file(image_path: str) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_active_llm() -> dict | None:
    cfg = get_active_config()
    if not cfg:
        return None
    if not cfg.get("api_key") and not cfg.get("base_url"):
        return None
    return cfg


def _build_url(base_url: str) -> str:
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/v1"):
        return f"{base_url}/v1/chat/completions"
    return f"{base_url}/chat/completions"


def _extract_content_from_response(message: dict) -> str:
    if not message:
        return ""

    content = message.get("content", "")
    if content is None:
        content = ""

    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text" and part.get("text"):
                    parts.append(part["text"])
        content = "\n".join(parts)

    if content.strip():
        return content.strip()

    reasoning = message.get("reasoning_content", "") or message.get("reasoning", "") or ""
    if reasoning:
        logger.info("content 为空，尝试从 reasoning_content 提取答案")
        answer = _extract_answer_from_reasoning(reasoning)
        if answer:
            logger.info(f"从 reasoning_content 提取到答案 ({len(answer)} 字符)")
            return answer

    return content.strip()


def _extract_answer_from_reasoning(reasoning: str) -> str:
    if not reasoning:
        return ""

    patterns = [
        r'(?:最终答案|答案|回答|输出|结果|翻译结果|翻译后内容)[:：]\s*([\s\S]+?)(?:\s*$)',
        r'<\s*(?:answer|output|result|response)\s*>[\s\S]*?</\s*(?:answer|output|result|response)\s*>',
        r'(?:Therefore|Thus|So|In conclusion|综上|因此|所以).*?[。.!！?:：]\s*([\s\S]+)',
        r'([^。.!！?:：]*?(?:翻译|描述|总结|分析)[^。.!！?:：]*?[。.!！?:：][\s\S]*?)$',
    ]

    for p in patterns:
        m = re.search(p, reasoning, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            if len(candidate) > 5:
                return candidate

    blocks = re.split(r'\n\s*\n', reasoning.strip())
    if blocks:
        last = blocks[-1].strip()
        if len(last) > 3:
            return last

    sentences = re.split(r'[。.!！?？\n]', reasoning.strip())
    meaningful = [s.strip() for s in sentences if len(s.strip()) > 10]
    if meaningful:
        return meaningful[-1]

    lines = [l.strip() for l in reasoning.split("\n") if l.strip()]
    if lines:
        for i in range(len(lines) - 1, -1, -1):
            line = lines[i]
            if len(line) > 10 and not re.match(r'^[\d\.\s\-]+$', line):
                return line
    return ""


def _call_llm(messages: list, max_tokens: int = 4096) -> str:
    cfg = _get_active_llm()
    if not cfg:
        raise ValueError("未配置大模型，请先在系统管理中配置并激活一个 LLM")

    url = _build_url(cfg.get("base_url", ""))
    logger.info(f"LLM 请求 URL: {url}, model={cfg.get('model')}, max_tokens={max_tokens}")

    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    effective_max_tokens = max(max_tokens, cfg.get("max_tokens", 4096), 2048)

    payload = {
        "model": cfg.get("model", "gpt-4o"),
        "messages": messages,
        "temperature": cfg.get("temperature", 0.3),
        "max_tokens": effective_max_tokens,
        "stream": False,
    }

    if cfg.get("disable_thinking"):
        payload["disable_thinking"] = True

    logger.info(f"发送请求 (tokens={effective_max_tokens})...")

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
    except urllib.error.HTTPError as e:
        logger.error(f"HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')[:500]}")
        raise ValueError(f"LLM API HTTP 错误: {e.code} {e.reason}")
    except Exception as e:
        logger.error(f"LLM 请求异常: {type(e).__name__}: {e}")
        raise

    logger.info(f"LLM 响应接收完成，原始大小: {len(raw)} 字符")

    if "choices" in result and len(result["choices"]) > 0:
        choice = result["choices"][0]
        finish_reason = choice.get("finish_reason", "")
        logger.info(f"finish_reason={finish_reason}")
        if finish_reason == "length":
            logger.warning(f"⚠️ 输出被截断 (finish_reason=length)，建议增大 max_tokens")

        message = choice.get("message", {})
        content = _extract_content_from_response(message)

        if not content:
            logger.warning(f"content 提取后仍为空，原始 message: {json.dumps(message, ensure_ascii=False)[:300]}")
            logger.warning(f"完整响应: {raw[:1000]}")

        usage = result.get("usage", {})
        if usage:
            logger.info(f"Token 使用: {usage}")

        return content

    logger.error(f"LLM 返回异常: {json.dumps(result, ensure_ascii=False)[:500]}")
    raise ValueError(f"LLM 返回异常格式: {list(result.keys())}")


def _call_llm_vision(text_prompt: str, image_path: str, max_tokens: int = 1024) -> str:
    cfg = _get_active_llm()
    if not cfg:
        raise ValueError("未配置大模型，请先在系统管理中配置并激活一个 LLM")

    if not cfg.get("supports_vision"):
        raise ValueError("当前激活的 LLM 不支持图生文 (Vision) 功能")

    url = _build_url(cfg.get("base_url", ""))
    logger.info(f"Vision 请求 URL: {url}")

    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    base64_image = _encode_image_file(image_path)
    file_size = Path(image_path).stat().st_size
    ext = Path(image_path).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    logger.info(f"图片: {image_path}, 大小: {file_size/1024:.1f} KB, base64: {len(base64_image)} 字符, MIME: {mime_type}")

    effective_max_tokens = max(max_tokens, cfg.get("max_tokens", 4096), 2048)

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": text_prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
            ],
        }
    ]

    payload = {
        "model": cfg.get("model", "gpt-4o"),
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": effective_max_tokens,
        "stream": False,
    }

    if cfg.get("disable_thinking"):
        payload["disable_thinking"] = True

    logger.info(f"发送 Vision 请求 (tokens={effective_max_tokens})...")

    data = json.dumps(payload).encode("utf-8")
    logger.info(f"请求体大小: {len(data)/1024:.1f} KB")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=VISION_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
    except urllib.error.HTTPError as e:
        logger.error(f"Vision HTTP Error {e.code}: {e.read().decode('utf-8', errors='ignore')[:500]}")
        raise ValueError(f"Vision LLM API HTTP 错误: {e.code} {e.reason}")
    except Exception as e:
        logger.error(f"Vision 请求异常: {type(e).__name__}: {e}")
        raise

    logger.info(f"Vision 响应接收完成，原始大小: {len(raw)} 字符")

    if "choices" in result and len(result["choices"]) > 0:
        choice = result["choices"][0]
        finish_reason = choice.get("finish_reason", "")
        logger.info(f"finish_reason={finish_reason}")
        if finish_reason == "length":
            logger.warning(f"⚠️ Vision 输出被截断 (finish_reason=length)")

        message = choice.get("message", {})
        content = _extract_content_from_response(message)

        if not content:
            logger.warning(f"Vision content 提取后仍为空，原始 message: {json.dumps(message, ensure_ascii=False)[:300]}")
            alt_messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                        {"type": "text", "text": text_prompt},
                    ],
                }
            ]
            logger.info("尝试交换图片和文本的顺序重试...")
            payload["messages"] = alt_messages
            try:
                data2 = json.dumps(payload).encode("utf-8")
                req2 = urllib.request.Request(url, data=data2, headers=headers, method="POST")
                with urllib.request.urlopen(req2, timeout=VISION_TIMEOUT) as resp:
                    raw2 = resp.read().decode("utf-8")
                    result2 = json.loads(raw2)
                if "choices" in result2 and len(result2["choices"]) > 0:
                    content = _extract_content_from_response(result2["choices"][0].get("message", {}))
                    if content:
                        logger.info("重试成功！")
            except Exception as e2:
                logger.error(f"Vision 重试失败: {e2}")

        usage = result.get("usage", {})
        if usage:
            logger.info(f"Vision Token 使用: {usage}")

        if content:
            return content

        logger.error(f"Vision 所有尝试都返回空内容。完整响应: {raw[:1500]}")
        raise ValueError("Vision 模型返回的内容为空，请检查模型是否正常工作")

    logger.error(f"Vision LLM 返回异常: {json.dumps(result, ensure_ascii=False)[:500]}")
    raise ValueError(f"Vision LLM 返回异常格式: {list(result.keys())}")


def describe_image(image_path: str) -> str:
    if not Path(image_path).exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    prompt = (
        "请用中文详细描述这张图片的内容，用于文档检索(RAG)。\n"
        "描述应包含：\n"
        "1. 图片的整体主题\n"
        "2. 图片中的关键元素（人物、物体、文字、图表、数据等）\n"
        "3. 任何重要的细节信息\n\n"
        "要求：\n"
        "- 直接输出描述内容，不要任何前缀或解释\n"
        "- 描述要尽可能详细准确\n"
        "- 最终答案要完整清晰"
    )
    return _call_llm_vision(prompt, image_path, max_tokens=2048)


def translate_text(text: str, target_language: str) -> str:
    lang_names = {"en": "英语", "zh": "中文", "ja": "日语"}
    lang_display = lang_names.get(target_language, target_language)

    messages = [
        {
            "role": "system",
            "content": (
                f"你是一个专业翻译助手。请将用户提供的文本翻译为{lang_display}。\n"
                f"要求：\n"
                f"1. 只输出翻译结果，不要任何解释、注释或前缀\n"
                f"2. 保持原文的格式和结构\n"
                f"3. 确保翻译准确流畅，符合{lang_display}表达习惯\n"
                f"4. 最终答案完整清晰"
            ),
        },
        {"role": "user", "content": text},
    ]
    result = _call_llm(messages, max_tokens=8192)
    return result


def translate_page_content(elements: list[dict], target_language: str) -> list[dict]:
    lang_names = {"en": "英语", "zh": "中文", "ja": "日语"}
    lang_display = lang_names.get(target_language, target_language)

    parts = []
    elem_map = []
    for i, elem in enumerate(elements):
        content = elem.get("content", "") or ""
        image_desc = elem.get("image_description", "") or ""
        etype = elem.get("element_type", "")

        if etype == "Picture" and image_desc:
            parts.append(f"[{i}] [图片描述] {image_desc}")
            elem_map.append(i)
        elif content.strip() and etype != "Picture":
            parts.append(f"[{i}] {content}")
            elem_map.append(i)

    if not parts:
        return []

    combined = "\n<hr/>\n".join(parts)
    logger.info(f"翻译页面: {len(parts)} 个解析项, 合并后文本长度: {len(combined)} 字符")

    messages = [
        {
            "role": "system",
            "content": f"""你是一个专业翻译助手。请将用户提供的文本翻译为{lang_display}。

重要规则：
1. 文本由多个解析项组成，每项格式为 [序号] 内容
2. 项与项之间用 <hr/> 分隔
3. 请严格按照相同的格式输出翻译结果：
   - 保留原来的 [序号] 标记，序号不能改变
   - 项与项之间仍然用 <hr/> 分隔
   - 对于 [图片描述] 标签，翻译时保留 [图片描述] 只翻译后面的内容
4. 只输出翻译结果，不要任何解释、注释或额外文字
5. 最终答案必须严格遵守格式，确保序号和分隔符完整""",
        },
        {"role": "user", "content": combined},
    ]

    result = _call_llm(messages, max_tokens=16384)
    logger.info(f"翻译完成，返回长度: {len(result)} 字符")

    translated_items = _parse_translated_result(result, len(parts))

    results = []
    for pos, i in enumerate(elem_map):
        elem = elements[i]
        content = elem.get("content", "") or ""
        image_desc = elem.get("image_description", "") or ""
        etype = elem.get("element_type", "")

        if pos in translated_items:
            translated = translated_items[pos]
            if etype == "Picture":
                prefix = "[图片描述]"
                if translated.startswith(prefix):
                    translated = translated[len(prefix):].strip()
                elif translated.startswith("【图片描述】"):
                    translated = translated[len("【图片描述】"):].strip()
            results.append({"element_id": elem["id"], "translated_content": translated})
        elif etype == "Picture" and image_desc:
            results.append({"element_id": elem["id"], "translated_content": image_desc})
        elif content.strip() and etype != "Picture":
            results.append({"element_id": elem["id"], "translated_content": content})

    return results


def _parse_translated_result(text: str, expected_count: int = 0) -> dict[int, str]:
    items = {}
    if not text:
        return items

    segments = re.split(r'<hr\s*/?>', text, flags=re.IGNORECASE)

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        match = re.match(r'\[(\d+)\]\s*', segment)
        if match:
            idx = int(match.group(1))
            content = segment[match.end():].strip()
            items[idx] = content
        else:
            if items:
                last_key = max(items.keys())
                items[last_key] += "\n" + segment

    if expected_count > 0 and len(items) < expected_count:
        logger.warning(f"翻译解析项数量不足: 预期 {expected_count}, 实际 {len(items)}")
        fallback = re.findall(r'\[(\d+)\][\s\S]*?(?=\[\d+\]|$)', text)
        if len(fallback) > len(items):
            logger.info("使用备用正则重新解析...")
            alt_segments = re.split(r'(?=\[\d+\])', text)
            for seg in alt_segments:
                seg = seg.strip()
                if not seg:
                    continue
                m = re.match(r'\[(\d+)\]\s*', seg)
                if m:
                    idx = int(m.group(1))
                    content = seg[m.end():].strip()
                    if content:
                        items[idx] = content

    return items
