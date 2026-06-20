const API = '';
pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

let currentDocId = null;
let currentPageIndex = 0;
let currentPageData = null;
let currentPages = [];
let currentElements = [];
let currentDocument = null;
let editingElementId = null;
let isEditOrderMode = false;
let originalOrder = [];
let currentPdfDoc = null;
let currentScale = 1.5;
let activeElementId = null;
let draggedElement = null;
let progressPollInterval = null;
let isAddElementMode = false;
let selectionStart = null;
let selectionRect = null;
let selectionOverlay = null;
let selectedBbox = null;
let pendingNewElement = null;
let reorderingPages = new Set();

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function init() {
    setupRouter();
    setupDropZone();
    setupViewToggle();
    handleRoute();
    
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            const hash = window.location.hash || '#/home';
            if (hash.startsWith('#/detail/') && currentPageData && currentElements) {
                renderPdfPage(currentPageData);
            }
        }, 100);
    });
}

function setupRouter() {
    window.addEventListener('hashchange', handleRoute);
}

function handleRoute() {
    const hash = window.location.hash || '#/home';
    const parts = hash.replace('#/', '').split('/');
    const route = parts[0];

    $$('.page').forEach(p => p.classList.remove('active'));
    $$('.nav-item').forEach(n => n.classList.remove('active'));

    if (progressPollInterval) {
        clearInterval(progressPollInterval);
        progressPollInterval = null;
    }

    if (isAddElementMode) {
        toggleAddElementMode();
    }
    clearSelection();

    if (route === 'home') {
        $('#page-home').classList.add('active');
        document.querySelector('.nav-item[data-route="home"]').classList.add('active');
        loadDocuments();
    } else if (route === 'detail' && parts[1]) {
        $('#page-detail').classList.add('active');
        document.querySelector('.nav-item[data-route="home"]').classList.add('active');
        loadDocumentDetail(parseInt(parts[1]));
    } else if (route === 'llm-config') {
        $('#page-llm-config').classList.add('active');
        document.querySelector('.nav-item[data-route="home"]').classList.add('active');
        initLlmConfigPage();
    } else {
        navigateTo('home');
    }
}


function updateProgressDisplay(progress) {
    const container = $('#detail-progress-container');
    const fill = $('#detail-progress-fill');
    const text = $('#detail-progress-text');
    const message = $('#detail-progress-message');

    if (!progress || progress.percent <= 0 || progress.percent >= 100) {
        container.classList.add('hidden');
        return;
    }

    container.classList.remove('hidden');
    fill.style.width = progress.percent + '%';
    text.textContent = progress.percent + '%';
    message.textContent = progress.message || '';
}


async function pollProgress(docId) {
    try {
        const res = await fetch(API + '/api/progress/' + docId);
        const data = await res.json();
        
        updateProgressDisplay(data.progress);
        
        if (data.status === 'completed' || data.status === 'failed') {
            if (progressPollInterval) {
                clearInterval(progressPollInterval);
                progressPollInterval = null;
            }
            $('#detail-progress-container').classList.add('hidden');
            
            const statusEl = $('#detail-status');
            statusEl.textContent = getStatusText(data.status);
            statusEl.className = 'status-badge status-' + data.status;
            
            if (data.status === 'completed') {
                loadDocumentDetail(docId);
            }
        }
    } catch (e) {
        console.error('Failed to poll progress:', e);
    }
}

