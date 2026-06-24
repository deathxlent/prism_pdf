"""Export all data from data.db to JSON format for demo."""
import sqlite3
import json
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "data.db"
OUTPUT_PATH = Path(__file__).parent / "demo" / "js" / "mock-data.js"

def export_data():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all documents
    cursor.execute("SELECT * FROM pdf_documents ORDER BY created_at DESC")
    documents = [dict(row) for row in cursor.fetchall()]
    
    result = {
        "documents": [],
        "exported_at": "2026-06-23"
    }
    
    for doc in documents:
        doc_data = {
            "id": doc["id"],
            "filename": doc["filename"],
            "original_filename": doc["original_filename"],
            "file_size": doc["file_size"],
            "page_count": doc["page_count"],
            "is_encrypted": doc["is_encrypted"],
            "status": doc["status"],
            "error_message": doc["error_message"],
            "created_at": doc["created_at"],
            "updated_at": doc["updated_at"],
            "pages": []
        }
        
        # Get pages for this document
        cursor.execute(
            "SELECT * FROM pdf_pages WHERE document_id = ? ORDER BY page_number",
            (doc["id"],)
        )
        pages = [dict(row) for row in cursor.fetchall()]
        
        for page in pages:
            page_data = {
                "id": page["id"],
                "document_id": page["document_id"],
                "page_number": page["page_number"],
                "width": page["width"],
                "height": page["height"],
                "jpg_width": page["jpg_width"],
                "jpg_height": page["jpg_height"],
                "is_scanned": page["is_scanned"],
                "jpg_path": page["jpg_path"],
                "single_pdf_path": page["single_pdf_path"],
                "status": page["status"],
                "error_message": page["error_message"],
                "created_at": page["created_at"],
                "updated_at": page["updated_at"],
                "is_ordered": page.get("is_ordered", 1),
                "header_y_threshold": page.get("header_y_threshold"),
                "footer_y_threshold": page.get("footer_y_threshold"),
                "elements": []
            }
            
            # Get elements for this page
            cursor.execute(
                "SELECT * FROM page_elements WHERE page_id = ? ORDER BY reading_order",
                (page["id"],)
            )
            elements = [dict(row) for row in cursor.fetchall()]
            
            for elem in elements:
                elem_data = {
                    "id": elem["id"],
                    "page_id": elem["page_id"],
                    "element_type": elem["element_type"],
                    "bbox_x0": elem["bbox_x0"],
                    "bbox_y0": elem["bbox_y0"],
                    "bbox_x1": elem["bbox_x1"],
                    "bbox_y1": elem["bbox_y1"],
                    "confidence": elem["confidence"],
                    "reading_order": elem["reading_order"],
                    "content": elem["content"],
                    "content_format": elem["content_format"],
                    "created_at": elem["created_at"],
                    "cross_page_group": elem.get("cross_page_group"),
                    "image_description": elem.get("image_description"),
                    "translated_content": elem.get("translated_content"),
                    "header_footer_mark": elem.get("header_footer_mark")
                }
                page_data["elements"].append(elem_data)
            
            doc_data["pages"].append(page_data)
        
        result["documents"].append(doc_data)
    
    conn.close()
    
    # Ensure output directory exists
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to JS file
    js_content = f"// Auto-generated mock data for demo\n// Exported at: {result['exported_at']}\n\nconst MOCK_DATA = {json.dumps(result, ensure_ascii=False, indent=2)};\n\nif (typeof module !== 'undefined' && module.exports) {{\n    module.exports = MOCK_DATA;\n}}\n"
    
    OUTPUT_PATH.write_text(js_content, encoding="utf-8")
    
    print(f"✅ Exported {len(result['documents'])} documents")
    for doc in result['documents']:
        print(f"  - {doc['original_filename']}: {len(doc['pages'])} pages")
        for page in doc['pages']:
            print(f"    Page {page['page_number']}: {len(page['elements'])} elements")
    
    print(f"\n📁 Output: {OUTPUT_PATH}")

if __name__ == "__main__":
    export_data()
