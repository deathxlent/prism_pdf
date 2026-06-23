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

async function exportDocumentHtml(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentMarkdown(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/markdown`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}.md`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentHtmlZip(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/html-zip`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}_pages_html.zip`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentRagHtml(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    await exportRagHtml(id, false);
}

async function exportDocumentRagHtmlZip(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    await exportRagHtml(id, true);
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

async function exportCurrentPageImage() {
    if (!currentPageData || !currentPageData.jpg_path) {
        alert('该页面没有图片文件');
        return;
    }
    
    try {
        const res = await fetch(`${currentPageData.jpg_path}`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}.jpg`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPageRagHtml() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/export/rag-html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}_RAG友好.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportCurrentPageTranslatedRagHtml() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(`${API}/api/pages/${currentPageData.id}/export/translated-rag-html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `page_${currentPageData.page_number}_译文_RAG友好.html`;
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

async function exportRagHtml(docId, keepPageNumbers) {
    if (!docId) return;
    try {
        const endpoint = keepPageNumbers ? 'rag-html-zip' : 'rag-html';
        const res = await fetch(`${API}/api/documents/${docId}/export/${endpoint}`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        if (keepPageNumbers) {
            a.download = `document_${docId}_RAG友好_按页.zip`;
        } else {
            a.download = `document_${docId}_RAG友好.html`;
        }
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentTranslatedRagHtml(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/translated/rag-html`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}_译文_RAG友好.html`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function exportDocumentTranslatedRagHtmlZip(docId = null) {
    const id = docId || currentDocId;
    if (!id) return;
    try {
        const res = await fetch(`${API}/api/documents/${id}/export/translated/rag-html-zip`);
        if (!res.ok) throw new Error('Export failed');
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `document_${id}_译文_RAG友好_按页.zip`;
        a.click();
        URL.revokeObjectURL(url);
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function checkHasTranslated(docId) {
    if (!docId) return false;
    try {
        const res = await fetch(`${API}/api/documents/${docId}/translated/count`);
        if (!res.ok) return false;
        const data = await res.json();
        return (data.count || 0) > 0;
    } catch (e) {
        return false;
    }
}

function applyTranslatedVisibility(dropdown, showTranslated) {
    let inTranslated = false;
    let inTranslatedRag = false;

    const children = dropdown.children;
    for (let i = 0; i < children.length; i++) {
        const child = children[i];
        if (child.classList.contains('dropdown-section-title')) {
            const title = child.textContent.trim();
            inTranslated = (title === '译文');
            inTranslatedRag = (title === '译文 RAG 友好');
            continue;
        }
        if (child.classList.contains('dropdown-divider')) {
            continue;
        }
        if (inTranslated || inTranslatedRag) {
            if (showTranslated) {
                child.style.display = '';
                child.classList.remove('dropdown-item-disabled');
                child.removeAttribute('disabled');
            } else {
                child.style.display = '';
                child.classList.add('dropdown-item-disabled');
                child.setAttribute('disabled', 'true');
            }
        }
    }

    const dividers = dropdown.querySelectorAll('.dropdown-divider');
    dividers.forEach(divider => {
        let prevHasContent = false;
        let nextHasContent = false;
        let prev = divider.previousElementSibling;
        let next = divider.nextElementSibling;
        while (prev && prev.classList.contains('dropdown-divider')) {
            prev = prev.previousElementSibling;
        }
        while (next && next.classList.contains('dropdown-divider')) {
            next = next.nextElementSibling;
        }
        if (prev) {
            prevHasContent = prev.style.display !== 'none' && !prev.classList.contains('dropdown-divider');
        }
        if (next) {
            nextHasContent = next.style.display !== 'none' && !next.classList.contains('dropdown-divider');
        }
        divider.style.display = (prevHasContent && nextHasContent) ? '' : 'none';
    });
}

async function updateExportDropdownVisibility(docId) {
    const detailDropdown = $('#detail-export-dropdown');
    if (detailDropdown) {
        const hasAny = await checkHasTranslated(docId || currentDocId);
        applyTranslatedVisibility(detailDropdown, hasAny);
    }
    const pageDropdown = $('#page-export-dropdown');
    if (pageDropdown) {
        const hasAny = await checkHasTranslated(docId || currentDocId);
        applyTranslatedVisibility(pageDropdown, hasAny);
    }
}

async function updateListExportDropdownVisibility(docId, dropdownId) {
    const dropdown = document.getElementById(dropdownId);
    if (!dropdown) return;
    const hasAny = await checkHasTranslated(docId);
    applyTranslatedVisibility(dropdown, hasAny);
}
