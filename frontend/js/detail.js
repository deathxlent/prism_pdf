async function loadDocumentDetail(docId) {
    currentDocId = docId;

    try {
        const [docRes, statusRes, llmRes] = await Promise.all([
            apiGetResults(docId),
            apiGetStatus(docId),
            getLlmActiveConfig().catch(() => null)
        ]);

        activeLlmConfig = llmRes;

        currentDocument = docRes.document;
        currentPages = docRes.pages || [];
        updatePageNumbers();

        if (statusRes.status === 'processing' || statusRes.status.startsWith('parsing')) {
            startProgressPolling(docId);
        }

        $('#detail-title').textContent = docRes.document.original_filename;
        $('#detail-status').textContent = getStatusText(statusRes.status);
        $('#detail-status').className = 'status-badge status-' + statusRes.status;

        const progressContainer = $('#detail-progress-container');
        if (statusRes.status === 'processing' || statusRes.status.startsWith('parsing')) {
            progressContainer.classList.remove('hidden');
        } else {
            progressContainer.classList.add('hidden');
        }

        updateLlmButtons();
        updateExportDropdownVisibility();
        renderThumbnails();

        if (currentPages.length > 0) {
            loadPage(0);
        } else {
            clearPageView();
        }
    } catch (e) {
        console.error('Failed to load document:', e);
        alert('加载文档失败: ' + e.message);
        navigateTo('home');
    }
}

function updatePageNumbers() {
    if (!currentPages || currentPages.length === 0) return;
    currentPages.forEach((page, index) => {
        page.page_number = page.page_number || (index + 1);
    });
}

function renderThumbnails() {
    const container = $('#thumbs-list');
    if (!currentPages || currentPages.length === 0) {
        container.innerHTML = '<p class="empty-msg">暂无页面</p>';
        return;
    }

    container.innerHTML = currentPages.map((page, idx) => {
        const thumbnail = page.id ? 
            `<img src="${API}/api/pages/${page.id}/jpg" alt="第 ${page.page_number} 页" loading="lazy" onerror="this.outerHTML='<div class=\\'thumb-placeholder\\'>第 ${page.page_number} 页</div>'">` :
            `<div class="thumb-placeholder">第 ${page.page_number} 页</div>`;

        const unorderedBadge = page.is_ordered === false ? 
            '<div class="thumb-unordered" title="未排序"><i class="fas fa-exclamation-triangle"></i></div>' : '';

        return `
            <div class="thumb-item ${idx === currentPageIndex ? 'active' : ''}" 
                 onclick="goToPage(${idx})"
                 data-page-index="${idx}">
                ${thumbnail}
                ${unorderedBadge}
                <div class="thumb-page-num">第 ${page.page_number} 页</div>
            </div>
        `;
    }).join('');
}

