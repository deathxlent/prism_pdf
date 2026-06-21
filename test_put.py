import json
import urllib.request
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import asyncio
import aiosqlite
import backend.database as database

API = "http://localhost:8888/api"


async def setup_test_data():
    await database.init_db()
    doc_id = await database.create_document("test.pdf", "/tmp/test.pdf", 1, 1024)
    page_id = await database.create_page(doc_id, 1, 612, 792, 2480, 3508, "/tmp/test.jpg", "/tmp/test.pdf")
    elem_id = await database.create_element(
        page_id, "Text", (10, 10, 100, 30), 0.95, 1,
        content="Hello world", content_format="markdown"
    )
    return doc_id, page_id, elem_id


async def check_element(elem_id):
    async with aiosqlite.connect(database.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM page_elements WHERE id = ?", (elem_id,)) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None


def test_put_translation():
    print("Setting up test data...")
    doc_id, page_id, elem_id = asyncio.run(setup_test_data())
    print(f"Created doc={doc_id}, page={page_id}, elem={elem_id}")

    print("\n1. Testing PUT with translated_content...")
    update_data = json.dumps({
        "element_type": "Text",
        "content": "Hello world",
        "translated_content": "你好世界"
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{API}/elements/{elem_id}",
        data=update_data,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        translated = result.get("translated_content", "")
        print(f"  Response translated_content: '{translated}'")
        if translated == "你好世界":
            print("  ✓ PUT with translated_content works!")
        else:
            print(f"  ❌ Mismatch: expected '你好世界', got '{translated}'")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        print(f"  ❌ HTTP {e.code}: {err[:500]}")
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")

    print("\n2. Verifying in database...")
    elem = asyncio.run(check_element(elem_id))
    if elem:
        print(f"  DB translated_content: '{elem.get('translated_content', '')}'")
        print(f"  DB image_description: '{elem.get('image_description', '')}'")
    else:
        print("  ❌ Element not found in DB")

    print("\n3. Testing PUT with image_description...")
    update_data2 = json.dumps({
        "element_type": "Picture",
        "content": "/tmp/test.png",
        "image_description": "A test image description",
        "translated_content": "一张测试图片"
    }).encode("utf-8")

    req2 = urllib.request.Request(
        f"{API}/elements/{elem_id}",
        data=update_data2,
        headers={"Content-Type": "application/json"},
        method="PUT"
    )
    try:
        with urllib.request.urlopen(req2, timeout=10) as resp:
            result2 = json.loads(resp.read().decode("utf-8"))
        desc = result2.get("image_description", "")
        trans = result2.get("translated_content", "")
        print(f"  image_description: '{desc}'")
        print(f"  translated_content: '{trans}'")
        if desc == "A test image description" and trans == "一张测试图片":
            print("  ✓ All fields updated correctly!")
        else:
            print("  ❌ Some fields not updated correctly")
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="ignore")
        print(f"  ❌ HTTP {e.code}: {err[:500]}")
    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")


def test_llm_functions():
    print("\n" + "=" * 70)
    print("Testing LLM service functions...")
    from backend.services.llm_service import is_vision_available, describe_image_silent

    vision_ok = is_vision_available()
    print(f"is_vision_available() = {vision_ok}")

    img_path = r"G:\ws\Prism PDF\tmp\ae3365ca461941228d683de19c0e3e31\output\picture_3660001.png"
    if Path(img_path).exists():
        print(f"\ntest describe_image_silent('{img_path}')...")
        result = describe_image_silent(img_path)
        if result:
            print(f"  ✓ Success! ({len(result)} chars)")
            print(f"  {result[:200]}...")
        else:
            print(f"  ✗ Returned None")
    else:
        print(f"\nImage path not found, skipping describe test")


if __name__ == "__main__":
    test_put_translation()
    test_llm_functions()
