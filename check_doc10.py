import aiosqlite
import asyncio

async def check():
    async with aiosqlite.connect('data.db') as db:
        db.row_factory = aiosqlite.Row
        
        # 获取文档信息
        cursor = await db.execute('SELECT * FROM pdf_documents WHERE id = 10')
        doc = await cursor.fetchone()
        if doc:
            print('=== Document id=10 ===')
            doc_dict = dict(doc)
            for k, v in doc_dict.items():
                print(f'  {k}: {v}')
        else:
            print('Document 10 not found')
            return
            
        # 获取页面信息
        cursor = await db.execute('SELECT * FROM pdf_pages WHERE document_id = 10 ORDER BY page_number')
        pages = await cursor.fetchall()
        print(f'\n=== Pages (count: {len(pages)}) ===')
        for p in pages:
            pd = dict(p)
            page_id = pd['id']
            pn = pd['page_number']
            iscan = pd['is_scanned']
            print(f'Page {pn}: id={page_id}, is_scanned={iscan}, status={pd["status"]}, size={pd["width"]}x{pd["height"]}, jpg={pd["jpg_width"]}x{pd["jpg_height"]}')
            
            # 获取元素
            cursor2 = await db.execute('SELECT * FROM page_elements WHERE page_id = ? ORDER BY reading_order', (page_id,))
            elems = await cursor2.fetchall()
            print(f'  Elements count: {len(elems)}')
            for e in elems:
                ed = dict(e)
                content_preview = (ed.get('content', '') or '')[:150].replace('\n', ' | ')
                fmt = ed.get('content_format', '')
                cross = ed.get('cross_page_group', '')
                cross_str = f' cross={cross}' if cross else ''
                print(f'    #{ed["reading_order"]:2d} [{ed["element_type"]:15s}] conf={ed["confidence"]:.2f} bbox=({ed["bbox_x0"]:.0f},{ed["bbox_y0"]:.0f},{ed["bbox_x1"]:.0f},{ed["bbox_y1"]:.0f}) format={fmt}{cross_str}')
                print(f'       Content: {content_preview}')
                if ed['element_type'] == 'Table' and ed.get('content'):
                    print(f'       Table HTML length: {len(ed["content"])} chars')

asyncio.run(check())
