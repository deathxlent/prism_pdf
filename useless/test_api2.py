import json
import sys
import urllib.request
from pathlib import Path
import aiosqlite
import asyncio

sys.path.insert(0, str(Path(__file__).parent))
import backend.database as database

API = "http://localhost:8888/api"


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

    if elems:
        return elems[0]
    return None


async def find_valid_pic():
    await database.init_db()
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, content, element_type FROM page_elements "
            "WHERE element_type = 'Picture' LIMIT 20"
        ) as cur:
            rows = await cur.fetchall()
            pics = [dict(r) for r in rows] if rows else []

    for p in pics:
        content = p.get("content", "") or ""
        if content and Path(content).exists():
            return p
    return None


def test_translate_chinese():
    elem = asyncio.run(find_chinese_elem())
    if not elem:
        print("❌ 没有找到元素")
        return False

    print(f"测试翻译元素 ID={elem['id']}, 类型={elem['element_type']}")
    content = elem.get("content", "")
    print(f"原内容 ({len(content)} 字符):\n{content[:200]}")

    url = f"{API}/elements/{elem['id']}/translate"
    for lang, lang_name in [("en", "英语"), ("ja", "日语")]:
        print(f"\n--- 翻译成 {lang_name} ---")
        data = json.dumps({"target_language": lang}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            trans = result.get("translated_content", "")
            print(f"翻译结果 ({len(trans)} 字符):\n{trans[:200]}")
        except Exception as e:
            print(f"❌ 失败: {e}")

    return True


def test_describe_valid_pic():
    pic = asyncio.run(find_valid_pic())
    if not pic:
        print("❌ 没有找到有效图片")
        return False

    print(f"\n测试图片描述 ID={pic['id']}")
    print(f"图片路径: {pic['content']}")
    print(f"存在: {Path(pic['content']).exists()}, 大小: {Path(pic['content']).stat().st_size}")

    url = f"{API}/elements/{pic['id']}/describe-image"
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        desc = result.get("image_description", "")
        print(f"✓ 图片描述成功 ({len(desc)} 字符):\n{desc}")
        return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP {e.code}: {err_body}")
    except Exception as e:
        print(f"❌ 失败: {e}")
        import traceback
        traceback.print_exc()
    return False


if __name__ == "__main__":
    test_translate_chinese()
    test_describe_valid_pic()
