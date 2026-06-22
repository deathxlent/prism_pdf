function initExportDropdown() {
    const exportBtn = $('#export-html-btn');
    const exportDropdown = $('#export-dropdown');
    if (!exportBtn || !exportDropdown) return;

    exportBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        exportDropdown.classList.toggle('show');
    });

    document.addEventListener('click', () => {
        if (exportDropdown) exportDropdown.classList.remove('show');
    });

    exportDropdown.addEventListener('click', (e) => {
        e.stopPropagation();
    });
}

async function exportDocumentHtml() {
    if (!currentDocId) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${currentDocId}/export/html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${currentDocId}.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentMarkdown() {
    if (!currentDocId) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${currentDocId}/export/markdown`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${currentDocId}.md`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentHtmlZip() {
    if (!currentDocId) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${currentDocId}/export/zip-html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${currentDocId}_html.zip`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPageHtml() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/export/html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPageMarkdown() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/export/markdown`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}.md`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPagePdf() {
    if (!currentPageData || !currentPageData.single_pdf_path) {
        alert('该页面没有单独的PDF文件');
        return;
    }
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/pdf`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}.pdf`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentTranslatedHtml(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/translated/html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}_译文.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentTranslatedMarkdown(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/translated/markdown`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}_译文.md`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentTranslatedHtmlZip(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/translated/html-zip`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}_译文_html.zip`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPageTranslatedHtml() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/export/translated/html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}_译文.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPageTranslatedMarkdown() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/export/translated/markdown`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}_译文.md`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}
