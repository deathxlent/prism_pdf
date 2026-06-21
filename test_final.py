import json
import sys
import urllib.request
from pathlib import Path
import time

API = "http://localhost:8888/api"

def test_describe_image_api():
    print("=" * 70)
    print("测试: describe_image API (timeout=3600s)")
    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_valid_pic():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content FROM page_elements WHERE element_type = 'Picture' LIMIT 20"
            ) as cur:
                rows = await cur.fetchall()
                pics = [dict(r) for r in rows] if rows else []

        for p in pics:
            content = p.get("content", "") or ""
            if content and Path(content).exists():
                return p
        return None

    pic = asyncio.run(find_valid_pic())
    if not pic:
        print("❌ 没有找到有效图片")
        return False

    elem_id = pic["id"]
    print(f"用元素 ID={elem_id}")
    print(f"图片路径: {pic['content']}")
    print(f"存在: {Path(pic['content']).exists()}, 大小: {Path(pic['content']).stat().st_size}")

    url = f"{API}/elements/{elem_id}/describe-image"
    req = urllib.request.Request(url, method="POST")

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
        elapsed = time.time() - start_time
        print(f"\n✓ API 成功! 耗时: {elapsed:.1f} 秒")
        desc = result.get("image_description", "")
        print(f"描述长度: {len(desc)} 字符")
        print("=" * 70)
        print(desc)
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP {e.code}: {err_body}")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 失败 ({elapsed:.1f}s): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    return False


def test_translate_element_api():
    print("\n" + "=" * 70)
    print("测试: translate_element API (timeout=1800s)")
    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_chinese_elem():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content, element_type FROM page_elements "
                "WHERE element_type != 'Picture' AND content IS NOT NULL "
                "LIMIT 30"
            ) as cur:
                rows = await cur.fetchall()
                elems = [dict(r) for r in rows] if rows else []

        for e in elems:
            content = e.get("content", "") or ""
            has_chinese = any('\u4e00' <= c <= '\u9fff' for c in content)
            if has_chinese and len(content) > 5:
                return e
        return elems[0] if elems else None

    elem = asyncio.run(find_chinese_elem())
    if not elem:
        print("❌ 没有找到元素")
        return False

    elem_id = elem["id"]
    print(f"用元素 ID={elem_id}, 类型={elem['element_type']}")
    content = elem.get("content", "")
    print(f"原内容: {content[:100]}...")

    url = f"{API}/elements/{elem_id}/translate"
    data = json.dumps({"target_language": "en"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    start_time = time.time()
    try:
        with urllib.request.urlopen(req, timeout=1800) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
        elapsed = time.time() - start_time
        print(f"\n✓ API 成功! 耗时: {elapsed:.1f} 秒")
        trans = result.get("translated_content", "")
        print(f"翻译长度: {len(trans)} 字符")
        print("=" * 70)
        print(f"原文:\n{content}")
        print("-" * 50)
        print(f"翻译:\n{trans}")
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP {e.code}: {err_body}")
    except Exception as e:
        elapsed = time.time() - start_time
        print(f"❌ 失败 ({elapsed:.1f}s): {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    return False


if __name__ == "__main__":
    test_translate_element_api()
    test_describe_image_api()
