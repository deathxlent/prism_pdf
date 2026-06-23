import asyncio
import aiosqlite
from pathlib import Path

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS pdf_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    page_count INTEGER NOT NULL DEFAULT 0,
    is_encrypted INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'uploaded',
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pdf_pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    width REAL NOT NULL DEFAULT 0,
    height REAL NOT NULL DEFAULT 0,
    jpg_width REAL NOT NULL DEFAULT 0,
    jpg_height REAL NOT NULL DEFAULT 0,
    is_scanned INTEGER NOT NULL DEFAULT 0,
    jpg_path TEXT,
    single_pdf_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (document_id) REFERENCES pdf_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS page_elements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    page_id INTEGER NOT NULL,
    element_type TEXT NOT NULL,
    bbox_x0 REAL NOT NULL DEFAULT 0,
    bbox_y0 REAL NOT NULL DEFAULT 0,
    bbox_x1 REAL NOT NULL DEFAULT 0,
    bbox_y1 REAL NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    reading_order INTEGER NOT NULL DEFAULT 0,
    content TEXT,
    cross_page_group INTEGER,
    image_description TEXT,
    translated_content TEXT,
    FOREIGN KEY (page_id) REFERENCES pdf_pages(id) ON DELETE CASCADE
);
"""

DB_PATH = Path(__file__).resolve().parent / "db.sqlite3"

async def create_db():
    # 确保目录存在
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
        print("Database tables created successfully!")

if __name__ == "__main__":
    asyncio.run(create_db())
