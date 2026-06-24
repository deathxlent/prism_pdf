function loadPage(pageIndex) {
    if (pageIndex < 0 || pageIndex >= currentPages.length) return;

    currentPageIndex = pageIndex;
    currentPageData = currentPages[pageIndex];

    renderThumbnails();
    renderPdfPreview();
    renderElementsList();
    updatePageInfo();
    updateUnorderedBadge();
}

function prevPage() {
    if (currentPageIndex > 0) {
        loadPage(currentPageIndex - 1);
    }
}

function nextPage() {
    if (currentPageIndex < currentPages.length - 1) {
        loadPage(currentPageIndex + 1);
    }
}

function updatePageInfo() {
    const info = $('#pdf-page-info');
    if (info && currentPageData) {
        info.textContent = `第 ${currentPageData.page_number} 页`;
    }
}

function updateUnorderedBadge() {
    const badge = $('#unordered-badge');
    if (!badge) return;
    
    if (!currentPageData || currentPageData.is_ordered) {
        badge.classList.add('hidden');
    } else {
        badge.classList.remove('hidden');
    }
}

function renderThumbnails() {
    const container = $('#thumbs-list');
    if (!container) return;

    container.innerHTML = currentPages.map((page, idx) => `
        <div class="thumb-item ${idx === currentPageIndex ? 'active' : ''}" onclick="loadPage(${idx})">
            <img src="assets/page_${page.page_number}.jpg" alt="第 ${page.page_number} 页" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
            <div class="thumb-placeholder" style="display:none;">
                <svg class="icon icon-huge" viewBox="0 0 24 24"><path d="M14,2H6A2,2 0 0,0 4,4V20A2,2 0 0,0 6,22H18A2,2 0 0,0 20,20V8L14,2M14,16V10H10L14,16M19,15V17H5V15H19Z"/></svg>
            </div>
            <div class="thumb-page-num">第 ${page.page_number} 页</div>
        </div>
    `).join('');
}

function renderPdfPreview() {
    const container = $('#pdf-container');
    if (!container || !currentPageData) return;

    const page = currentPageData;
    const pageNum = page.page_number;

    const oldOverlay = selectionOverlay;

    container.innerHTML = `
        <img src="assets/page_${pageNum}.jpg" alt="第 ${pageNum} 页" class="pdf-preview-image" onload="onPdfImageLoad(this)" onerror="this.style.display='none';">
        <div class="annotation-layer" id="annotation-layer"></div>
    `;

    if (oldOverlay && isAddElementMode) {
        selectionOverlay = null;
        selectionRect = null;
        setupSelectionHandlers();
    }
}

function onPdfImageLoad(img) {
    const container = $('#pdf-container');
    const layer = $('#annotation-layer');
    if (!container || !layer) return;

    const containerRect = container.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();
    
    const offsetX = imgRect.left - containerRect.left;
    const offsetY = imgRect.top - containerRect.top;
    const displayWidth = imgRect.width;
    const displayHeight = imgRect.height;
    
    layer.style.left = offsetX + 'px';
    layer.style.top = offsetY + 'px';
    layer.style.width = displayWidth + 'px';
    layer.style.height = displayHeight + 'px';

    currentElements = loadElementsForPage(currentPageData.id);
    renderAnnotations(currentElements, img.naturalWidth, img.naturalHeight, displayWidth, displayHeight);
}

function clearAnnotations() {
    const layer = $('#annotation-layer');
    if (layer) {
        layer.innerHTML = '';
    }
}