function navigateTo(route) {
    window.location.hash = `#/${route}`;
}

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

    const formData = new FormData();
    formData.append('file', file);

    try {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', API + '/api/upload');

        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                progressEl.querySelector('.progress-fill').style.width = pct + '%';
                progressEl.querySelector('.progress-text').textContent = pct + '%';
            }
        };

        const result = await new Promise((resolve, reject) => {
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    resolve(JSON.parse(xhr.responseText));
                } else {
                    try {
                        reject(JSON.parse(xhr.responseText));
                    } catch {
                        reject({ detail: xhr.statusText });
                    }
                }
            };
            xhr.onerror = () => reject({ detail: 'Network error' });
            xhr.send(formData);
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
        const res = await fetch(API + '/api/documents');
        const data = await res.json();
        
        const docsWithStatus = await Promise.all(
            data.documents.map(async doc => {
                try {
                    const statusRes = await fetch(API + '/api/status/' + doc.id);
                    const statusData = await statusRes.json();
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

function formatDateTime(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getStatusText(status) {
    const map = {
        'uploaded': '已上传',
        'validated': '已验证',
        'pages_ready': '待解析',
        'processing': '处理中',
        'parsing_layout': '布局解析中',
        'parsing_content': '内容解析中',
        'completed': '已完成',
        'failed': '失败'
    };
    return map[status] || status;
}

function getResultText(status) {
    if (status === 'completed') return '<span class="parse-result success"><i class="fas fa-check-circle"></i> 解析成功</span>';
    if (status === 'failed') return '<span class="parse-result failed"><i class="fas fa-times-circle"></i> 解析失败</span>';
    if (status === 'processing' || status.startsWith('parsing')) return '<span class="parse-result processing"><i class="fas fa-spinner fa-spin"></i> 解析中</span>';
    return '<span class="parse-result"><i class="fas fa-clock"></i> 待解析</span>';
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
        const res = await fetch(API + '/api/parse/' + docId, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start parsing');
        alert('解析已开始，请稍候...');
        loadDocuments();
    } catch (e) {
        alert('启动解析失败: ' + e.message);
    }
}

async function reparseDocumentFromList(docId) {
    if (!confirm('确定要重新解析此文档吗？这将清除现有解析结果。')) return;
    try {
        const res = await fetch(API + '/api/reparse/' + docId, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start reparsing');
        alert('重解析已开始，请稍候...');
        loadDocuments();
    } catch (e) {
        alert('启动重解析失败: ' + e.message);
    }
}

async function deleteDocument(docId) {
    if (!confirm('确定要删除此文档及其解析结果吗？')) return;

    try {
        await fetch(API + '/api/documents/' + docId, { method: 'DELETE' });
        loadDocuments();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function viewDocument(docId) {
    navigateTo(`detail/${docId}`);
}

async function loadDocumentDetail(docId) {
    currentDocId = docId;
    currentPageIndex = 0;
    activeElementId = null;
    isEditOrderMode = false;
    
    searchResults = [];
    currentSearchIndex = -1;
    if ($('#pdf-search-input')) {
        $('#pdf-search-input').value = '';
    }
    if ($('#search-count')) {
        $('#search-count').classList.add('hidden');
    }
    closeSearchResults();

    if (progressPollInterval) {
        clearInterval(progressPollInterval);
        progressPollInterval = null;
    }

    try {
        const [docRes, pagesRes, resultsRes] = await Promise.all([
            fetch(API + '/api/documents').then(r => r.json()),
            fetch(API + '/api/status/' + docId).then(r => r.json()),
            fetch(API + '/api/results/' + docId).then(r => r.json()).catch(() => null)
        ]);

        currentDocument = docRes.documents.find(d => d.id === docId);
        currentPages = pagesRes.pages;

        if (!currentDocument) {
            alert('文档不存在');
            navigateTo('home');
            return;
        }

        $('#detail-title').textContent = currentDocument.original_filename;
        const statusEl = $('#detail-status');
        statusEl.textContent = getStatusText(currentDocument.status);
        statusEl.className = 'status-badge status-' + currentDocument.status;

        if (pagesRes.progress) {
            updateProgressDisplay(pagesRes.progress);
        }

        if (currentDocument.status === 'processing' || currentDocument.status.startsWith('parsing')) {
            progressPollInterval = setInterval(() => pollProgress(docId), 1000);
        }

        renderThumbnails();

        if (currentPages.length > 0) {
            loadPage(0);
        }
    } catch (e) {
        console.error('Failed to load document detail:', e);
        alert('加载文档详情失败: ' + e.message);
    }
}

function renderThumbnails() {
    const container = $('#thumbs-list');
    container.innerHTML = currentPages.map((page, idx) => {
        const imgSrc = page.jpg_path ? `${API}/api/file/${encodeURIComponent(page.jpg_path)}` : null;
        const unordered = page.is_ordered === false;

        return `
            <div class="thumb-item ${idx === currentPageIndex ? 'active' : ''}" data-index="${idx}" onclick="loadPage(${idx})">
                ${unordered ? '<span class="thumb-unordered" title="未排序"><i class="fas fa-exclamation-triangle"></i></span>' : ''}
                ${imgSrc ? 
                    `<img src="${imgSrc}" alt="第 ${page.page_number} 页" onerror="this.outerHTML='<div class=\\'thumb-placeholder\\'>第 ${page.page_number} 页</div>'">` :
                    `<div class="thumb-placeholder">第 ${page.page_number} 页</div>`
                }
                <div class="thumb-page-num">P. ${page.page_number}</div>
            </div>
        `;
    }).join('');
}

function getPageDataByNumber(pageNum) {
    return currentPages.find(p => p.page_number === pageNum) || null;
}

async function loadPage(index) {
    currentPageIndex = index;
    const page = currentPages[index];

    $$('.thumb-item').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });

    $('#pdf-page-info').textContent = `第 ${page.page_number} 页`;

    activeElementId = null;
    
    if (isAddElementMode) {
        toggleAddElementMode();
    }
    clearSelection();
    clearSearchHighlights();

    try {
        const res = await fetch(API + '/api/pages/' + page.id + '/elements');
        const data = await res.json();
        currentElements = data.elements;
        currentPageData = page;

        const isOrdered = data.is_ordered !== false && page.is_ordered !== false;
        const unorderedBadge = $('#unordered-badge');
        const reorderBtn = $('#reorder-btn');
        const isPageReordering = reorderingPages.has(page.id);
        
        if (isOrdered) {
            unorderedBadge.classList.add('hidden');
        } else {
            unorderedBadge.classList.remove('hidden');
        }
        
        reorderBtn.style.display = '';
        reorderBtn.disabled = isPageReordering;
        if (isPageReordering) {
            reorderBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 排序中...';
        } else {
            reorderBtn.innerHTML = '<i class="fas fa-sort-amount-down"></i> 重排序';
        }

        await renderPdfPage(page);
        renderElements();
    } catch (e) {
        console.error('Failed to load page:', e);
        currentElements = [];
        renderElements();
    }
}

async function renderPdfPage(page) {
    const canvas = $('#pdf-canvas');
    const ctx = canvas.getContext('2d');
    const annotationLayer = $('#annotation-layer');
    const container = $('#pdf-container');

    function updateAnnotationLayer() {
        const canvasRect = canvas.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        
        const displayWidth = canvasRect.width;
        const displayHeight = canvasRect.height;
        
        const offsetX = canvasRect.left - containerRect.left;
        const offsetY = canvasRect.top - containerRect.top;
        
        annotationLayer.style.left = offsetX + 'px';
        annotationLayer.style.top = offsetY + 'px';
        annotationLayer.style.width = displayWidth + 'px';
        annotationLayer.style.height = displayHeight + 'px';
        
        return { displayWidth, displayHeight };
    }

    try {
        if (page.single_pdf_path) {
            const pdfUrl = `${API}/api/pages/${page.id}/pdf`;
            const loadingTask = pdfjsLib.getDocument(pdfUrl);
            const pdfDoc = await loadingTask.promise;
            const pdfPage = await pdfDoc.getPage(1);

            const viewport = pdfPage.getViewport({ scale: currentScale });
            canvas.width = viewport.width;
            canvas.height = viewport.height;

            await pdfPage.render({
                canvasContext: ctx,
                viewport: viewport
            }).promise;

            requestAnimationFrame(() => {
                const { displayWidth, displayHeight } = updateAnnotationLayer();
                clearAnnotations();
                renderAnnotations(currentElements, viewport.width, viewport.height, displayWidth, displayHeight);
            });
        } else if (page.jpg_path) {
            const img = new Image();
            img.onload = () => {
                canvas.width = img.width * currentScale;
                canvas.height = img.height * currentScale;
                ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

                requestAnimationFrame(() => {
                    const { displayWidth, displayHeight } = updateAnnotationLayer();
                    clearAnnotations();
                    renderAnnotations(currentElements, canvas.width, canvas.height, displayWidth, displayHeight);
                });
            };
            img.src = `${API}/api/file/${encodeURIComponent(page.jpg_path)}`;
        } else {
            canvas.width = 600;
            canvas.height = 800;
            ctx.fillStyle = '#f8fafc';
            ctx.fillRect(0, 0, 600, 800);
            ctx.fillStyle = '#64748b';
            ctx.font = '16px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('暂无页面预览', 300, 400);
            
            requestAnimationFrame(() => {
                const { displayWidth, displayHeight } = updateAnnotationLayer();
                clearAnnotations();
            });
        }
    } catch (e) {
        console.error('Failed to render PDF:', e);
        canvas.width = 600;
        canvas.height = 800;
        ctx.fillStyle = '#fef2f2';
        ctx.fillRect(0, 0, 600, 800);
        ctx.fillStyle = '#ef4444';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('页面渲染失败: ' + e.message, 300, 400);
    }
}

function clearAnnotations() {
    $('#annotation-layer').innerHTML = '';
}

function renderAnnotations(elements, canvasWidth, canvasHeight, displayWidth, displayHeight) {
    const layer = $('#annotation-layer');
    if (!currentPageData) return;

    const page = currentPageData;
    let jpgWidth = page.jpg_width;
    let jpgHeight = page.jpg_height;
    if (!jpgWidth || !jpgHeight) {
        jpgWidth = page.width * 200 / 72;
        jpgHeight = page.height * 200 / 72;
    }
    if (!jpgWidth) jpgWidth = canvasWidth;
    if (!jpgHeight) jpgHeight = canvasHeight;

    const dispW = displayWidth || canvasWidth;
    const dispH = displayHeight || canvasHeight;

    clearAnnotations();

    elements.forEach(elem => {
        const scaleX = dispW / jpgWidth;
        const scaleY = dispH / jpgHeight;

        const x = elem.bbox_x0 * scaleX;
        const y = elem.bbox_y0 * scaleY;
        const w = (elem.bbox_x1 - elem.bbox_x0) * scaleX;
        const h = (elem.bbox_y1 - elem.bbox_y0) * scaleY;

        const box = document.createElement('div');
        box.className = `annotation-box type-${elem.element_type.toLowerCase()} hidden`;
        box.dataset.type = elem.element_type;
        box.dataset.elementId = elem.id;
        box.style.left = x + 'px';
        box.style.top = y + 'px';
        box.style.width = w + 'px';
        box.style.height = h + 'px';

        box.addEventListener('click', (e) => {
            e.stopPropagation();
            highlightElement(elem.id);
        });

        layer.appendChild(box);
    });

    if (activeElementId) {
        const activeBox = document.querySelector(`.annotation-box[data-element-id="${activeElementId}"]`);
        if (activeBox) {
            activeBox.classList.remove('hidden');
            activeBox.classList.add('active');
        }
    }
}

function highlightElement(elementId) {
    activeElementId = elementId;

    $$('.annotation-box').forEach(box => {
        const isActive = parseInt(box.dataset.elementId) === elementId;
        box.classList.toggle('hidden', !isActive);
        box.classList.toggle('active', isActive);
    });

    $$('.element-card').forEach(card => {
        card.classList.toggle('active', parseInt(card.dataset.elementId) === elementId);
    });

    const card = document.querySelector(`.element-card[data-element-id="${elementId}"]`);
    if (card) {
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function renderElements() {
    const container = $('#elements-list');
    container.classList.toggle('edit-order-mode', isEditOrderMode);

    if (!currentElements || currentElements.length === 0) {
        container.innerHTML = '<p class="empty-msg">当前页面暂无解析元素</p>';
        return;
    }

    const sorted = [...currentElements].sort((a, b) => a.reading_order - b.reading_order);

    container.innerHTML = sorted.map((elem, idx) => {
        const type = elem.element_type.toLowerCase();
        const isImage = elem.content_format === 'image_path';
        let contentHtml = '';

        if (isImage && elem.content) {
            contentHtml = `<img src="${API}/api/file/${encodeURIComponent(elem.content)}" alt="图片">`;
        } else if (elem.content_format === 'html') {
            contentHtml = elem.content || '(空)';
        } else if (elem.content_format === 'latex') {
            contentHtml = `<code>${escapeHtml(elem.content || '(空)')}</code>`;
        } else {
            contentHtml = renderMarkdownSimple(elem.content || '(空)');
        }

        return `
            <div class="element-card ${activeElementId === elem.id ? 'active' : ''}" 
                 data-element-id="${elem.id}"
                 data-order="${elem.reading_order}"
                 draggable="${isEditOrderMode}"
                 ondragstart="handleDragStart(event, ${elem.id})"
                 ondragend="handleDragEnd(event)"
                 ondragover="handleDragOver(event)"
                 ondragleave="handleDragLeave(event)"
                 ondrop="handleDrop(event, ${elem.id})">
                <div class="element-header" onclick="highlightElement(${elem.id})">
                    <span class="drag-handle" onclick="event.stopPropagation()">
                        <i class="fas fa-grip-vertical"></i>
                    </span>
                    <span class="element-type ${type}">${elem.element_type}</span>
                    <span class="element-order">#${elem.reading_order}</span>
                    <span class="element-confidence">${(elem.confidence * 100).toFixed(1)}%</span>
                </div>
                <div class="element-content markdown" onclick="highlightElement(${elem.id})">
                    ${contentHtml}
                </div>
                <div class="element-footer">
                    <button class="btn btn-outline btn-sm edit-btn" onclick="event.stopPropagation(); openEditModal(${elem.id})">
                        <i class="fas fa-edit"></i> 编辑
                    </button>
                    <button class="btn btn-outline btn-sm delete-btn" onclick="event.stopPropagation(); deleteElement(${elem.id})">
                        <i class="fas fa-trash"></i> 删除
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function renderMarkdownSimple(text) {
    if (!text) return '';
    
    let html = escapeHtml(text);
    
    html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');
    
    html = html.replace(/^\|(.+)\|$/gm, (match) => {
        const cells = match.split('|').filter(c => c.trim());
        if (cells.every(c => /^[-:]+$/.test(c.trim()))) return '';
        return '<tr>' + cells.map(c => `<td>${c.trim()}</td>`).join('') + '</tr>';
    });
    
    if (html.includes('<tr>')) {
        html = '<table>' + html.replace(/(<tr>.*?<\/tr>)/gs, '$1') + '</table>';
    }
    
    html = html.replace(/^- (.*$)/gm, '<li>$1</li>');
    html = html.replace(/^(\d+)\. (.*$)/gm, '<li>$2</li>');
    
    html = html.replace(/(<li>.*?<\/li>)(\n<li>)/gs, '$1$2');
    html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');
    
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    
    html = html.replace(/<p><h(\d)>/g, '<h$1>');
    html = html.replace(/<\/h(\d)><\/p>/g, '</h$1>');
    html = html.replace(/<p><table>/g, '<table>');
    html = html.replace(/<\/table><\/p>/g, '</table>');
    html = html.replace(/<p><ul>/g, '<ul>');
    html = html.replace(/<\/ul><\/p>/g, '</ul>');
    html = html.replace(/<p><\/p>/g, '');
    
    return html;
}

function openEditModal(elementId) {
    const elem = currentElements.find(e => e.id === elementId);
    if (!elem) return;

    editingElementId = elementId;
    $('#edit-type').value = elem.element_type;
    $('#edit-content').value = elem.content || '';
    $('#edit-modal').classList.remove('hidden');
}

function closeEditModal() {
    $('#edit-modal').classList.add('hidden');
    editingElementId = null;
}

async function saveElementEdit() {
    if (!editingElementId) return;

    const newType = $('#edit-type').value;
    const newContent = $('#edit-content').value;

    try {
        const res = await fetch(API + '/api/elements/' + editingElementId, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                element_type: newType,
                content: newContent
            })
        });

        if (!res.ok) throw new Error('Failed to update element');

        const updated = await res.json();
        const idx = currentElements.findIndex(e => e.id === editingElementId);
        if (idx !== -1) {
            currentElements[idx] = updated;
        }

        renderElements();
        
        if (currentPageData) {
            const canvas = $('#pdf-canvas');
            clearAnnotations();
            renderAnnotations(currentElements, canvas.width, canvas.height);
        }

        closeEditModal();
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

function toggleEditOrder() {
    isEditOrderMode = true;
    originalOrder = currentElements.map(e => ({ id: e.id, order: e.reading_order }));
    $('#edit-order-btn').classList.add('hidden');
    $('#save-order-btn').classList.remove('hidden');
    $('#cancel-order-btn').classList.remove('hidden');
    renderElements();
}

function cancelOrder() {
    isEditOrderMode = false;
    currentElements.forEach(elem => {
        const orig = originalOrder.find(o => o.id === elem.id);
        if (orig) elem.reading_order = orig.order;
    });
    originalOrder = [];
    $('#edit-order-btn').classList.remove('hidden');
    $('#save-order-btn').classList.add('hidden');
    $('#cancel-order-btn').classList.add('hidden');
    renderElements();
}

async function saveOrder() {
    if (!currentPageData) return;

    const sorted = [...currentElements].sort((a, b) => a.reading_order - b.reading_order);
    const elementOrder = sorted.map(e => e.id);

    try {
        const res = await fetch(API + '/api/pages/' + currentPageData.id + '/elements/reorder', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ element_order: elementOrder })
        });

        if (!res.ok) throw new Error('Failed to reorder elements');

        sorted.forEach((elem, idx) => {
            elem.reading_order = idx;
        });

        if (currentPageData) {
            currentPageData.is_ordered = true;
        }
        const idx = currentPages.findIndex(p => p.id === currentPageData.id);
        if (idx >= 0) {
            currentPages[idx].is_ordered = true;
        }

        $('#unordered-badge').classList.add('hidden');
        renderThumbnails();

        isEditOrderMode = false;
        originalOrder = [];
        $('#edit-order-btn').classList.remove('hidden');
        $('#save-order-btn').classList.add('hidden');
        $('#cancel-order-btn').classList.add('hidden');
        renderElements();

        alert('排序已保存');
    } catch (e) {
        alert('保存排序失败: ' + e.message);
    }
}

function handleDragStart(e, elementId) {
    if (!isEditOrderMode) return;
    draggedElement = elementId;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
}

function handleDragEnd(e) {
    if (!isEditOrderMode) return;
    e.target.classList.remove('dragging');
    document.querySelectorAll('.element-card').forEach(card => {
        card.classList.remove('drag-over');
    });
    draggedElement = null;
}

function handleDragOver(e) {
    if (!isEditOrderMode || !draggedElement) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    e.currentTarget.classList.add('drag-over');
}

function handleDragLeave(e) {
    if (!isEditOrderMode) return;
    e.currentTarget.classList.remove('drag-over');
}

function handleDrop(e, targetId) {
    if (!isEditOrderMode || !draggedElement || draggedElement === targetId) return;
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');

    const draggedElem = currentElements.find(e => e.id === draggedElement);
    const targetElem = currentElements.find(e => e.id === targetId);

    if (draggedElem && targetElem) {
        const tempOrder = draggedElem.reading_order;
        draggedElem.reading_order = targetElem.reading_order;
        targetElem.reading_order = tempOrder;
        renderElements();
    }
}

async function reparseDocument() {
    if (!currentDocId) return;
    if (!confirm('确定要重新解析此文档吗？这将清除现有解析结果。')) return;

    try {
        const res = await fetch(API + '/api/reparse/' + currentDocId, { method: 'POST' });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Failed to start reparsing');
        
        if (progressPollInterval) {
            clearInterval(progressPollInterval);
        }
        progressPollInterval = setInterval(() => pollProgress(currentDocId), 1000);
        
        const statusEl = $('#detail-status');
        statusEl.textContent = getStatusText('processing');
        statusEl.className = 'status-badge status-processing';
        
        alert('重解析已开始，请稍候...');
    } catch (e) {
        alert('启动重解析失败: ' + e.message);
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

document.addEventListener('DOMContentLoaded', init);

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeEditModal();
        closeAddElementModal();
        closeRawDataModal();
        if (isAddElementMode) {
            toggleAddElementMode();
        }
    }
});

$('#edit-modal').addEventListener('click', (e) => {
    if (e.target.id === 'edit-modal') {
        closeEditModal();
    }
});

async function deleteElement(elementId) {
    if (!confirm('确定要删除这个元素吗？')) return;
    
    try {
        const res = await fetch(API + '/api/elements/' + elementId, {
            method: 'DELETE'
        });
        
        if (!res.ok) throw new Error('Failed to delete element');
        
        currentElements = currentElements.filter(e => e.id !== elementId);
        if (activeElementId === elementId) {
            clearHighlights();
            activeElementId = null;
        }
        renderElements();
        
        console.log('Element deleted:', elementId);
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

function toggleAddElementMode() {
    isAddElementMode = !isAddElementMode;
    const canvasContainer = $('.pdf-canvas-container');
    const addBtn = $('#add-element-btn');
    
    if (isAddElementMode) {
        canvasContainer.classList.add('add-mode');
        addBtn.innerHTML = '<i class="fas fa-times"></i> 取消添加';
        addBtn.classList.remove('btn-success');
        addBtn.classList.add('btn-danger');
        setupSelectionHandlers();
    } else {
        canvasContainer.classList.remove('add-mode');
        addBtn.innerHTML = '<i class="fas fa-plus"></i> 添加元素';
        addBtn.classList.remove('btn-danger');
        addBtn.classList.add('btn-success');
        clearSelection();
        removeSelectionHandlers();
    }
}

function setupSelectionHandlers() {
    const canvasContainer = $('.pdf-canvas-container');
    if (!canvasContainer) return;
    
    if (!selectionOverlay) {
        selectionOverlay = document.createElement('div');
        selectionOverlay.className = 'selection-overlay';
        canvasContainer.appendChild(selectionOverlay);
        
        selectionRect = document.createElement('div');
        selectionRect.className = 'selection-rect';
        selectionRect.style.display = 'none';
        selectionOverlay.appendChild(selectionRect);
    }
    
    selectionOverlay.style.pointerEvents = 'auto';
    selectionOverlay.addEventListener('mousedown', handleSelectionStart);
    selectionOverlay.addEventListener('mousemove', handleSelectionMove);
    selectionOverlay.addEventListener('mouseup', handleSelectionEnd);
    selectionOverlay.addEventListener('mouseleave', handleSelectionEnd);
}

function removeSelectionHandlers() {
    if (!selectionOverlay) return;
    
    selectionOverlay.style.pointerEvents = 'none';
    selectionOverlay.removeEventListener('mousedown', handleSelectionStart);
    selectionOverlay.removeEventListener('mousemove', handleSelectionMove);
    selectionOverlay.removeEventListener('mouseup', handleSelectionEnd);
    selectionOverlay.removeEventListener('mouseleave', handleSelectionEnd);
}

function handleSelectionStart(e) {
    if (!isAddElementMode) return;
    
    const rect = selectionOverlay.getBoundingClientRect();
    selectionStart = {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
    
    selectionRect.style.display = 'block';
    selectionRect.style.left = selectionStart.x + 'px';
    selectionRect.style.top = selectionStart.y + 'px';
    selectionRect.style.width = '0px';
    selectionRect.style.height = '0px';
}

function handleSelectionMove(e) {
    if (!isAddElementMode || !selectionStart) return;
    
    const rect = selectionOverlay.getBoundingClientRect();
    const currentX = e.clientX - rect.left;
    const currentY = e.clientY - rect.top;
    
    const left = Math.min(selectionStart.x, currentX);
    const top = Math.min(selectionStart.y, currentY);
    const width = Math.abs(currentX - selectionStart.x);
    const height = Math.abs(currentY - selectionStart.y);
    
    selectionRect.style.left = left + 'px';
    selectionRect.style.top = top + 'px';
    selectionRect.style.width = width + 'px';
    selectionRect.style.height = height + 'px';
}

function handleSelectionEnd(e) {
    if (!isAddElementMode || !selectionStart) return;
    
    const rect = selectionOverlay.getBoundingClientRect();
    const endX = e.clientX - rect.left;
    const endY = e.clientY - rect.top;
    
    const screenX0 = Math.min(selectionStart.x, endX);
    const screenY0 = Math.min(selectionStart.y, endY);
    const screenX1 = Math.max(selectionStart.x, endX);
    const screenY1 = Math.max(selectionStart.y, endY);
    
    const width = screenX1 - screenX0;
    const height = screenY1 - screenY0;
    
    selectionStart = null;
    
    if (width < 10 || height < 10) {
        selectionRect.style.display = 'none';
        return;
    }
    
    const jpgCoords = screenToJpgCoords(screenX0, screenY0, screenX1, screenY1);
    if (jpgCoords) {
        selectedBbox = jpgCoords;
        openAddElementModal();
    }
    
    selectionRect.style.display = 'none';
}

function screenToJpgCoords(screenX0, screenY0, screenX1, screenY1) {
    const canvas = $('#pdf-canvas');
    if (!canvas || !currentPageData) return null;
    
    const canvasRect = canvas.getBoundingClientRect();
    const containerRect = $('.pdf-canvas-container').getBoundingClientRect();
    
    const offsetX = canvasRect.left - containerRect.left;
    const offsetY = canvasRect.top - containerRect.top;
    
    const canvasX0 = screenX0 - offsetX;
    const canvasY0 = screenY0 - offsetY;
    const canvasX1 = screenX1 - offsetX;
    const canvasY1 = screenY1 - offsetY;
    
    const canvasWidth = canvas.width;
    const canvasHeight = canvas.height;
    
    const jpgWidth = currentPageData.jpg_width;
    const jpgHeight = currentPageData.jpg_height;
    
    const scaleX = jpgWidth / canvasWidth;
    const scaleY = jpgHeight / canvasHeight;
    
    const jpgX0 = Math.max(0, canvasX0 * scaleX);
    const jpgY0 = Math.max(0, canvasY0 * scaleY);
    const jpgX1 = Math.min(jpgWidth, canvasX1 * scaleX);
    const jpgY1 = Math.min(jpgHeight, canvasY1 * scaleY);
    
    console.log('Screen coords:', { screenX0, screenY0, screenX1, screenY1 });
    console.log('Canvas coords:', { canvasX0, canvasY0, canvasX1, canvasY1 });
    console.log('JPG coords (to save):', { jpgX0, jpgY0, jpgX1, jpgY1 });
    console.log('Scale:', { scaleX, scaleY, jpgWidth, jpgHeight, canvasWidth, canvasHeight });
    
    return [jpgX0, jpgY0, jpgX1, jpgY1];
}

function clearSelection() {
    if (selectionRect) {
        selectionRect.style.display = 'none';
    }
    selectionStart = null;
    selectedBbox = null;
}

function openAddElementModal() {
    if (!selectedBbox) return;
    
    const bboxToSave = [...selectedBbox];
    
    const bboxStr = `(${bboxToSave[0].toFixed(2)}, ${bboxToSave[1].toFixed(2)}, ${bboxToSave[2].toFixed(2)}, ${bboxToSave[3].toFixed(2)})`;
    $('#add-element-bbox').textContent = bboxStr;
    $('#add-element-content').value = '';
    $('#add-element-type').value = 'Text';
    $('#add-element-save-btn').disabled = false;
    $('#add-element-modal').classList.remove('hidden');
    
    pendingNewElement = {
        bbox: bboxToSave
    };
    
    toggleAddElementMode();
}

function closeAddElementModal() {
    $('#add-element-modal').classList.add('hidden');
    selectedBbox = null;
    pendingNewElement = null;
}

async function saveNewElement() {
    if (!pendingNewElement || !pendingNewElement.bbox || !currentPageData) {
        alert('请先框选区域');
        return;
    }
    
    const elementType = $('#add-element-type').value;
    const content = $('#add-element-content').value;
    const bbox = pendingNewElement.bbox;
    
    console.log('Saving new element with JPG bbox:', bbox);
    console.log('Current page jpg dimensions:', { width: currentPageData.jpg_width, height: currentPageData.jpg_height });
    
    try {
        const res = await fetch(API + '/api/pages/' + currentPageData.id + '/elements', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                element_type: elementType,
                bbox: bbox,
                content: content,
                content_format: 'markdown',
                confidence: 1.0
            })
        });
        
        if (!res.ok) throw new Error('Failed to create element');
        
        const newElement = await res.json();
        currentElements.push(newElement);
        renderElements();
        closeAddElementModal();
        
        alert('元素添加成功');
    } catch (e) {
        alert('添加元素失败: ' + e.message);
    }
}

async function showRawLayoutData() {
    if (!currentPageData) return;
    
    try {
        const res = await fetch(API + '/api/pages/' + currentPageData.id + '/layout-raw');
        if (!res.ok) throw new Error('Failed to get raw layout data');
        
        const data = await res.json();
        
        $('#raw-data-count').textContent = `共检测到 ${data.count} 个原始元素`;
        
        const formattedData = data.raw_detections.map((det, idx) => {
            return `#${idx} ${det.element_type} (class_id: ${det.class_id}, conf: ${det.confidence.toFixed(3)})\n` +
                   `  bbox: (${det.bbox.map(v => v.toFixed(2)).join(', ')})`;
        }).join('\n\n');
        
        $('#raw-data-content').textContent = formattedData || '没有检测到原始数据';
        $('#raw-data-modal').classList.remove('hidden');
        
    } catch (e) {
        alert('获取原始数据失败: ' + e.message);
    }
}

function closeRawDataModal() {
    $('#raw-data-modal').classList.add('hidden');
}

$('#add-element-modal').addEventListener('click', (e) => {
    if (e.target.id === 'add-element-modal') {
        closeAddElementModal();
    }
});

$('#raw-data-modal').addEventListener('click', (e) => {
    if (e.target.id === 'raw-data-modal') {
        closeRawDataModal();
    }
});

$('#annotation-image-modal').addEventListener('click', (e) => {
    if (e.target.id === 'annotation-image-modal') {
        closeAnnotationImageModal();
    }
});

async function showLayoutAnnotationImage() {
    if (!currentPageData) return;

    try {
        const imgUrl = `${API}/api/pages/${currentPageData.id}/layout-annotation`;
        $('#annotation-image').src = imgUrl + '?t=' + Date.now();
        $('#annotation-image-modal').classList.remove('hidden');
        closeRawDataModal();
    } catch (e) {
        alert('获取标注图片失败: ' + e.message);
    }
}

function closeAnnotationImageModal() {
    $('#annotation-image-modal').classList.add('hidden');
    $('#annotation-image').src = '';
}

function exportDocumentHtml() {
    if (!currentDocId) return;

    const exportBtn = $('#export-html-btn');
    const originalText = exportBtn.innerHTML;
    exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 导出中...';
    exportBtn.disabled = true;

    try {
        const url = `${API}/api/documents/${currentDocId}/export/html`;
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.click();
    } catch (e) {
        alert('导出失败: ' + e.message);
    } finally {
        setTimeout(() => {
            exportBtn.innerHTML = originalText;
            exportBtn.disabled = false;
        }, 1000);
    }
}

function exportCurrentPageHtml() {
    if (!currentPageData) return;

    try {
        const url = `${API}/api/pages/${currentPageData.id}/export/html`;
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.click();
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

function exportCurrentPageMarkdown() {
    if (!currentPageData) return;

    try {
        const url = `${API}/api/pages/${currentPageData.id}/export/markdown`;
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.click();
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

function exportCurrentPagePdf() {
    if (!currentPageData) return;

    try {
        const url = `${API}/api/pages/${currentPageData.id}/pdf`;
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.click();
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

async function reorderCurrentPage() {
    if (!currentPageData) return;
    
    const pageId = currentPageData.id;
    if (reorderingPages.has(pageId)) return;

    const confirmMsg = '确定要使用Surya模型对该页进行重新排序吗？\n\n注意：如果显存不足，可能会失败。';
    if (!confirm(confirmMsg)) return;

    reorderingPages.add(pageId);
    
    const reorderBtn = $('#reorder-btn');
    reorderBtn.disabled = true;
    reorderBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 排序中...';

    try {
        const res = await fetch(`${API}/api/pages/${pageId}/reorder`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '重排序失败');
        }

        const result = await res.json();
        
        if (currentPageData && currentPageData.id === pageId) {
            currentPageData.is_ordered = true;
        }
        
        const idx = currentPages.findIndex(p => p.id === pageId);
        if (idx >= 0) {
            currentPages[idx].is_ordered = true;
        }

        renderThumbnails();
        if (currentPageData && currentPageData.id === pageId) {
            loadPage(currentPageIndex);
        }
        
        alert('重排序成功！页面元素已重新排序。');
    } catch (e) {
        console.error('Reorder failed:', e);
        alert('重排序失败: ' + e.message);
    } finally {
        reorderingPages.delete(pageId);
        if (currentPageData && currentPageData.id === pageId) {
            reorderBtn.disabled = false;
            reorderBtn.innerHTML = '<i class="fas fa-sort-amount-down"></i> 重排序';
        }
    }
}

function exportDocumentHtmlZip() {
    if (!currentDocId) return;

    try {
        const url = `${API}/api/documents/${currentDocId}/export/html-zip`;
        const a = document.createElement('a');
        a.href = url;
        a.target = '_blank';
        a.click();
    } catch (e) {
        alert('导出失败: ' + e.message);
    }
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAnnotationImageModal();
        closeLlmConfigModal();
    }
});

$('#llm-config-modal').addEventListener('click', (e) => {
    if (e.target.id === 'llm-config-modal') {
        closeLlmConfigModal();
    }
});


let llmModelTypes = {};
let llmConfigsData = {};
let llmCurrentType = 'openai';
let llmEditingConfigId = null;
let llmStatusRefreshTimer = null;

function toggleTopMenu() {
    const dropdown = $('#top-menu-dropdown');
    dropdown.classList.toggle('show');
}

function closeTopMenu() {
    const dropdown = $('#top-menu-dropdown');
    dropdown.classList.remove('show');
}

document.addEventListener('click', (e) => {
    if (!e.target.closest('.top-menu-dropdown')) {
        closeTopMenu();
    }
});

async function initLlmConfigPage() {
    try {
        const [typesRes, configsRes] = await Promise.all([
            fetch(API + '/api/llm-config/types'),
            fetch(API + '/api/llm-config')
        ]);
        const typesData = await typesRes.json();
        llmModelTypes = typesData.model_types;

        const configsData = await configsRes.json();
        llmConfigsData = configsData.configs;
        llmCurrentType = configsData.active_type || 'openai';

        $('#current-active-type').textContent = llmModelTypes[llmCurrentType]?.name || llmCurrentType;

        renderLlmTabs();
        renderLlmConfigsList();
        populateConfigTypeSelect();
        loadResourceStatus();

        if (llmStatusRefreshTimer) {
            clearInterval(llmStatusRefreshTimer);
        }
        llmStatusRefreshTimer = setInterval(loadResourceStatus, 5000);
    } catch (e) {
        console.error('Failed to init LLM config page:', e);
        alert('加载配置失败: ' + e.message);
    }
}

async function loadResourceStatus() {
    try {
        const res = await fetch(API + '/api/model-status');
        const data = await res.json();
        renderResourceStatus(data);
    } catch (e) {
        console.error('Failed to load model status:', e);
    }
}

function renderResourceStatus(data) {
    const gpu = data.gpu || {};
    const yolo = data.yolo || {};
    const surya = data.surya_order || {};

    if (gpu.cuda_available) {
        const deviceName = gpu.device_name || 'Unknown GPU';
        const free = gpu.free_vram_mb || 0;
        const total = gpu.total_vram_mb || 0;
        const used = gpu.used_vram_mb || (total - free);
        const percent = gpu.vram_percent || ((used / total) * 100);
        $('#gpu-status-text').html = '';
        $('#gpu-status-text').innerHTML = `
            <strong>${deviceName}</strong><br>
            已用: ${used.toFixed(0)} MB / ${total.toFixed(0)} MB
        `;
        const bar = $('#gpu-vram-bar');
        bar.classList.remove('hidden');
        const fill = bar.querySelector('.gpu-fill');
        fill.style.width = percent.toFixed(1) + '%';
        if (percent > 85) {
            fill.style.background = '#dc2626';
        } else if (percent > 65) {
            fill.style.background = '#d97706';
        } else {
            fill.style.background = '#059669';
        }
    } else {
        $('#gpu-status-text').innerHTML = `<strong>CPU 模式</strong><br>CUDA 不可用`;
        $('#gpu-vram-bar').classList.add('hidden');
    }

    let yoloStatus = '';
    let yoloMem = '';
    if (yolo.loaded) {
        yoloStatus = yolo.loaded_on_gpu
            ? '<span class="status-ok"><i class="fas fa-check-circle"></i> 已加载 (GPU)</span>'
            : '<span class="status-warn"><i class="fas fa-check-circle"></i> 已加载 (CPU)</span>';
        if (yolo.memory_mb) {
            yoloMem = `占用: ${yolo.memory_mb.toFixed(0)} MB`;
        }
    } else {
        yoloStatus = '<span class="status-off"><i class="fas fa-circle-notch"></i> 未加载</span>';
    }
    $('#yolo-status-text').innerHTML = yoloStatus;
    $('#yolo-mem-text').textContent = yoloMem;

    let suryaStatus = '';
    let suryaMem = '';
    if (surya.loaded) {
        suryaStatus = surya.loaded_on_gpu
            ? '<span class="status-ok"><i class="fas fa-check-circle"></i> 已加载 (GPU)</span>'
            : '<span class="status-warn"><i class="fas fa-check-circle"></i> 已加载 (CPU)</span>';
        if (surya.memory_mb) {
            suryaMem = `占用: ${surya.memory_mb.toFixed(0)} MB`;
        }
    } else {
        suryaStatus = '<span class="status-off"><i class="fas fa-circle-notch"></i> 未加载</span>';
    }
    $('#surya-status-text').innerHTML = suryaStatus;
    $('#surya-mem-text').textContent = suryaMem;
}

function renderLlmTabs() {
    const tabsContainer = $('#llm-tabs');
    const tabsHtml = Object.entries(llmModelTypes).map(([key, info]) => {
        const configs = llmConfigsData[key] || [];
        const activeConfig = configs.find(c => c.is_active);
        const isActive = key === llmCurrentType;
        return `
            <div class="llm-tab ${isActive ? 'active' : ''}" 
                 data-type="${key}" 
                 onclick="switchLlmTab('${key}')">
                <i class="fas ${info.icon}"></i>
                <span class="llm-tab-name">${info.name}</span>
                ${activeConfig ? '<span class="llm-tab-active-dot" title="有激活配置"></span>' : ''}
                <span class="llm-tab-count">${configs.length}</span>
            </div>
        `;
    }).join('');
    tabsContainer.innerHTML = tabsHtml;
}

function switchLlmTab(typeKey) {
    llmCurrentType = typeKey;
    $('#current-active-type').textContent = llmModelTypes[typeKey]?.name || typeKey;
    renderLlmTabs();
    renderLlmConfigsList();
}

function renderLlmConfigsList() {
    const typeInfo = llmModelTypes[llmCurrentType];
    const configs = llmConfigsData[llmCurrentType] || [];
    const listContainer = $('#llm-config-list');
    const tabInfo = $('#tab-type-info');

    tabInfo.innerHTML = `
        <i class="fas ${typeInfo.icon}"></i>
        ${typeInfo.name}
        ${typeInfo.supports_vision 
            ? '<span class="vision-badge"><i class="fas fa-eye"></i> 类型默认支持图生文</span>' 
            : '<span class="no-vision-badge"><i class="fas fa-eye-slash"></i> 类型默认不支持图生文</span>'}
    `;

    if (configs.length === 0) {
        listContainer.innerHTML = `
            <div class="llm-empty">
                <i class="fas fa-inbox"></i>
                <p>暂无 ${typeInfo.name} 配置</p>
                <p class="llm-empty-hint">点击右上角"新建配置"按钮创建一个配置</p>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = configs.map(cfg => {
        const isActive = cfg.is_active;
        return `
            <div class="llm-config-card ${isActive ? 'active' : ''}">
                <div class="llm-config-card-header">
                    <div class="llm-config-title">
                        ${isActive ? '<span class="active-badge"><i class="fas fa-star"></i> 生效中</span>' : ''}
                        <h3><i class="fas ${typeInfo.icon}"></i> ${escapeHtml(cfg.name)}</h3>
                        ${cfg.supports_vision ? '<span class="vision-tag"><i class="fas fa-eye"></i> 支持图生文</span>' : ''}
                    </div>
                    <div class="llm-config-actions">
                        ${!isActive ? `
                            <button class="btn btn-success btn-sm" onclick="activateLlmConfig('${cfg.id}')">
                                <i class="fas fa-check"></i> 设为生效
                            </button>
                        ` : ''}
                        <button class="btn btn-outline btn-sm" onclick="openEditConfigModal('${cfg.id}')">
                            <i class="fas fa-edit"></i> 编辑
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="deleteLlmConfig('${cfg.id}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
                <div class="llm-config-card-body">
                    <div class="config-field">
                        <span class="config-label">模型名称</span>
                        <span class="config-value">${escapeHtml(cfg.model || '-')}</span>
                    </div>
                    <div class="config-field">
                        <span class="config-label">Base URL</span>
                        <span class="config-value config-url">${escapeHtml(cfg.base_url || '-')}</span>
                    </div>
                    <div class="config-field">
                        <span class="config-label">API Key</span>
                        <span class="config-value">${cfg.api_key ? '••••••••' + cfg.api_key.slice(-4) : '未设置'}</span>
                    </div>
                    <div class="config-field-row">
                        <div class="config-field">
                            <span class="config-label">Temperature</span>
                            <span class="config-value">${cfg.temperature}</span>
                        </div>
                        <div class="config-field">
                            <span class="config-label">Max Tokens</span>
                            <span class="config-value">${cfg.max_tokens}</span>
                        </div>
                    </div>
                </div>
                <div class="llm-config-card-footer">
                    <span class="config-meta">创建: ${formatDateTime(cfg.created_at)}</span>
                    <span class="config-meta">更新: ${formatDateTime(cfg.updated_at)}</span>
                </div>
            </div>
        `;
    }).join('');
}

function populateConfigTypeSelect() {
    const select = $('#llm-config-type');
    select.innerHTML = Object.entries(llmModelTypes).map(([key, info]) => `
        <option value="${key}">${info.name}</option>
    `).join('');
}

function openCreateConfigModal() {
    llmEditingConfigId = null;
    $('#llm-config-modal-title').textContent = '新建配置';
    $('#llm-config-name').value = '';
    $('#llm-config-type').value = llmCurrentType;
    const defaults = llmModelTypes[llmCurrentType].defaults;
    $('#llm-config-base-url').value = defaults.base_url || '';
    $('#llm-config-api-key').value = defaults.api_key || '';
    $('#llm-config-model').value = defaults.model || '';
    $('#llm-config-temperature').value = defaults.temperature ?? 0.7;
    $('#llm-config-max-tokens').value = defaults.max_tokens ?? 4096;
    $('#llm-config-supports-vision').checked = !!llmModelTypes[llmCurrentType].supports_vision;
    $('#llm-config-modal').classList.remove('hidden');
}

function openEditConfigModal(configId) {
    const configs = llmConfigsData[llmCurrentType] || [];
    const cfg = configs.find(c => c.id === configId);
    if (!cfg) return;

    llmEditingConfigId = configId;
    $('#llm-config-modal-title').textContent = '编辑配置';
    $('#llm-config-name').value = cfg.name || '';
    $('#llm-config-type').value = cfg.type || llmCurrentType;
    $('#llm-config-base-url').value = cfg.base_url || '';
    $('#llm-config-api-key').value = cfg.api_key || '';
    $('#llm-config-model').value = cfg.model || '';
    $('#llm-config-temperature').value = cfg.temperature ?? 0.7;
    $('#llm-config-max-tokens').value = cfg.max_tokens ?? 4096;
    $('#llm-config-supports-vision').checked = !!cfg.supports_vision;
    $('#llm-config-modal').classList.remove('hidden');
}

function closeLlmConfigModal() {
    $('#llm-config-modal').classList.add('hidden');
    llmEditingConfigId = null;
}

function onLlmConfigTypeChange() {
    const typeKey = $('#llm-config-type').value;
    const defaults = llmModelTypes[typeKey]?.defaults || {};
    if (!llmEditingConfigId) {
        if (defaults.base_url && !$('#llm-config-base-url').value) {
            $('#llm-config-base-url').value = defaults.base_url;
        }
        if (defaults.model && !$('#llm-config-model').value) {
            $('#llm-config-model').value = defaults.model;
        }
        if (defaults.temperature !== undefined) {
            $('#llm-config-temperature').value = defaults.temperature;
        }
        if (defaults.max_tokens !== undefined) {
            $('#llm-config-max-tokens').value = defaults.max_tokens;
        }
        $('#llm-config-supports-vision').checked = !!llmModelTypes[typeKey]?.supports_vision;
    }
}

async function saveLlmConfig() {
    const name = $('#llm-config-name').value.trim();
    if (!name) {
        alert('请输入配置名称');
        return;
    }

    const typeKey = $('#llm-config-type').value;
    const data = {
        name: name,
        base_url: $('#llm-config-base-url').value.trim(),
        api_key: $('#llm-config-api-key').value.trim(),
        model: $('#llm-config-model').value.trim(),
        temperature: parseFloat($('#llm-config-temperature').value),
        max_tokens: parseInt($('#llm-config-max-tokens').value),
        supports_vision: $('#llm-config-supports-vision').checked,
    };

    try {
        let url, method;
        if (llmEditingConfigId) {
            url = `${API}/api/llm-config/${typeKey}/${llmEditingConfigId}`;
            method = 'PUT';
        } else {
            url = `${API}/api/llm-config/${typeKey}`;
            method = 'POST';
        }

        const res = await fetch(url, {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '保存失败');
        }

        await refreshLlmConfigs();
        closeLlmConfigModal();
        alert('保存成功');
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

async function deleteLlmConfig(configId) {
    if (!confirm('确定要删除此配置吗？')) return;

    try {
        const res = await fetch(`${API}/api/llm-config/${llmCurrentType}/${configId}`, {
            method: 'DELETE'
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '删除失败');
        }
        await refreshLlmConfigs();
        alert('删除成功');
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

async function activateLlmConfig(configId) {
    try {
        const res = await fetch(`${API}/api/llm-config/${llmCurrentType}/${configId}/activate`, {
            method: 'PUT'
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '激活失败');
        }
        await refreshLlmConfigs();
        alert('已设为生效配置');
    } catch (e) {
        alert('激活失败: ' + e.message);
    }
}

async function refreshLlmConfigs() {
    try {
        const res = await fetch(API + '/api/llm-config');
        const data = await res.json();
        llmConfigsData = data.configs;
        llmCurrentType = data.active_type || llmCurrentType;
        $('#current-active-type').textContent = llmModelTypes[llmCurrentType]?.name || llmCurrentType;
        renderLlmTabs();
        renderLlmConfigsList();
    } catch (e) {
        console.error('Failed to refresh LLM configs:', e);
    }
}

function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    const icon = btn.querySelector('i');
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}

let searchResults = [];
let currentSearchIndex = -1;
let searchDebounceTimer = null;
let isSearchPanelDragging = false;
let dragOffset = { x: 0, y: 0 };

function handleSearchKeyUp(event) {
    if (event.key === 'Enter') {
        clearTimeout(searchDebounceTimer);
        performSearch();
    } else {
        clearTimeout(searchDebounceTimer);
        searchDebounceTimer = setTimeout(() => {
            performSearch();
        }, 300);
    }
}

async function performSearch() {
    const keyword = $('#pdf-search-input').value.trim();
    const countEl = $('#search-count');
    
    if (!keyword) {
        searchResults = [];
        currentSearchIndex = -1;
        countEl.classList.add('hidden');
        closeSearchResults();
        clearSearchHighlights();
        return;
    }

    if (!currentDocId) {
        return;
    }

    try {
        const res = await fetch(`${API}/api/documents/${currentDocId}/search?q=${encodeURIComponent(keyword)}`);
        const data = await res.json();
        searchResults = data.results || [];
        currentSearchIndex = searchResults.length > 0 ? 0 : -1;

        countEl.textContent = `${searchResults.length} 结果`;
        countEl.classList.remove('hidden');

        if (searchResults.length > 0) {
            renderSearchResults(keyword);
            showSearchResults();
        } else {
            renderSearchResults(keyword);
            showSearchResults();
        }
    } catch (e) {
        console.error('Search failed:', e);
    }
}

function renderSearchResults(keyword) {
    const body = $('#search-results-body');
    
    if (searchResults.length === 0) {
        body.innerHTML = '<div class="search-results-empty">未找到匹配的内容</div>';
        return;
    }

    body.innerHTML = searchResults.map((result, index) => {
        const content = result.content || '';
        const highlightedContent = highlightKeyword(content, keyword);
        const isActive = index === currentSearchIndex;
        
        return `
            <div class="search-result-item ${isActive ? 'active' : ''}" 
                 data-index="${index}" 
                 onclick="goToSearchResult(${index})">
                <div class="search-result-header">
                    <span class="search-result-type">${escapeHtml(result.element_type)}</span>
                    <span class="search-result-page">第 ${result.page_number} 页</span>
                </div>
                <div class="search-result-content">${highlightedContent}</div>
            </div>
        `;
    }).join('');
}

function highlightKeyword(text, keyword) {
    if (!keyword || !text) return escapeHtml(text || '');
    
    const regex = new RegExp(`(${escapeRegExp(keyword)})`, 'gi');
    return escapeHtml(text).replace(regex, '<mark>$1</mark>');
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function showSearchResults() {
    const panel = $('#search-results-panel');
    panel.classList.remove('hidden');
    setupSearchPanelDrag();
}

function closeSearchResults() {
    $('#search-results-panel').classList.add('hidden');
    clearSearchHighlights();
}

function setupSearchPanelDrag() {
    const header = $('#search-results-header');
    const panel = $('#search-results-panel');
    
    header.onmousedown = function(e) {
        isSearchPanelDragging = true;
        const rect = panel.getBoundingClientRect();
        dragOffset.x = e.clientX - rect.left;
        dragOffset.y = e.clientY - rect.top;
        panel.style.right = 'auto';
        panel.style.left = rect.left + 'px';
        panel.style.top = rect.top + 'px';
        
        document.addEventListener('mousemove', onDragMove);
        document.addEventListener('mouseup', onDragEnd);
    };
}

function onDragMove(e) {
    if (!isSearchPanelDragging) return;
    
    const panel = $('#search-results-panel');
    const newX = e.clientX - dragOffset.x;
    const newY = e.clientY - dragOffset.y;
    
    const maxX = window.innerWidth - panel.offsetWidth;
    const maxY = window.innerHeight - panel.offsetHeight;
    
    panel.style.left = Math.max(0, Math.min(newX, maxX)) + 'px';
    panel.style.top = Math.max(0, Math.min(newY, maxY)) + 'px';
}

function onDragEnd() {
    isSearchPanelDragging = false;
    document.removeEventListener('mousemove', onDragMove);
    document.removeEventListener('mouseup', onDragEnd);
}

async function goToSearchResult(index) {
    if (index < 0 || index >= searchResults.length) return;
    
    currentSearchIndex = index;
    const result = searchResults[index];
    
    const pageIndex = currentPages.findIndex(p => p.id === result.page_id);
    if (pageIndex === -1) {
        const pageData = getPageDataByNumber(result.page_number);
        if (pageData) {
            const idx = currentPages.findIndex(p => p.id === pageData.id);
            if (idx !== -1) {
                await loadPage(idx);
            }
        }
    } else {
        await loadPage(pageIndex);
    }
    
    setTimeout(() => {
        highlightSearchResult(result);
    }, 100);
    
    $$('.search-result-item').forEach((item, i) => {
        item.classList.toggle('active', i === index);
    });
    
    const activeItem = document.querySelector(`.search-result-item[data-index="${index}"]`);
    if (activeItem) {
        activeItem.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
}

function highlightSearchResult(result) {
    clearSearchHighlights();
    
    const page = currentPageData;
    if (!page) return;
    
    let jpgWidth = page.jpg_width;
    let jpgHeight = page.jpg_height;
    if (!jpgWidth || !jpgHeight) {
        jpgWidth = page.width * 200 / 72;
        jpgHeight = page.height * 200 / 72;
    }
    
    const canvas = $('#pdf-canvas');
    const canvasRect = canvas.getBoundingClientRect();
    const container = $('#pdf-container');
    const containerRect = container.getBoundingClientRect();
    
    const displayWidth = canvasRect.width;
    const displayHeight = canvasRect.height;
    const offsetX = canvasRect.left - containerRect.left;
    const offsetY = canvasRect.top - containerRect.top;
    
    const scaleX = displayWidth / jpgWidth;
    const scaleY = displayHeight / jpgHeight;
    
    const x = result.bbox_x0 * scaleX + offsetX;
    const y = result.bbox_y0 * scaleY + offsetY;
    const w = (result.bbox_x1 - result.bbox_x0) * scaleX;
    const h = (result.bbox_y1 - result.bbox_y0) * scaleY;
    
    const highlight = document.createElement('div');
    highlight.className = 'search-highlight';
    highlight.id = 'search-highlight-box';
    highlight.style.left = x + 'px';
    highlight.style.top = y + 'px';
    highlight.style.width = w + 'px';
    highlight.style.height = h + 'px';
    
    container.appendChild(highlight);
    
    highlightElement(result.id);
    
    container.scrollTo({
        top: Math.max(0, y - 50),
        behavior: 'smooth'
    });
}

function clearSearchHighlights() {
    const highlight = document.getElementById('search-highlight-box');
    if (highlight) {
        highlight.remove();
    }
}