function clearPageView() {
    currentPageData = null;
    currentElements = [];
    activeElementId = null;
    const canvas = $('#pdf-canvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    $('#elements-list').innerHTML = '<p class="empty-msg">请选择一个页面查看</p>';
    clearAnnotations();
}

async function loadPage(pageIndex) {
    if (!currentPages || pageIndex < 0 || pageIndex >= currentPages.length) return;

    currentPageIndex = pageIndex;
    const page = currentPages[pageIndex];
    currentPageData = page;

    $$('.thumb-item').forEach((item, idx) => {
        item.classList.toggle('active', idx === pageIndex);
    });

    const pageInfo = $('#pdf-page-info');
    if (pageInfo) pageInfo.textContent = `第 ${page.page_number} / ${currentPages.length} 页`;

    try {
        const elements = await apiGetPageElements(page.id);
        currentElements = elements.elements || [];
        currentPageData.is_ordered = elements.is_ordered;

        const unorderedBadge = $('#unordered-badge');
        if (unorderedBadge) {
            unorderedBadge.classList.toggle('hidden', elements.is_ordered);
        }

        if (isEditOrderMode) {
            cancelOrder();
        }

        if (isAddElementMode) {
            toggleAddElementMode();
        }

        await renderPdfPage(page);
        renderElements();

        const reorderBtn = $('#reorder-btn');
        if (reorderBtn) {
            if (reorderingPages.has(page.id)) {
                reorderBtn.disabled = true;
                reorderBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 排序中...';
            } else {
                reorderBtn.disabled = false;
                reorderBtn.innerHTML = '<i class="fas fa-sort-amount-down"></i> 重排序';
            }
        }
    } catch (e) {
        console.error('Failed to load page:', e);
        currentElements = [];
        renderElements();
    }
}

function goToPage(pageIndex) {
    if (pageIndex < 0 || pageIndex >= currentPages.length) return;
    loadPage(pageIndex);
}

function prevPage() {
    if (currentPageIndex > 0) {
        goToPage(currentPageIndex - 1);
    }
}

function nextPage() {
    if (currentPageIndex < currentPages.length - 1) {
        goToPage(currentPageIndex + 1);
    }
}

function zoomIn() {
    currentScale = Math.min(currentScale * 1.2, 3);
    if (currentPageData) {
        renderPdfPage(currentPageData);
    }
}

function zoomOut() {
    currentScale = Math.max(currentScale / 1.2, 0.5);
    if (currentPageData) {
        renderPdfPage(currentPageData);
    }
}

function startProgressPolling(docId) {
    if (progressPollInterval) {
        clearInterval(progressPollInterval);
    }

    progressPollInterval = setInterval(async () => {
        try {
            const progress = await apiGetProgress(docId);
            updateProgressDisplay(progress);
            
            if (progress.status === 'completed' || progress.status === 'failed') {
                clearInterval(progressPollInterval);
                progressPollInterval = null;
                
                if (progress.status === 'completed') {
                    loadDocuments();
                    loadDocumentDetail(docId);
                }
            }
        } catch (e) {
            console.error('Progress polling error:', e);
        }
    }, 2000);
}

function updateProgressDisplay(progress) {
    const bar = $('#detail-progress-fill');
    const text = $('#detail-progress-text');
    const msg = $('#detail-progress-message');
    const status = $('#detail-status');
    const container = $('#detail-progress-container');
    
    if (container) container.classList.remove('hidden');
    if (bar && text) {
        const pct = progress.percentage || 0;
        bar.style.width = pct + '%';
        text.textContent = pct.toFixed(1) + '%';
    }
    if (msg) {
        msg.textContent = progress.message || '';
    }
    if (status) {
        status.textContent = getStatusText(progress.status);
        status.className = 'status-badge status-' + progress.status;
    }
}

async function reparseDocument() {
    if (!currentDocId) return;
    if (!confirm('确定要重新解析此文档吗？这将清除现有解析结果。')) return;
    
    showLoading('正在启动重新解析...');
    try {
        await apiReparseDocument(currentDocId);
        hideLoading();
        alert('重解析已开始，请稍候...');
        startProgressPolling(currentDocId);
    } catch (e) {
        hideLoading();
        alert('启动重解析失败: ' + e.message);
    }
}

function backToDocuments() {
    if (progressPollInterval) {
        clearInterval(progressPollInterval);
        progressPollInterval = null;
    }
    currentDocId = null;
    navigateTo('home');
}

async function toggleDetailExportDropdown(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('detail-export-dropdown');
    
    document.querySelectorAll('.export-dropdown').forEach(d => {
        if (d !== dropdown) {
            d.classList.remove('show');
        }
    });
    
    await updateExportDropdownVisibility();
    dropdown.classList.toggle('show');
}

async function togglePageExportDropdown(event) {
    event.stopPropagation();
    const dropdown = document.getElementById('page-export-dropdown');
    
    document.querySelectorAll('.export-dropdown').forEach(d => {
        if (d !== dropdown) {
            d.classList.remove('show');
        }
    });
    
    await updateExportDropdownVisibility();
    dropdown.classList.toggle('show');
}