function renderAnnotations(elements, imageWidth, imageHeight, displayWidth, displayHeight) {
    const layer = $('#annotation-layer');
    if (!layer || !currentPageData) return;

    const page = currentPageData;
    let jpgWidth = page.jpg_width;
    let jpgHeight = page.jpg_height;
    if (!jpgWidth || !jpgHeight) {
        jpgWidth = imageWidth;
        jpgHeight = imageHeight;
    }
    if (!jpgWidth) jpgWidth = imageWidth;
    if (!jpgHeight) jpgHeight = imageHeight;

    const dispW = displayWidth || imageWidth;
    const dispH = displayHeight || imageHeight;

    clearAnnotations();

    elements.forEach(elem => {
        const x0 = elem.bbox_x0;
        const y0 = elem.bbox_y0;
        const x1 = elem.bbox_x1;
        const y1 = elem.bbox_y1;
        
        if (x0 === undefined || y0 === undefined || x1 === undefined || y1 === undefined) return;

        const scaleX = dispW / jpgWidth;
        const scaleY = dispH / jpgHeight;

        const x = x0 * scaleX;
        const y = y0 * scaleY;
        const w = (x1 - x0) * scaleX;
        const h = (y1 - y0) * scaleY;

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
        const activeBox = layer.querySelector(`.annotation-box[data-element-id="${activeElementId}"]`);
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

function clearHighlights() {
    activeElementId = null;
    $$('.annotation-box').forEach(box => box.classList.add('hidden'));
    $$('.element-card').forEach(card => card.classList.remove('active'));
}

function screenToJpgCoords(screenX0, screenY0, screenX1, screenY1) {
    if (!currentPageData) return null;
    
    const img = document.querySelector('.pdf-preview-image');
    if (!img) return null;
    
    const overlayRect = selectionOverlay.getBoundingClientRect();
    const imgRect = img.getBoundingClientRect();
    
    const offsetX = imgRect.left - overlayRect.left;
    const offsetY = imgRect.top - overlayRect.top;
    
    const canvasX0 = Math.max(0, screenX0 - offsetX);
    const canvasY0 = Math.max(0, screenY0 - offsetY);
    const canvasX1 = Math.min(imgRect.width, screenX1 - offsetX);
    const canvasY1 = Math.min(imgRect.height, screenY1 - offsetY);
    
    const jpgWidth = currentPageData.jpg_width;
    const jpgHeight = currentPageData.jpg_height;
    
    const scaleX = jpgWidth / imgRect.width;
    const scaleY = jpgHeight / imgRect.height;
    
    const jpgX0 = Math.max(0, canvasX0 * scaleX);
    const jpgY0 = Math.max(0, canvasY0 * scaleY);
    const jpgX1 = Math.min(jpgWidth, canvasX1 * scaleX);
    const jpgY1 = Math.min(jpgHeight, canvasY1 * scaleY);
    
    return [jpgX0, jpgY0, jpgX1, jpgY1];
}

function toggleAddElementMode() {
    isAddElementMode = !isAddElementMode;
    const container = $('#pdf-container');
    const addBtn = $('#add-element-btn');
    
    if (isAddElementMode) {
        container.classList.add('add-mode');
        if (addBtn) {
            addBtn.innerHTML = '<svg class="icon icon-small" viewBox="0 0 24 24"><path d="M19,6.41L17.59,5L12,10.59L6.41,5L5,6.41L10.59,12L5,17.59L6.41,19L12,13.41L17.59,19L19,17.59L13.41,12L19,6.41Z"/></svg> 取消';
            addBtn.classList.remove('btn-success');
            addBtn.classList.add('btn-danger');
        }
        setupSelectionHandlers();
    } else {
        container.classList.remove('add-mode');
        if (addBtn) {
            addBtn.innerHTML = '<svg class="icon icon-small" viewBox="0 0 24 24"><path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/></svg> 添加元素';
            addBtn.classList.remove('btn-danger');
            addBtn.classList.add('btn-success');
        }
        clearSelection();
        removeSelectionHandlers();
    }
}

function setupSelectionHandlers() {
    const container = $('#pdf-container');
    if (!container) return;
    
    if (!selectionOverlay) {
        selectionOverlay = document.createElement('div');
        selectionOverlay.className = 'selection-overlay';
        container.appendChild(selectionOverlay);
        
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
    console.log('handleSelectionEnd: jpgCoords =', jpgCoords, 'selectedBbox =', selectedBbox);
    if (jpgCoords) {
        selectedBbox = jpgCoords;
        console.log('Opening modal...');
        openAddElementModal();
    } else {
        console.warn('screenToJpgCoords returned null');
    }
    
    selectionRect.style.display = 'none';
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
    const bboxDisplay = $('#add-element-bbox');
    if (bboxDisplay) {
        bboxDisplay.textContent = bboxStr;
    }
    
    const contentInput = $('#add-element-content');
    if (contentInput) {
        contentInput.value = '';
    }
    
    const typeSelect = $('#add-element-type');
    if (typeSelect) {
        typeSelect.value = 'Text';
    }
    
    pendingNewElement = {
        bbox: bboxToSave
    };
    
    isAddElementMode = false;
    const container = $('#pdf-container');
    const addBtn = $('#add-element-btn');
    container.classList.remove('add-mode');
    if (addBtn) {
        addBtn.innerHTML = '<svg class="icon icon-small" viewBox="0 0 24 24"><path d="M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z"/></svg> 添加元素';
        addBtn.classList.remove('btn-danger');
        addBtn.classList.add('btn-success');
    }
    clearSelection();
    removeSelectionHandlers();
    
    const modal = $('#add-element-modal');
    console.log('modal element:', modal);
    if (modal) {
        modal.classList.remove('hidden');
        console.log('modal classes after:', modal.className);
    }
}

function closeAddElementModal() {
    const modal = $('#add-element-modal');
    if (modal) {
        modal.classList.add('hidden');
    }
    selectedBbox = null;
    pendingNewElement = null;
}

function saveNewElement() {
    if (!pendingNewElement || !pendingNewElement.bbox || !currentPageData) {
        alert('请先框选区域');
        return;
    }
    
    const typeSelect = $('#add-element-type');
    const contentInput = $('#add-element-content');
    
    const elementType = typeSelect ? typeSelect.value : 'Text';
    const content = contentInput ? contentInput.value : '';
    const bbox = pendingNewElement.bbox;
    
    const newElement = {
        id: Date.now(),
        page_id: currentPageData.id,
        element_type: elementType,
        content: content,
        content_format: 'markdown',
        bbox_x0: bbox[0],
        bbox_y0: bbox[1],
        bbox_x1: bbox[2],
        bbox_y1: bbox[3],
        confidence: 1.0,
        reading_order: currentElements.length + 1,
        sort_order: currentElements.length + 1,
        is_ordered: false,
        header_footer_mark: null,
        cross_page_group: null,
        is_cross_page_first: false,
        is_cross_page_part: false,
        translated_content: null,
        image_description: null
    };
    
    currentElements.push(newElement);
    saveElementsForPage(currentPageData.id, currentElements);
    
    renderElementsList();
    renderAnnotations(currentElements, currentPageData.jpg_width, currentPageData.jpg_height, 
        $('#annotation-layer').offsetWidth, $('#annotation-layer').offsetHeight);
    
    closeAddElementModal();
}
