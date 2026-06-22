function setupDropZone() {
    const zone = $('#drop-zone');
    const input = $('#file-input');

    zone.addEventListener('click', () => input.click());

    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('drag-over');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('drag-over');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.name.toLowerCase().endsWith('.pdf')) {
            uploadFile(file);
        } else {
            showUploadResult('仅支持 PDF 文件', true);
        }
    });

    input.addEventListener('change', () => {
        if (input.files[0]) {
            uploadFile(input.files[0]);
        }
    });
}

function setupViewToggle() {
    $$('.view-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const view = btn.dataset.view;
            $$('.view-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            $('.documents-list-view').classList.toggle('active', view === 'list');
            $('.documents-grid-view').classList.toggle('active', view === 'grid');
        });
    });
}

async function uploadFile(file) {
    const progressEl = $('#upload-progress');
    const resultEl = $('#upload-result');
    progressEl.classList.remove('hidden');
    resultEl.classList.add('hidden');

    try {
        const result = await apiUploadFile(file, (pct) => {
            progressEl.querySelector('.progress-fill').style.width = pct + '%';
            progressEl.querySelector('.progress-text').textContent = pct + '%';
        });

        showUploadResult(`上传成功！文档 ID: ${result.document_id}，共 ${result.page_count} 页`, false);
        loadDocuments();

        setTimeout(() => {
            startParsing(result.document_id);
        }, 500);
    } catch (err) {
        showUploadResult(err.detail || '上传失败', true);
    }
}

function showUploadResult(msg, isError) {
    const el = $('#upload-result');
    el.textContent = msg;
    el.className = 'result-msg ' + (isError ? 'error' : 'success');
    el.classList.remove('hidden');
}

async function loadDocuments() {
    try {
        const [docsRes, llmRes] = await Promise.all([
            apiGetDocuments(),
            getLlmActiveConfig()
        ]);

        activeLlmConfig = llmRes;

        const docsWithStatus = await Promise.all(
            docsRes.documents.map(async doc => {
                try {
                    const statusData = await apiGetStatus(doc.id);
                    return { ...doc, unordered_count: statusData.unordered_count || 0 };
                } catch (e) {
                    return { ...doc, unordered_count: 0 };
                }
            })
        );

        renderDocumentsList(docsWithStatus);
        renderDocumentsGrid(docsWithStatus);
    } catch (e) {
        console.error('Failed to load documents:', e);
    }
}

function renderDocumentsList(docs) {
    const container = $('#documents-list');
    if (!docs || docs.length === 0) {
        container.innerHTML = '<p class="empty-msg"><i class="fas fa-inbox"></i><br>暂无文档，请上传 PDF 文件开始使用</p>';
        return;
    }

    container.innerHTML = `
        <table class="doc-list-table">
            <thead>
                <tr>
                    <th>文件名</th>
                    <th>上传时间</th>
                    <th>解析时间</th>
                    <th>解析结果</th>
                    <th>操作</th>
                </tr>
            </thead>
            <tbody>
                ${docs.map(doc => `
                    <tr>
                        <td class="doc-name-cell" onclick="viewDocument(${doc.id})">
                            <i class="fas fa-file-pdf" style="color: var(--error); margin-right: 0.5rem;"></i>
                            ${escapeHtml(doc.original_filename)}
                            ${doc.unordered_count && doc.unordered_count > 0 ? 
                                `<span class="unordered-page-count" title="未排序页数">
                                    <i class="fas fa-exclamation-triangle"></i> ${doc.unordered_count}页未排序
                                </span>` : ''}
                        </td>
                        <td class="doc-time">${formatDateTime(doc.created_at)}</td>
                        <td class="doc-time">${doc.status === 'completed' ? formatDateTime(doc.updated_at) : '-'}</td>
                        <td>${getResultText(doc.status)}</td>
                        <td class="doc-actions">
                            ${doc.status !== 'processing' && !doc.status.startsWith('parsing') ? 
                                `<button class="btn btn-primary btn-sm" onclick="event.stopPropagation(); startParsing(${doc.id})">
                                    <i class="fas fa-play"></i> 解析
                                </button>` : ''}
                            ${doc.status === 'completed' ? 
                                `<button class="btn btn-warning btn-sm" onclick="event.stopPropagation(); reparseDocumentFromList(${doc.id})">
                                    <i class="fas fa-sync-alt"></i> 重解析
                                </button>` : ''}
                            ${doc.status === 'completed' && activeLlmConfig ? 
                                `<button class="btn btn-info btn-sm" onclick="event.stopPropagation(); showDocTranslateLanguageSelect(${doc.id})">
                                    <i class="fas fa-language"></i> 翻译
                                </button>` : ''}
                            <button class="btn btn-success btn-sm" onclick="event.stopPropagation(); viewDocument(${doc.id})">
                                <i class="fas fa-eye"></i> 查看
                            </button>
                            <button class="btn btn-danger btn-sm" onclick="event.stopPropagation(); deleteDocument(${doc.id})">
                                <i class="fas fa-trash"></i> 删除
                            </button>
                        </td>
                    </tr>
                `).join('')}
            </tbody>
        </table>
    `;
}

function renderDocumentsGrid(docs) {
    const container = $('#documents-grid');
    if (!docs || docs.length === 0) {
        container.innerHTML = '<p class="empty-msg"><i class="fas fa-inbox"></i><br>暂无文档</p>';
        return;
    }

    container.innerHTML = docs.map(doc => `
        <div class="book-card" onclick="viewDocument(${doc.id})">
            <div class="book-cover">
                ${doc.status === 'completed' ? 
                    `<img src="${API}/api/documents/${doc.id}/thumbnail" alt="${escapeHtml(doc.original_filename)}" onerror="this.outerHTML='<div class=\\'book-cover-placeholder\\'><i class=\\'fas fa-file-pdf\\'></i>待解析</div>'">` :
                    `<div class="book-cover-placeholder">
                        <i class="fas fa-file-pdf"></i>
                        ${doc.status === 'processing' || doc.status.startsWith('parsing') ? '解析中...' : '待解析'}
                    </div>`
                }
            </div>
            <div class="book-info">
                <div class="book-title" title="${escapeHtml(doc.original_filename)}">${escapeHtml(doc.original_filename)}</div>
                <div class="book-meta">
                    <span class="status-badge status-${doc.status}">${getStatusText(doc.status)}</span>
                    <span>${doc.page_count} 页</span>
                </div>
            </div>
        </div>
    `).join('');
}

async function startParsing(docId) {
    try {
        await apiStartParsing(docId);
        alert('解析已开始，请稍候...');
        loadDocuments();
    } catch (e) {
        alert('启动解析失败: ' + e.message);
    }
}

async function reparseDocumentFromList(docId) {
    if (!confirm('确定要重新解析此文档吗？这将清除现有解析结果。')) return;
    try {
        await apiReparseDocument(docId);
        alert('重解析已开始，请稍候...');
        loadDocuments();
    } catch (e) {
        alert('启动重解析失败: ' + e.message);
    }
}

async function deleteDocument(docId) {
    if (!confirm('确定要删除此文档及其解析结果吗？')) return;

    try {
        await apiDeleteDocument(docId);
        loadDocuments();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function viewDocument(docId) {
    navigateTo(`detail/${docId}`);
}
