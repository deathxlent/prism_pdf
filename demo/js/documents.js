function initDocumentsPage() {
    renderDocumentsList();
    setupUploadSection();
}

function setupUploadSection() {
    const dropZone = $('#drop-zone');
    if (!dropZone) return;

    dropZone.addEventListener('click', () => {
        showDemoNotice('上传 PDF');
    });

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        showDemoNotice('上传 PDF');
    });
}

function renderDocumentsList() {
    const docs = MOCK_DATA.documents;
    const listContainer = $('#documents-list');
    const emptyMsg = $('#empty-msg');

    if (!listContainer) return;

    if (!docs || docs.length === 0) {
        listContainer.innerHTML = '';
        if (emptyMsg) emptyMsg.classList.remove('hidden');
        return;
    }

    if (emptyMsg) emptyMsg.classList.add('hidden');

    listContainer.innerHTML = `
        <table class="doc-list-table">
            <thead>
                <tr>
                    <th>文件名</th>
                    <th>页数</th>
                    <th>状态</th>
                    <th>创建时间</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                ${docs.map(doc => `
                    <tr>
                        <td class="doc-name-cell" onclick="openDocument('${doc.id}')">
                            ${escapeHtml(doc.original_filename || doc.filename)}
                        </td>
                        <td>${doc.page_count || '-'}</td>
                        <td>
                            <span class="status-badge status-${doc.status}">
                                ${getStatusText(doc.status)}
                            </span>
                        </td>
                        <td class="doc-time">${formatDateTime(doc.created_at)}</td>
                        <td class="doc-actions">
                            <button class="btn btn-sm btn-warning" onclick="event.stopPropagation(); showDemoNotice('重解析')">
                                <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/></svg>
                                重解析
                            </button>
                            <button class="btn btn-sm btn-info" onclick="event.stopPropagation(); showDemoNotice('翻译')">
                                <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M12.87,15.07L10.33,12.56L10.36,12.53C12.1,10.59 13.34,8.36 14.07,6H17V4H10V2H8V4H1V6H12.17C11.5,7.92 10.44,9.75 9,11.35C8.07,10.32 7.3,9.19 6.69,8H4.69C5.42,9.63 6.42,11.17 7.67,12.56L2.58,17.58L4,19L9,14L12.11,17.11L12.87,15.07M18.5,10H16.5L12,22H14L15.12,19H19.87L21,22H23L18.5,10M15.88,17L17.5,12.67L19.12,17H15.88Z"/></svg>
                                翻译
                            </button>
                            <div class="btn-group" onclick="event.stopPropagation();">
                                <button class="btn btn-sm btn-outline" onclick="toggleHomeExportDropdown(${doc.id}, event)">
                                    <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M5,20H19V18H5M19,9H15V3H9V9H5L12,16L19,9Z"/></svg>
                                    导出
                                    <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M7,10L12,15L17,10H7Z"/></svg>
                                </button>
                                <div class="export-dropdown" id="home-export-dropdown-${doc.id}">
                                    <div class="dropdown-section-title">原文</div>
                                    <button class="dropdown-item" onclick="exportHomeFile('${doc.id}', 'html')">
                                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
                                        整本 HTML
                                    </button>
                                    <button class="dropdown-item" onclick="exportHomeFile('${doc.id}', 'markdown')">
                                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
                                        整本 Markdown
                                    </button>
                                    <div class="dropdown-divider"></div>
                                    <div class="dropdown-section-title">译文</div>
                                    <button class="dropdown-item" onclick="exportHomeFile('${doc.id}', 'translated_html')">
                                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
                                        译文 HTML
                                    </button>
                                    <button class="dropdown-item" onclick="exportHomeFile('${doc.id}', 'translated_md')">
                                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
                                        译文 Markdown
                                    </button>
                                    <div class="dropdown-divider"></div>
                                    <div class="dropdown-section-title">RAG 友好</div>
                                    <button class="dropdown-item" onclick="exportHomeFile('${doc.id}', 'rag_html')">
                                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
                                        RAG 友好格式
                                    </button>
                                    <div class="dropdown-divider"></div>
                                    <div class="dropdown-section-title">译文 RAG 友好</div>
                                    <button class="dropdown-item" onclick="exportHomeFile('${doc.id}', 'translated_rag_html')">
                                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M18,20H6V4H13V9H18V20Z"/></svg>
                                        译文 RAG 友好格式
                                    </button>
                                </div>
                            </div>
                            <button class="btn btn-sm btn-success" onclick="event.stopPropagation(); openDocument('${doc.id}')">
                                <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M12,9A3,3 0 0,0 9,12A3,3 0 0,0 12,15A3,3 0 0,0 15,12A3,3 0 0,0 12,9M12,17A5,5 0 0,1 7,12A5,5 0 0,1 12,7A5,5 0 0,1 17,12A5,5 0 0,1 12,17M12,4.5C7,4.5 2.73,7.61 1,12C2.73,16.39 7,19.5 12,19.5C17,19.5 21.27,16.39 23,12C21.27,7.61 17,4.5 12,4.5Z"/></svg>
                                查看
                            </button>
                            <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); showDemoNotice('删除文档')">
                                <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>
                                删除
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function openDocument(docId) {
    currentDocId = docId;
    currentDocument = MOCK_DATA.documents.find(d => d.id == docId);
    
    if (!currentDocument) return;

    currentPages = currentDocument.pages || [];
    currentPageIndex = 0;

    $('#page-home').classList.remove('active');
    $('#page-detail').classList.add('active');

    renderDetailHeader();
    loadPage(0);
}

