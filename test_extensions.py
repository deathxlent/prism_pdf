import json
import sys
import urllib.request
from pathlib import Path

API = "http://localhost:8888/api"


def test_edit_with_translation():
    print("=" * 70)
    print("测试1: 编辑元素时保存译文")
    import aiosqlite
    import asyncio
    sys.path.insert(0, str(Path(__file__).parent))
    import backend.database as database

    async def find_translated_elem():
        await database.init_db()
        async with aiosqlite.connect(database.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, content, translated_content FROM page_elements "
                "WHERE translated_content IS NOT NULL AND translated_content != '' LIMIT 1"
            ) as cur:
                rows = await cur.fetchall()
                return [dict(r) for r in rows] if rows else []

    elems = asyncio.run(find_translated_elem())
    if not elems:
        print("没有找到有译文的元素，先找一个元素做翻译测试...")

        async def find_any_elem():
            await database.init_db()
            async with aiosqlite.connect(database.DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT id, content FROM page_elements "
                    "WHERE element_type != 'Picture' AND content IS NOT NULL AND length(content) > 5 LIMIT 1"
                ) as cur:
                    rows = await cur.fetchall()
                    return [dict(r) for r in rows] if rows else []

        elems2 = asyncio.run(find_any_elem())
        if not elems2:
            print("❌ 数据库没有元素")
            return False
        elem_id = elems2[0]["id"]
        print(f"先用元素 {elem_id} 做翻译...")
        url = f"{API}/elements/{elem_id}/translate"
        data = json.dumps({"target_language": "en"}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=1800) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            print(f"翻译成功: {result.get('translated_content', '')[:80]}")
            elem_id = result["element_id"]
        except Exception as e:
            print(f"❌ 翻译失败: {e}")
            return False
    else:
        elem_id = elems[0]["id"]
        print(f"已有译文元素 ID={elem_id}")
        print(f"原文: {elems[0]['content'][:80]}")
        print(f"译文: {elems[0]['translated_content'][:80]}")

    print(f"\n测试 PUT 更新译文...")
    new_translated = "This is a modified translation for testing."
    update_data = json.dumps({
        "element_type": "Text",
        "content": elems[0]["content"] if elems else "test",
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
        actual_translated = result.get("translated_content", "")
        if actual_translated == new_translated:
            print(f"✓ 译文更新成功: {actual_translated}")
            return True
        else:
            print(f"❌ 译文不匹配: 期望 '{new_translated}', 实际 '{actual_translated}'")
            return False
    except Exception as e:
        print(f"❌ 更新失败: {e}")
        return False


def test_vision_available():
    print("\n" + "=" * 70)
    print("测试2: is_vision_available 函数")
    sys.path.insert(0, str(Path(__file__).parent))
    from backend.services.llm_service import is_vision_available
    result = is_vision_available()
    print(f"is_vision_available() = {result}")
    return result


def test_describe_silent():
    print("\n" + "=" * 70)
    print("测试3: describe_image_silent 函数")
    sys.path.insert(0, str(Path(__file__).parent))
    from backend.services.llm_service import describe_image_silent

    image_path = r"G:\ws\Prism PDF\tmp\ae3365ca461941228d683de19c0e3e31\output\picture_3660001.png"
    if not Path(image_path).exists():
        print(f"❌ 图片不存在: {image_path}")
        return False

    print(f"用图片: {image_path}")
    result = describe_image_silent(image_path)
    if result:
        print(f"✓ describe_image_silent 成功 ({len(result)} 字符):")
        print(result[:200])
        return True
    else:
        print("❌ describe_image_silent 返回 None")
        return False


if __name__ == "__main__":
    test_vision_available()
    test_edit_with_translation()
    test_describe_silent()
