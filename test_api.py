import json
import sys
import urllib.request
from pathlib import Path

API = "http://localhost:8888/api"


def test_describe_image_api():
    print("=" * 70)
    print("测试: describe_image API")

    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_pic():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content FROM page_elements WHERE element_type = 'Picture' LIMIT 5"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows] if rows else []

    pics = asyncio.run(find_pic())

    if not pics:
        print("❌ 没有找到图片元素")
        return

    valid_pic = None
    for p in pics:
        if p["content"] and Path(p["content"]).exists():
            valid_pic = p
            break

    if not valid_pic:
        # 找一个本地图片作为替换测试
        candidates = list(Path(r"G:\ws\Prism PDF\tmp").rglob("*.png")) + list(Path(r"G:\ws\Prism PDF\tmp").rglob("*.jpg"))
        if not candidates:
            print("❌ 没有找到有效的图片")
            return
        # 把找到的本地图片路径更新到数据库，或者只找一个真实存在的
        for p in pics:
            for c in candidates:
                if Path(p["content"]).name == c.name:
                    valid_pic = {"id": p["id"], "content": str(c)}
                    break
            if valid_pic:
                break

    if not valid_pic:
        print("❌ 数据库图片路径都不存在，用一个新的图片更新数据库...")
        print("（跳过此测试，直接测试翻译 API）")
        return

    elem_id = valid_pic["id"]
    print(f"用元素 ID={elem_id}, 路径={valid_pic['content']}")

    url = f"{API}/elements/{elem_id}/describe-image"
    print(f"请求 URL: {url}")
    req = urllib.request.Request(url, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            print(f"\n✓ API 成功!")
            print(f"element_id: {result.get('element_id')}")
            desc = result.get("image_description", "")
            print(f"描述长度: {len(desc)}")
            print(f"描述内容:\n{desc}")
            return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP {e.code}: {err_body}")
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    return False


def test_translate_element_api():
    print("\n" + "=" * 70)
    print("测试: translate_element API")

    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_text():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content, element_type FROM page_elements "
                "WHERE element_type != 'Picture' AND content IS NOT NULL AND length(content) > 5 "
                "LIMIT 5"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows] if rows else []

    elems = asyncio.run(find_text())
    if not elems:
        print("❌ 没有找到文字元素")
        return False

    elem = elems[0]
    elem_id = elem["id"]
    print(f"用元素 ID={elem_id}, 类型={elem['element_type']}")
    print(f"原内容: {elem['content'][:100]}...")

    url = f"{API}/elements/{elem_id}/translate"
    data = json.dumps({"target_language": "en"}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            raw = resp.read().decode("utf-8")
            result = json.loads(raw)
            print(f"\n✓ API 成功!")
            print(f"element_id: {result.get('element_id')}")
            trans = result.get("translated_content", "")
            print(f"翻译长度: {len(trans)}")
            print(f"翻译内容:\n{trans}")
            return True
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP {e.code}: {err_body}")
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    return False


if __name__ == "__main__":
    test_describe_image_api()
    test_translate_element_api()
