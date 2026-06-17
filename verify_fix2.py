import asyncio
import aiosqlite
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from backend.config import DB_PATH

async def fix_empty_updated_at():
    print("修复现有记录中为空的 updated_at...")
    
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM pdf_pages WHERE updated_at IS NULL OR updated_at = ''"
        )
        count = await cursor.fetchone()
        print(f"需要修复的记录数: {count[0]}")
        
        if count[0] > 0:
            await conn.execute(
                "UPDATE pdf_pages SET updated_at = created_at WHERE updated_at IS NULL OR updated_at = ''"
            )
            await conn.commit()
            print(f"已修复 {count[0]} 条记录的 updated_at 字段")

async def test_reorder_query():
    print("\n测试排序 SQL 语句...")
    
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        conn.row_factory = aiosqlite.Row
        
        cursor = await conn.execute("SELECT id FROM pdf_pages LIMIT 1")
        row = await cursor.fetchone()
        if not row:
            print("没有测试数据，跳过查询测试")
            return
        
        test_page_id = row["id"]
        print(f"使用测试页面 ID: {test_page_id}")
        
        cursor = await conn.execute("SELECT id FROM page_elements WHERE page_id = ? LIMIT 5", (test_page_id,))
        elements = await cursor.fetchall()
        
        if elements:
            element_ids = [e["id"] for e in elements]
            print(f"找到元素: {element_ids}")
            
            for idx, elem_id in enumerate(element_ids):
                await conn.execute(
                    "UPDATE page_elements SET reading_order = ? WHERE id = ? AND page_id = ?",
                    (idx, elem_id, test_page_id)
                )
                print(f"  已更新元素 {elem_id} 的 reading_order = {idx}")
            
            now = datetime.now().isoformat()
            await conn.execute(
                "UPDATE pdf_pages SET is_ordered = 1, updated_at = ? WHERE id = ?",
                (now, test_page_id)
            )
            print(f"  已更新页面 {test_page_id} 的 is_ordered=1, updated_at={now}")
            
            await conn.commit()
            print("\n测试排序操作成功！没有报错。")
        else:
            print(f"页面 {test_page_id} 上没有元素，只测试更新 pdf_pages 表")
            now = datetime.now().isoformat()
            await conn.execute(
                "UPDATE pdf_pages SET is_ordered = 1, updated_at = ? WHERE id = ?",
                (now, test_page_id)
            )
            await conn.commit()
            print("测试更新 pdf_pages 表成功！没有报错。")

async def main():
    await fix_empty_updated_at()
    await test_reorder_query()
    print("\n全部验证通过！")

if __name__ == "__main__":
    asyncio.run(main())