function renderDetailHeader() {
    const header = $('#detail-header-title');
    const actions = $('#detail-actions');
    
    if (header) {
        header.textContent = currentDocument.original_filename || currentDocument.filename;
    }

    if (actions) {
        actions.innerHTML = `
            <span id="detail-status" class="status-badge status-${currentDocument.status}">
                ${getStatusText(currentDocument.status)}
            </span>
            <div class="btn-group" id="detail-export-group">
                <button class="btn btn-success" onclick="toggleDetailExportDropdown(event)" id="export-html-btn">
                    <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M14,16V10H10L14,16M19,15V17H5V15H19Z"/></svg>
                    导出
                    <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M7,10L12,15L17,10H7Z"/></svg>
                </button>
            </div>
            <button class="btn btn-info hidden" id="translate-doc-btn">
                <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M12.87,15.07L10.33,12.56L10.36,12.53C12.1,10.59 13.34,8.36 14.07,6H17V4H10V2H8V4H1V6H12.17C11.5,7.92 10.44,9.75 9,11.35C8.07,10.32 7.3,9.19 6.69,8H4.69C5.42,9.63 6.42,11.17 7.67,12.56L2.58,17.58L4,19L9,14L12.11,17.11L12.87,15.07M18.5,10H16.5L12,22H14L15.12,19H19.87L21,22H23L18.5,10M15.88,17L17.5,12.67L19.12,17H15.88Z"/></svg>
                翻译
            </button>
            <button class="btn btn-primary" onclick="showDemoNotice('重解析')">
                <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M17.65,6.35C16.2,4.9 14.21,4 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20C15.73,20 18.84,17.45 19.73,14H17.65C16.83,16.33 14.61,18 12,18A6,6 0 0,1 6,12A6,6 0 0,1 12,6C13.66,6 15.14,6.69 16.22,7.78L13,11H20V4L17.65,6.35Z"/></svg>
                重解析
            </button>
        `;
    }
}

function toggleDetailExportDropdown(event) {
    event.stopPropagation();
    const dropdown = $('#detail-export-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

function toggleExportDropdown() {
    const dropdown = $('#export-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

function toggleHomeExportDropdown(docId, event) {
    event.stopPropagation();
    const dropdown = $(`#home-export-dropdown-${docId}`);
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

function exportHomeFile(docId, format) {
    const dropdown = $(`#home-export-dropdown-${docId}`);
    if (dropdown) dropdown.classList.remove('show');

    const fileMap = {
        'html': 'document.html',
        'markdown': 'document.md',
        'translated_html': 'document_translated.html',
        'translated_md': 'document_translated.md',
        'rag_html': 'document_rag.html',
        'translated_rag_html': 'document_translated_rag.html'
    };
    
    const filename = fileMap[format] || 'document.html';
    const exportPath = `exports/${filename}`;

    const link = document.createElement('a');
    link.href = exportPath;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

function backToHome() {
    $('#page-detail').classList.remove('active');
    $('#page-home').classList.add('active');
    currentDocId = null;
    currentDocument = null;
    currentPages = [];
    currentElements = [];
    currentPageData = null;
}
