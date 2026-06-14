import aiosqlite
from datetime import datetime
from backend.config import DB_PATH

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
    content_format TEXT NOT NULL DEFAULT 'markdown',
    created_at TEXT NOT NULL,
    FOREIGN KEY (page_id) REFERENCES pdf_pages(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_pages_document ON pdf_pages(document_id);
CREATE INDEX IF NOT EXISTS idx_elements_page ON page_elements(page_id);
CREATE INDEX IF NOT EXISTS idx_elements_type ON page_elements(element_type);
"""


def _now():
    return datetime.now().isoformat()


async def init_db():
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.executescript(CREATE_TABLES_SQL)
        
        try:
            await db.execute("ALTER TABLE pdf_pages ADD COLUMN jpg_width REAL NOT NULL DEFAULT 0")
        except aiosqlite.OperationalError:
            pass
        
        try:
            await db.execute("ALTER TABLE pdf_pages ADD COLUMN jpg_height REAL NOT NULL DEFAULT 0")
        except aiosqlite.OperationalError:
            pass

        try:
            await db.execute("ALTER TABLE page_elements ADD COLUMN cross_page_group INTEGER")
        except aiosqlite.OperationalError:
            pass
        
        await db.commit()


async def create_document(filename: str, original_filename: str, file_path: str, file_size: int) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """INSERT INTO pdf_documents
               (filename, original_filename, file_path, file_size, page_count, is_encrypted, status, created_at, updated_at)
               VALUES (?, ?, ?, ?, 0, 0, 'uploaded', ?, ?)""",
            (filename, original_filename, file_path, file_size, _now(), _now()),
        )
        await db.commit()
        return cursor.lastrowid


async def update_document(doc_id: int, **kwargs):
    kwargs["updated_at"] = _now()
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [doc_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE pdf_documents SET {sets} WHERE id = ?", vals)
        await db.commit()


async def get_document(doc_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pdf_documents WHERE id = ?", (doc_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def list_documents() -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pdf_documents ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def create_page(document_id: int, page_number: int, width: float, height: float,
                      jpg_width: float = 0, jpg_height: float = 0,
                      jpg_path: str = None, single_pdf_path: str = None) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """INSERT INTO pdf_pages
               (document_id, page_number, width, height, jpg_width, jpg_height, is_scanned, jpg_path, single_pdf_path, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, 'pending', ?)""",
            (document_id, page_number, width, height, jpg_width, jpg_height, jpg_path, single_pdf_path, _now()),
        )
        await db.commit()
        return cursor.lastrowid


async def update_page(page_id: int, **kwargs):
    kwargs.setdefault("updated_at", _now()) if "updated_at" in kwargs else None
    if "updated_at" not in kwargs:
        pass
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [page_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE pdf_pages SET {sets} WHERE id = ?", vals)
        await db.commit()


async def get_pages(document_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM pdf_pages WHERE document_id = ? ORDER BY page_number",
            (document_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_page(page_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM pdf_pages WHERE id = ?", (page_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_element(page_id: int, element_type: str, bbox: tuple[float, float, float, float],
                         confidence: float, reading_order: int, content: str = None,
                         content_format: str = "markdown", cross_page_group: int = None) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cursor = await db.execute(
            """INSERT INTO page_elements
               (page_id, element_type, bbox_x0, bbox_y0, bbox_x1, bbox_y1,
                confidence, reading_order, content, content_format, cross_page_group, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (page_id, element_type, bbox[0], bbox[1], bbox[2], bbox[3],
             confidence, reading_order, content, content_format, cross_page_group, _now()),
        )
        await db.commit()
        return cursor.lastrowid


async def get_elements(page_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM page_elements WHERE page_id = ? ORDER BY reading_order",
            (page_id,),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_elements_by_type(page_id: int, element_type: str) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM page_elements WHERE page_id = ? AND element_type = ? ORDER BY reading_order",
            (page_id, element_type),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def delete_document(doc_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM page_elements WHERE page_id IN (SELECT id FROM pdf_pages WHERE document_id = ?)", (doc_id,))
        await db.execute("DELETE FROM pdf_pages WHERE document_id = ?", (doc_id,))
        await db.execute("DELETE FROM pdf_documents WHERE id = ?", (doc_id,))
        await db.commit()


async def update_element_cross_page_group(element_id: int, cross_page_group: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE page_elements SET cross_page_group = ? WHERE id = ?",
            (cross_page_group, element_id),
        )
        await db.commit()


async def execute_query(sql: str, params: tuple = ()):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(sql, params)
        await db.commit()


async def update_element(element_id: int, **kwargs):
    sets = ", ".join(f"{k} = ?" for k in kwargs)
    vals = list(kwargs.values()) + [element_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(f"UPDATE page_elements SET {sets} WHERE id = ?", vals)
        await db.commit()


async def get_element(element_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM page_elements WHERE id = ?", (element_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
