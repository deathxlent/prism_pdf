import asyncio
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.config import DB_PATH
from backend import database as db

async def verify():
    print(f"Database path: {DB_PATH}")
    print(f"Database exists: {Path(DB_PATH).exists()}")
    
    await db.init_db()
    
    async with aiosqlite.connect(str(DB_PATH)) as conn:
        cursor = await conn.execute("PRAGMA table_info(pdf_pages)")
        columns = await cursor.fetchall()
        print("\npdf_pages 表列结构:")
        for col in columns:
            print(f"  {col[1]}: {col[2]} (nullable: {'YES' if col[3] == 0 else 'NO'})")
        
        col_names = [col[1] for col in columns]
        has_updated_at = 'updated_at' in col_names
        has_is_ordered = 'is_ordered' in col_names
        
        print(f"\nupdated_at 列存在: {has_updated_at}")
        print(f"is_ordered 列存在: {has_is_ordered}")
        
        cursor = await conn.execute("SELECT COUNT(*) FROM pdf_pages")
        count = await cursor.fetchone()
        print(f"\npdf_pages 表记录数: {count[0]}")
        
        if has_updated_at and count[0] > 0:
            cursor = await conn.execute("SELECT id, created_at, updated_at, is_ordered FROM pdf_pages LIMIT 5")
            rows = await cursor.fetchall()
            print("\npdf_pages 示例记录:")
            for row in rows:
                print(f"  id={row[0]}, created_at={row[1]}, updated_at={row[2]}, is_ordered={row[3]}")

    print("\n修复验证完成!")

if __name__ == "__main__":
    asyncio.run(verify())
