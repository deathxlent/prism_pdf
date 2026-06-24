function downloadExport(filename, label) {
    const dropdown = $('#detail-export-dropdown');
    if (dropdown) dropdown.classList.remove('show');

    const exportPath = `exports/${filename}`;

    const link = document.createElement('a');
    link.href = exportPath;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function togglePageExportDropdown(event) {
    event.stopPropagation();
    const dropdown = $('#page-export-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

function exportCurrentPageHtml() {
    const dropdown = $('#page-export-dropdown');
    if (dropdown) dropdown.classList.remove('show');
    
    if (!currentPageData) return;
    const pageNum = currentPageData.page_number;
    
    const link = document.createElement('a');
    link.href = `exports/page_${pageNum}.html`;
    link.download = `page_${pageNum}.html`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function exportCurrentPageHtmlZh() {
    const dropdown = $('#page-export-dropdown');
    if (dropdown) dropdown.classList.remove('show');
    
    if (!currentPageData) return;
    const pageNum = currentPageData.page_number;
    
    const link = document.createElement('a');
    link.href = `exports/page_${pageNum}_translated.html`;
    link.download = `page_${pageNum}_translated.html`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function exportCurrentPageMarkdown() {
    const dropdown = $('#page-export-dropdown');
    if (dropdown) dropdown.classList.remove('show');
    
    if (!currentPageData) return;
    const pageNum = currentPageData.page_number;
    
    const link = document.createElement('a');
    link.href = `exports/page_${pageNum}.md`;
    link.download = `page_${pageNum}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function exportCurrentPageMarkdownZh() {
    const dropdown = $('#page-export-dropdown');
    if (dropdown) dropdown.classList.remove('show');
    
    if (!currentPageData) return;
    const pageNum = currentPageData.page_number;
    
    const link = document.createElement('a');
    link.href = `exports/page_${pageNum}_translated.md`;
    link.download = `page_${pageNum}_translated.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}
