import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.services.llm_config_service import get_active_config
from backend.services.llm_service import _get_active_llm, _encode_image_file, _extract_content_from_response


def test_llm_detailed():
    print("=" * 70)
    print("测试: LLM 详细响应分析")
    cfg = _get_active_llm()
    if not cfg:
        print("❌ 未找到激活的 LLM 配置")
        return None

    print(f"配置 max_tokens: {cfg.get('max_tokens')}")

    from backend.services.llm_service import _build_url
    url = _build_url(cfg.get("base_url", ""))
    print(f"URL: {url}")
    print(f"Model: {cfg.get('model')}")

    messages = [
        {
            "role": "system",
            "content": "你是一个翻译助手。用户说什么，你就翻译成英语。只输出翻译结果。"
        },
        {"role": "user", "content": "你好，今天天气不错，我们一起去公园玩吧！"}
    ]
    payload = {
        "model": cfg.get("model", "gpt-4o"),
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": cfg.get("max_tokens", 4096),
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        print(f"\n发送请求 (max_tokens={payload['max_tokens']})...")
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
            print(f"原始响应长度: {len(raw)} 字符")
            result = json.loads(raw)
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return None

    print(f"\n解析后的 JSON 顶层 keys: {list(result.keys())}")
    if "choices" in result:
        print(f"choices 长度: {len(result['choices'])}")
        if len(result["choices"]) > 0:
            choice = result["choices"][0]
            print(f"choice[0] finish_reason: {choice.get('finish_reason')}")
            if "message" in choice:
                msg = choice["message"]
                content = _extract_content_from_response(msg)
                reasoning = msg.get("reasoning_content", "")
                print(f"\n--- 原始 reasoning_content ({len(reasoning)} 字符) ---")
                print(reasoning[-800:] if len(reasoning) > 800 else reasoning)
                print(f"\n--- 提取到的最终答案 ({len(content)} 字符) ---")
                print(repr(content))
    if "usage" in result:
        print(f"\nUsage: {result['usage']}")
    return cfg


def test_vision_detailed(cfg):
    if not cfg:
        return
    if not cfg.get("supports_vision"):
        print("\n⚠️ 配置不支持 Vision，跳过")
        return

    import asyncio
    import aiosqlite
    import backend.database as database

    print("\n" + "=" * 70)
    print("测试: Vision 图片描述详细分析")

    async def _query():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content, page_id, element_type FROM page_elements WHERE element_type = 'Picture' LIMIT 3"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows] if rows else []

    pics = asyncio.run(_query())
    if not pics:
        print("⚠️ 数据库中没有图片元素，查找本地测试图片")
        candidates = list(Path("data").rglob("*.jpg")) + list(Path("data").rglob("*.png"))
        if not candidates:
            print("❌ 也没有找到任何测试图片，跳过 Vision 测试")
            return
        image_path = str(candidates[0])
        print(f"用找到的本地图片: {image_path}")
    else:
        image_path = pics[0]["content"]
        print(f"找到图片元素 id={pics[0]['id']}, path={image_path}")

    if not Path(image_path).exists():
        print(f"❌ 图片不存在: {image_path}")
        return

    from backend.services.llm_service import _build_url
    url = _build_url(cfg.get("base_url", ""))

    file_size = Path(image_path).stat().st_size
    print(f"图片路径: {image_path}")
    print(f"文件大小: {file_size} 字节")

    base64_image = _encode_image_file(image_path)
    ext = Path(image_path).suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")
    print(f"MIME: {mime_type}, base64 长度: {len(base64_image)}")

    test_cases = [
        {
            "name": "格式1: 先文本后图片",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "用中文简短描述这张图片的内容。要求直接输出描述，不要任何前缀。"},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                    ],
                }
            ],
        },
        {
            "name": "格式2: 先图片后文本",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{base64_image}"}},
                        {"type": "text", "text": "用中文简短描述这张图片的内容。要求直接输出描述，不要任何前缀。"},
                    ],
                }
            ],
        },
    ]

    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key", "")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    for tc in test_cases:
        print(f"\n{'='*50}")
        print(f"--- {tc['name']} ---")
        payload = {
            "model": cfg.get("model", "gpt-4o"),
            "messages": tc["messages"],
            "temperature": 0.3,
            "max_tokens": cfg.get("max_tokens", 4096),
            "stream": False,
        }
        data = json.dumps(payload).encode("utf-8")
        print(f"请求体大小: {len(data)/1024:.1f} KB")
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")

        try:
            print("发送请求...")
            with urllib.request.urlopen(req, timeout=600) as resp:
                raw = resp.read().decode("utf-8")
            print(f"响应长度: {len(raw)}")
            result = json.loads(raw)
            if "choices" in result and len(result["choices"]) > 0:
                choice = result["choices"][0]
                print(f"finish_reason: {choice.get('finish_reason')}")
                msg = choice.get("message", {})
                content = _extract_content_from_response(msg)
                reasoning = msg.get("reasoning_content", "")
                if reasoning:
                    print(f"\n--- reasoning_content 末尾 (500 chars) ---")
                    print(reasoning[-500:])
                print(f"\n--- 提取到的内容 ({len(content)} 字符) ---")
                print(repr(content[:300]))
                if len(content) > 0:
                    print(f"✓ 成功! 这种格式可用。")
                    return tc
            else:
                print(f"响应: {json.dumps(result, ensure_ascii=False)[:300]}")
        except Exception as e:
            print(f"失败: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("\n❌ 所有 Vision 格式都失败")
    return None


if __name__ == "__main__":
    cfg = test_llm_detailed()
    if cfg:
        test_vision_detailed(cfg)
