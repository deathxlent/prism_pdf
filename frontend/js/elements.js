function renderElements() {
    const container = $('#elements-list');
    container.classList.toggle('edit-order-mode', isEditOrderMode);

    if (!currentElements || currentElements.length === 0) {
        container.innerHTML = '<p class="empty-msg">当前页面暂无解析元素</p>';
        return;
    }

    const sorted = [...currentElements].sort((a, b) => a.reading_order - b.reading_order);
    const hasLlm = !!activeLlmConfig;
    const hasVision = hasLlm && activeLlmConfig.supports_vision;

    container.innerHTML = sorted.map((elem, idx) => {
        const type = elem.element_type.toLowerCase();
        const isImage = elem.content_format === 'image_path';
        const isPicture = elem.element_type === 'Picture';
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

        let descHtml = '';
        if (isPicture && elem.image_description) {
            descHtml = `<div class="element-image-desc"><i class="fas fa-image"></i> ${escapeHtml(elem.image_description)}</div>`;
        }

        let translatedHtml = '';
        if (elem.translated_content) {
            translatedHtml = `<div class="element-translated"><i class="fas fa-language"></i> ${escapeHtml(elem.translated_content)}</div>`;
        }

        let extraBtns = '';
        if (isPicture && hasVision) {
            extraBtns += `<button class="btn btn-info btn-sm describe-btn" onclick="event.stopPropagation(); describeImage(${elem.id})" title="AI生成图片描述">
                <i class="fas fa-magic"></i> 描述
            </button>`;
        }
        if (hasLlm && (isPicture ? !!elem.image_description : !!(elem.content || '').trim())) {
            extraBtns += `<button class="btn btn-info btn-sm translate-btn" onclick="event.stopPropagation(); showElementTranslateLanguageSelect(${elem.id})" title="翻译此解析项">
                <i class="fas fa-language"></i> 翻译
            </button>`;
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
                ${descHtml}
                ${translatedHtml}
                <div class="element-footer">
                    <button class="btn btn-outline btn-sm edit-btn" onclick="event.stopPropagation(); openEditModal(${elem.id})">
                        <i class="fas fa-edit"></i> 编辑
                    </button>
                    ${extraBtns}
                    <button class="btn btn-outline btn-sm delete-btn" onclick="event.stopPropagation(); deleteElement(${elem.id})">
                        <i class="fas fa-trash"></i> 删除
                    </button>
                </div>
            </div>
        `;
    }).join('');
}

function openEditModal(elementId) {
    const elem = currentElements.find(e => e.id === elementId);
    if (!elem) return;

    editingElementId = elementId;
    $('#edit-type').value = elem.element_type;
    $('#edit-content').value = elem.content || '';

    const transGroup = $('#edit-translated-group');
    const transField = $('#edit-translated');
    if (elem.translated_content) {
        transField.value = elem.translated_content;
        transGroup.style.display = '';
    } else {
        transField.value = '';
        transGroup.style.display = 'none';
    }

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
    const newTranslated = $('#edit-translated').value;

    const body = {
        element_type: newType,
        content: newContent
    };
    if (newTranslated !== undefined) {
        body.translated_content = newTranslated;
    }

    try {
        const updated = await apiUpdateElement(editingElementId, body);
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

async function deleteElement(elementId) {
    if (!confirm('确定要删除这个元素吗？')) return;
    
    try {
        await apiDeleteElement(elementId);
        
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
        await apiReorderElements(currentPageData.id, elementOrder);

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
        const newElement = await apiCreateElement(currentPageData.id, {
            element_type: elementType,
            bbox: bbox,
            content: content,
            content_format: 'markdown',
            confidence: 1.0
        });
        
        currentElements.push(newElement);
        renderElements();
        closeAddElementModal();
        
        alert('元素添加成功');
    } catch (e) {
        alert('添加元素失败: ' + e.message);
    }
}

async function describeImage(elementId) {
    try {
        const result = await apiDescribeImage(elementId);
        const idx = currentElements.findIndex(e => e.id === elementId);
        if (idx !== -1) {
            currentElements[idx].image_description = result.image_description;
        }
        renderElements();
        alert('图片描述已生成');
    } catch (e) {
        alert('生成图片描述失败: ' + e.message);
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
        const result = await apiReorderPage(pageId);
        
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

async function showRawLayoutData() {
    if (!currentPageData) return;
    
    try {
        const data = await apiGetRawLayout(currentPageData.id);
        
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
