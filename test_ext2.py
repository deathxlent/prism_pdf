import json
import sys
import urllib.request
from pathlib import Path

API = "http://localhost:8888/api"

def test_edit_with_translation():
    print("=" * 70)
    print("测试: 编辑元素时保存译文")
    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_translated_elem():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content, translated_content, element_type FROM page_elements "
                "WHERE translated_content IS NOT NULL AND translated_content != '' LIMIT 1"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows] if rows else []

    elems = asyncio.run(find_translated_elem())
    if not elems:
        print("没有找到有译文的元素")
        return False

    elem = elems[0]
    elem_id = elem["id"]
    print(f"元素 ID={elem_id}, 类型={elem['element_type']}")
    print(f"原文: {elem['content'][:80]}")
    print(f"译文: {elem['translated_content'][:80]}")

    new_translated = "This is a modified translation for testing."
    update_data = json.dumps({
        "element_type": elem["element_type"],
        "content": elem["content"],
        "translated_content": new_translated
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API}/elements/{elem_id}",
        data=update_data,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        actual = result.get("translated_content", "")
        if actual == new_translated:
            print(f"\n✓ 译文更新成功: {actual}")

            orig_data = json.dumps({
                "element_type": elem["element_type"],
                "content": elem["content"],
                "translated_content": elem["translated_content"]
            }).encode("utf-8")
            req2 = urllib.request.Request(
                f"{API}/elements/{elem_id}",
                data=orig_data,
                headers={"Content-Type": "application/json"},
                method="PUT"
            )
            with urllib.request.urlopen(req2, timeout=30) as resp2:
                pass
            print("✓ 已恢复原始译文")
            return True
        else:
            print(f"❌ 译文不匹配: 期望 '{new_translated}', 实际 '{actual}'")
            return False
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ HTTP {e.code}: {err_body}")
        return False
    except Exception as e:
        print(f"❌ 更新失败: {type(e).__name__}: {e}")
        return False


def test_get_element_with_translated():
    print("\n" + "=" * 70)
    print("测试: GET 元素包含 translated_content 字段")
    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_any_elem():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM page_elements LIMIT 1"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows] if rows else []

    elems = asyncio.run(find_any_elem())
    if not elems:
        print("❌ 没有元素")
        return False

    elem_id = elems[0]["id"]
    req = urllib.request.Request(f"{API}/elements/{elem_id}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        has_translated = "translated_content" in result
        has_desc = "image_description" in result
        print(f"元素 ID={elem_id}")
        print(f"  translated_content 字段存在: {has_translated}")
        print(f"  image_description 字段存在: {has_desc}")
        if has_translated and has_desc:
            print("✓ API 返回了完整的字段")
            return True
        else:
            print("❌ 缺少字段")
            return False
    except Exception as e:
        print(f"❌ 失败: {e}")
        return False


if __name__ == "__main__":
    test_get_element_with_translated()
    test_edit_with_translation()
