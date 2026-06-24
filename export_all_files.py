"""Call all export APIs and save files to demo/exports directory."""
import requests
import os
from pathlib import Path

BASE_URL = "http://localhost:8000"
EXPORTS_DIR = Path(__file__).parent / "demo" / "exports"
ASSETS_DIR = Path(__file__).parent / "demo" / "assets"

# Ensure directories exist
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

def download_file(url, output_path):
    """Download a file from URL and save to output_path."""
    print(f"  Downloading: {output_path.name}")
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        output_path.write_bytes(response.content)
        print(f"  ✅ Saved: {output_path.name} ({len(response.content)} bytes)")
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return False

def main():
    # Step 1: Get document ID
    print("📋 Fetching document list...")
    docs_res = requests.get(f"{BASE_URL}/api/documents")
    docs = docs_res.json()["documents"]
    
    if not docs:
        print("❌ No documents found!")
        return
    
    doc = docs[0]
    doc_id = doc["id"]
    print(f"📄 Document: {doc['original_filename']} (ID: {doc_id})")
    
    # Step 2: Get pages
    print("\n📑 Fetching pages...")
    results_res = requests.get(f"{BASE_URL}/api/results/{doc_id}")
    results = results_res.json()
    pages = results.get("pages", [])
    
    print(f"  Found {len(pages)} pages")
    
    # Step 3: Export document-level files
    print("\n📦 Exporting document-level files...")
    
    exports = [
        # Original exports
        (f"{BASE_URL}/api/documents/{doc_id}/export/html", "document.html"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/markdown", "document.md"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/html-zip", "document_pages.zip"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/rag-html", "document_rag.html"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/rag-html-zip", "document_rag_pages.zip"),
        
        # Translated exports
        (f"{BASE_URL}/api/documents/{doc_id}/export/translated/html", "document_translated.html"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/translated/markdown", "document_translated.md"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/translated/html-zip", "document_translated_pages.zip"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/translated/rag-html", "document_translated_rag.html"),
        (f"{BASE_URL}/api/documents/{doc_id}/export/translated/rag-html-zip", "document_translated_rag_pages.zip"),
    ]
    
    for url, filename in exports:
        output_path = EXPORTS_DIR / filename
        download_file(url, output_path)
    
    # Step 4: Export page-level files
    print("\n📄 Exporting page-level files...")
    
    for page in pages:
        page_id = page["id"]
        page_num = page["page_number"]
        print(f"\n  Page {page_num} (ID: {page_id}):")
        
        page_exports = [
            (f"{BASE_URL}/api/pages/{page_id}/export/html", f"page_{page_num}.html"),
            (f"{BASE_URL}/api/pages/{page_id}/export/markdown", f"page_{page_num}.md"),
            (f"{BASE_URL}/api/pages/{page_id}/export/rag-html", f"page_{page_num}_rag.html"),
            (f"{BASE_URL}/api/pages/{page_id}/export/translated/html", f"page_{page_num}_translated.html"),
            (f"{BASE_URL}/api/pages/{page_id}/export/translated/markdown", f"page_{page_num}_translated.md"),
            (f"{BASE_URL}/api/pages/{page_id}/export/translated/rag-html", f"page_{page_num}_translated_rag.html"),
        ]
        
        for url, filename in page_exports:
            output_path = EXPORTS_DIR / filename
            download_file(url, output_path)
    
    # Step 5: Copy page thumbnails
    print("\n🖼️  Copying page thumbnails...")
    
    for page in pages:
        page_id = page["id"]
        page_num = page["page_number"]
        
        # Download JPG
        jpg_url = f"{BASE_URL}/api/pages/{page_id}/jpg"
        jpg_path = ASSETS_DIR / f"page_{page_num}.jpg"
        download_file(jpg_url, jpg_path)
        
        # Download thumbnail
        thumb_url = f"{BASE_URL}/api/documents/{doc_id}/thumbnail"
        thumb_path = ASSETS_DIR / f"thumbnail.jpg"
        if page_num == 1:  # Only download once
            download_file(thumb_url, thumb_path)
    
    print("\n✅ All exports completed!")
    print(f"\n📁 Exports directory: {EXPORTS_DIR}")
    print(f"📁 Assets directory: {ASSETS_DIR}")
    
    # List all files
    print("\n📋 Exported files:")
    for f in sorted(EXPORTS_DIR.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name}: {size:,} bytes")
    
    print("\n📋 Asset files:")
    for f in sorted(ASSETS_DIR.iterdir()):
        size = f.stat().st_size
        print(f"  {f.name}: {size:,} bytes")

if __name__ == "__main__":
    main()
