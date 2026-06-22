import logging
import aiosqlite
from datetime import datetime
from pathlib import Path

from backend.config import DB_PATH
from backend import database as db

logger = logging.getLogger(__name__)


async def update_element(element_id: int, data: dict) -> dict:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Element not found")

        updates = {}
        if "content" in data:
            updates["content"] = data["content"]
        if "reading_order" in data:
            updates["reading_order"] = data["reading_order"]
        if "element_type" in data:
            updates["element_type"] = data["element_type"]
        if "image_description" in data:
            updates["image_description"] = data["image_description"]
        if "translated_content" in data:
            updates["translated_content"] = data["translated_content"]

        if updates:
            sets = ", ".join(f"{k} = ?" for k in updates)
            vals = list(updates.values()) + [element_id]
            await conn.execute(f"UPDATE page_elements SET {sets} WHERE id = ?", vals)
            await conn.commit()

        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        return dict(row)


async def delete_element(element_id: int) -> None:
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        if not row:
            raise ValueError("Element not found")

        await conn.execute("DELETE FROM page_elements WHERE id = ?", (element_id,))
        await conn.commit()


async def create_element(page_id: int, data: dict) -> dict:
    page = await db.get_page(page_id)
    if not page:
        raise ValueError("Page not found")

    element_type = data.get("element_type", "Text")
    bbox = data.get("bbox")
    content = data.get("content", "")
    content_format = data.get("content_format", "markdown")
    confidence = data.get("confidence", 1.0)

    if not bbox or len(bbox) != 4:
        raise ValueError("bbox is required and must have 4 values")

    elements = await db.get_elements(page_id)
    reading_order = len(elements)

    element_id = await db.create_element(
        page_id, element_type, tuple(bbox), confidence, reading_order,
        content=content, content_format=content_format
    )

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        cursor = await conn.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        return dict(row)


async def reorder_elements(page_id: int, element_order: list[int]) -> None:
    if not element_order:
        raise ValueError("element_order is required")

    async with aiosqlite.connect(str(DB_PATH)) as conn:
        for idx, elem_id in enumerate(element_order):
            await conn.execute(
                "UPDATE page_elements SET reading_order = ? WHERE id = ? AND page_id = ?",
                (idx, elem_id, page_id)
            )
        await conn.execute(
            "UPDATE pdf_pages SET is_ordered = 1, updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), page_id)
        )
        await conn.commit()


async def describe_image_element(element_id: int) -> dict:
    from backend.services.llm_service import describe_image

    element = await db.get_element(element_id)
    if not element:
        raise ValueError("Element not found")

    if element["element_type"] != "Picture":
        raise ValueError("Only Picture elements can be described")

    image_path = element.get("content", "") or ""
    if not image_path or not Path(image_path).exists():
        raise ValueError("图片文件不存在")

    description = describe_image(image_path)
    await db.update_element(element_id, image_description=description)
    return {"element_id": element_id, "image_description": description}


async def translate_element(element_id: int, target_language: str = "en") -> dict:
    from backend.services.llm_service import translate_text

    element = await db.get_element(element_id)
    if not element:
        raise ValueError("Element not found")

    etype = element.get("element_type", "")
    content = element.get("content", "") or ""
    image_desc = element.get("image_description", "") or ""

    text_to_translate = ""
    if etype == "Picture":
        if image_desc:
            text_to_translate = image_desc
        else:
            raise ValueError("图片元素无描述，请先生成图片描述")
    else:
        if not content.strip():
            raise ValueError("元素内容为空，无法翻译")
        text_to_translate = content

    translated = translate_text(text_to_translate, target_language)
    await db.update_element(element_id, translated_content=translated)
    return {"element_id": element_id, "translated_content": translated}
