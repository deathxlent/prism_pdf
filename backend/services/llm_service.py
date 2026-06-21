import base64
import json
import logging
import urllib.request
from pathlib import Path
from backend.services.llm_config_service import get_active_config

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120


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


def _call_llm(messages: list, max_tokens: int = 2048) -> str:
    cfg = _get_active_llm()
    if not cfg:
        raise ValueError("未配置大模型，请先在系统管理中配置并激活一个 LLM")

    base_url = cfg.get("base_url", "").rstrip("/")
    if not base_url.endswith("/v1"):
        url = f"{base_url}/v1/chat/completions"
    else:
        url = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": cfg.get("model", "gpt-4o"),
        "messages": messages,
        "temperature": cfg.get("temperature", 0.3),
        "max_tokens": min(max_tokens, cfg.get("max_tokens", 4096)),
        "stream": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"]
    raise ValueError(f"LLM 返回异常: {result}")


def _call_llm_vision(text_prompt: str, image_path: str, max_tokens: int = 1024) -> str:
    cfg = _get_active_llm()
    if not cfg:
        raise ValueError("未配置大模型，请先在系统管理中配置并激活一个 LLM")

    if not cfg.get("supports_vision"):
        raise ValueError("当前激活的 LLM 不支持图生文 (Vision) 功能")

    base_url = cfg.get("base_url", "").rstrip("/")
    if not base_url.endswith("/v1"):
        url = f"{base_url}/v1/chat/completions"
    else:
        url = f"{base_url}/chat/completions"

    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    base64_image = _encode_image_file(image_path)

    ext = Path(image_path).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                {"type": "text", "text": text_prompt},
            ],
        }
    ]

    payload = {
        "model": cfg.get("model", "gpt-4o"),
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": min(max_tokens, cfg.get("max_tokens", 4096)),
        "stream": False,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    if "choices" in result and len(result["choices"]) > 0:
        return result["choices"][0]["message"]["content"]
    raise ValueError(f"LLM 返回异常: {result}")


def describe_image(image_path: str) -> str:
    if not Path(image_path).exists():
        raise FileNotFoundError(f"图片文件不存在: {image_path}")

    prompt = "请用中文简短描述这张图片的内容，用于文档检索(RAG)。描述应包含图片中的关键信息，不超过100字。只输出描述内容，不要任何前缀或解释。"
    return _call_llm_vision(prompt, image_path, max_tokens=200)


def translate_text(text: str, target_language: str) -> str:
    lang_names = {"en": "英语", "zh": "中文", "ja": "日语"}
    lang_display = lang_names.get(target_language, target_language)

    messages = [
        {
            "role": "system",
            "content": f"你是一个专业翻译助手。请将用户提供的文本翻译为{lang_display}。只输出翻译结果，不要任何解释、注释或前缀。保持原文的格式和结构。",
        },
        {"role": "user", "content": text},
    ]
    return _call_llm(messages, max_tokens=4096)


def translate_page_content(elements: list[dict], target_language: str) -> list[dict]:
    lang_names = {"en": "英语", "zh": "中文", "ja": "日语"}
    lang_display = lang_names.get(target_language, target_language)

    parts = []
    for i, elem in enumerate(elements):
        content = elem.get("content", "") or ""
        image_desc = elem.get("image_description", "") or ""
        etype = elem.get("element_type", "")

        if etype == "Picture" and image_desc:
            parts.append(f"[{i}] [图片描述] {image_desc}")
        elif content.strip() and etype != "Picture":
            parts.append(f"[{i}] {content}")

    if not parts:
        return []

    combined = "\n<hr/>\n".join(parts)

    messages = [
        {
            "role": "system",
            "content": f"""你是一个专业翻译助手。请将用户提供的文本翻译为{lang_display}。
文本由多个解析项组成，每项以 [序号] 开头，项与项之间用 <hr/> 分隔。
请严格按照相同的格式输出翻译结果，保留 [序号] 和 <hr/> 分隔符，以便程序解析回每一项。
只输出翻译结果，不要任何解释或注释。""",
        },
        {"role": "user", "content": combined},
    ]

    result = _call_llm(messages, max_tokens=8192)

    translated_items = _parse_translated_result(result)

    results = []
    for i, elem in enumerate(elements):
        content = elem.get("content", "") or ""
        image_desc = elem.get("image_description", "") or ""
        etype = elem.get("element_type", "")

        if etype == "Picture" and image_desc:
            translated = translated_items.get(i, image_desc)
        elif content.strip() and etype != "Picture":
            translated = translated_items.get(i, content)
        else:
            translated = ""

        if translated:
            results.append({"element_id": elem["id"], "translated_content": translated})

    return results


def _parse_translated_result(text: str) -> dict[int, str]:
    items = {}
    segments = text.split("<hr/>")

    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue

        import re
        match = re.match(r"\[(\d+)\]\s*", segment)
        if match:
            idx = int(match.group(1))
            content = segment[match.end():].strip()
            items[idx] = content
        else:
            if items:
                last_key = max(items.keys())
                items[last_key] += "\n" + segment

    return items
