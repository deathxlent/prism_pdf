import aiosqlite, asyncio, re

async def check():
    async with aiosqlite.connect('data.db') as db:
        db.row_factory = aiosqlite.Row
        
        cursor = await db.execute('SELECT * FROM page_elements WHERE page_id=260 AND element_type="Table" ORDER BY reading_order')
        rows = await cursor.fetchall()
        for r in rows:
            rd = dict(r)
            content = rd['content']
            tr_pat = re.compile(r'<tr[^>]*>(.*?)</tr>', re.DOTALL | re.IGNORECASE)
            cell_pat = re.compile(r'<t[hd][^>]*>(.*?)</t[hd]>', re.IGNORECASE)
            print(f"=== Table id={rd['id']}, ro={rd['reading_order']} ===")
            for tri, tr_match in enumerate(tr_pat.finditer(content)):
                tr_html = tr_match.group(1)
                cells = []
                for cm in cell_pat.finditer(tr_html):
                    cells.append(re.sub(r'<[^>]+>', '', cm.group(1)).strip())
                print(f"  Row {tri}: {cells}")
            print()

asyncio.run(check())
