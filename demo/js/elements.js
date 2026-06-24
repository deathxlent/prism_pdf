function renderElementsList() {
    const container = $('#elements-list');
    if (!container) return;

    if (!currentPageData) {
        container.innerHTML = '<p class="empty-msg">请先选择页面</p>';
        return;
    }

    currentElements = loadElementsForPage(currentPageData.id);
    
    if (!currentElements || currentElements.length === 0) {
        container.innerHTML = '<p class="empty-msg">当前页面暂无解析元素</p>';
        return;
    }

    const sorted = [...currentElements].sort((a, b) => a.reading_order - b.reading_order);
    const unordered = currentElements.filter(e => !e.is_ordered);

    let html = '';
    
    if (unordered.length > 0) {
        html += `<div class="unordered-badge">
            <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M13,14H11V10H13M13,18H11V16H13M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2Z"/></svg>
            ${unordered.length} 个元素未排序
        </div>`;
    }

    sorted.forEach((elem, idx) => {
        const type = elem.element_type.toLowerCase();
        const isPicture = elem.element_type === 'Picture';
        const isHeaderFooter = elem.header_footer_mark === 'header' || elem.header_footer_mark === 'footer';
        let contentHtml = '';

        if (elem.content_format === 'html') {
            contentHtml = elem.content || '(空)';
        } else if (elem.content_format === 'latex') {
            contentHtml = `<code>${escapeHtml(elem.content || '(空)')}</code>`;
        } else if (elem.content_format === 'image_path') {
            contentHtml = `<img src="${elem.content}" alt="图片">`;
        } else {
            contentHtml = renderMarkdownSimple(elem.content || '(空)');
        }

        let descHtml = '';
        if (isPicture && elem.image_description) {
            descHtml = `<div class="element-image-desc"><svg class="icon icon-small" viewBox="0 0 24 24"><path d="M21,19V5C21,3.89 20.1,3 19,3H5C3.89,3 3,3.89 3,5V19A2,2 0 0,0 5,21H19A2,2 0 0,0 21,19M8.5,13.5L11,16.5L14.5,12L19,18H5L8.5,13.5Z"/></svg> ${escapeHtml(elem.image_description)}</div>`;
        }

        let translatedHtml = '';
        if (elem.translated_content) {
            translatedHtml = `<div class="element-translated"><svg class="icon icon-small" viewBox="0 0 24 24"><path d="M12.87,15.07L10.33,12.56L10.36,12.53C12.1,10.59 13.34,8.36 14.07,6H17V4H10V2H8V4H1V6H12.17C11.5,7.92 10.44,9.75 9,11.35C8.07,10.32 7.3,9.19 6.69,8H4.69C5.42,9.63 6.42,11.17 7.67,12.56L2.58,17.58L4,19L9,14L12.11,17.11L12.87,15.07M18.5,10H16.5L12,22H14L15.12,19H19.87L21,22H23L18.5,10M15.88,17L17.5,12.67L19.12,17H15.88Z"/></svg> ${escapeHtml(elem.translated_content)}</div>`;
        }

        let headerFooterBadge = '';
        if (isHeaderFooter) {
            const badgeText = elem.header_footer_mark === 'header' ? '页眉' : '页脚';
            headerFooterBadge = `<span class="header-footer-badge" title="被标记为${badgeText}区域"><svg class="icon icon-small" viewBox="0 0 24 24"><path d="${elem.header_footer_mark === 'header' ? 'M7,14L12,9L17,14H7Z' : 'M7,10L12,15L17,10H7Z'}"/></svg> ${badgeText}</span>`;
        }

        let crossPageBadge = '';
        if (elem.element_type === 'Table' && elem.cross_page_group !== undefined && elem.cross_page_group !== null) {
            const isCrossPageFirst = elem.is_cross_page_first === true;
            const isCrossPagePart = elem.is_cross_page_part === true;
            if (isCrossPageFirst) {
                crossPageBadge = `<span class="cross-page-badge" title="跨页表格（起始页）"><svg class="icon icon-small" viewBox="0 0 24 24"><path d="M3,3H21V21H3V3M5,5V10H10V5M11,5V10H16V5M17,5V10H19V5M5,11V16H10V11M11,11V16H16V11M17,11V16H19V11M5,17V19H10V17M11,17V19H16V17M17,17V19H19V17Z"/></svg> 跨页表格</span>`;
            } else if (isCrossPagePart) {
                crossPageBadge = `<span class="cross-page-badge cross-page-part" title="跨页表格（被合并部分）"><svg class="icon icon-small" viewBox="0 0 24 24"><path d="M3,3H21V21H3V3M5,5V10H10V5M11,5V10H16V5M17,5V10H19V5M5,11V16H10V11M11,11V16H16V11M17,11V16H19V11M5,17V19H10V17M11,17V19H16V17M17,17V19H19V17Z"/></svg> 跨页续表</span>`;
            }
        }

        const confidence = elem.confidence ? (elem.confidence * 100).toFixed(1) + '%' : '';
        const orderNum = elem.reading_order || idx + 1;

        html += `
            <div class="element-card ${isHeaderFooter ? 'header-footer-element' : ''} ${activeElementId === elem.id ? 'active' : ''}" 
                 data-element-id="${elem.id}"
                 data-order="${orderNum}"
                 draggable="${isEditOrderMode}"
                 ondragstart="handleDragStart(event, ${elem.id})"
                 ondragend="handleDragEnd(event)"
                 ondragover="handleDragOver(event)"
                 ondragleave="handleDragLeave(event)"
                 ondrop="handleDrop(event, ${elem.id})">
                <div class="element-header" onclick="highlightElement(${elem.id})">
                    <span class="drag-handle" onclick="event.stopPropagation()">
                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M11,18V16H13V18H11M11,12V10H13V12H11M11,6V4H13V6H11M15,18V16H17V18H15M15,12V10H17V12H15M15,6V4H17V6H15M7,18V16H9V18H7M7,12V10H9V12H7M7,6V4H9V6H7Z"/></svg>
                    </span>
                    <span class="element-type ${type}">${elem.element_type}</span>
                    <span class="element-order">#${orderNum}</span>
                    <span class="element-confidence">${confidence}</span>
                    ${headerFooterBadge}
                    ${crossPageBadge}
                </div>
                <div class="element-content markdown" onclick="highlightElement(${elem.id})">
                    ${contentHtml}
                </div>
                ${descHtml}
                ${translatedHtml}
                <div class="element-footer">
                    <button class="btn btn-sm btn-outline" onclick="event.stopPropagation(); openEditModal(${elem.id})">
                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M20.71,7.04C21.1,6.65 21.1,6 20.71,5.63L18.37,3.29C18,2.9 17.35,2.9 16.96,3.29L15.12,5.12L18.87,8.87M3,17.25V21H6.75L17.81,9.93L14.06,6.18L3,17.25Z"/></svg>
                        编辑
                    </button>
                    <button class="btn btn-sm btn-outline" onclick="event.stopPropagation(); showDemoNotice('翻译')">
                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M12.87,15.07L10.33,12.56L10.36,12.53C12.1,10.59 13.34,8.36 14.07,6H17V4H10V2H8V4H1V6H12.17C11.5,7.92 10.44,9.75 9,11.35C8.07,10.32 7.3,9.19 6.69,8H4.69C5.42,9.63 6.42,11.17 7.67,12.56L2.58,17.58L4,19L9,14L12.11,17.11L12.87,15.07M18.5,10H16.5L12,22H14L15.12,19H19.87L21,22H23L18.5,10M15.88,17L17.5,12.67L19.12,17H15.88Z"/></svg>
                        翻译
                    </button>
                    ${isPicture ? `<button class="btn btn-sm btn-outline" onclick="event.stopPropagation(); showDemoNotice('生成描述')">
                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M12,2A10,10 0 0,0 2,12A10,10 0 0,0 12,22A10,10 0 0,0 22,12A10,10 0 0,0 12,2M12,4A8,8 0 0,1 20,12A8,8 0 0,1 12,20A8,8 0 0,1 4,12A8,8 0 0,1 12,4M12,6A6,6 0 0,0 6,12A6,6 0 0,0 12,18A6,6 0 0,0 18,12A6,6 0 0,0 12,6M12,8A4,4 0 0,1 16,12A4,4 0 0,1 12,16A4,4 0 0,1 8,12A4,4 0 0,1 12,8Z"/></svg>
                        描述
                    </button>` : ''}
                    <button class="btn btn-sm btn-danger" onclick="event.stopPropagation(); deleteElement(${elem.id})">
                        <svg class="icon icon-small" viewBox="0 0 24 24"><path d="M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z"/></svg>
                    </button>
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
    container.classList.toggle('edit-order-mode', isEditOrderMode);
}

function selectElement(elementId) {
    highlightElement(elementId);
}

function deleteElement(elementId) {
    if (!confirm('确定要删除这个元素吗？')) return;
    
    currentElements = currentElements.filter(e => e.id !== elementId);
    saveElementsForPage(currentPageData.id, currentElements);
    
    if (activeElementId === elementId) {
        clearHighlights();
        activeElementId = null;
    }
    
    renderElementsList();
}

function openEditModal(elementId) {
    const elem = currentElements.find(e => e.id == elementId);
    if (!elem) return;

    editingElementId = elementId;
    const typeInput = $('#edit-type');
    const contentInput = $('#edit-content');
    const transGroup = $('#edit-translated-group');
    const transField = $('#edit-translated');
    
    if (typeInput) typeInput.value = elem.element_type;
    if (contentInput) contentInput.value = elem.content || '';

    if (transField && transGroup) {
        if (elem.translated_content) {
            transField.value = elem.translated_content;
            transGroup.style.display = '';
        } else {
            transField.value = '';
            transGroup.style.display = 'none';
        }
    }

    const modal = $('#edit-modal');
    if (modal) modal.classList.remove('hidden');
}

function closeEditModal() {
    const modal = $('#edit-modal');
    if (modal) modal.classList.add('hidden');
    editingElementId = null;
}

function saveElementEdit() {
    if (!editingElementId) return;

    const elem = currentElements.find(e => e.id == editingElementId);
    if (!elem) return;

    const typeInput = $('#edit-type');
    const contentInput = $('#edit-content');
    const translatedInput = $('#edit-translated');

    if (typeInput) elem.element_type = typeInput.value;
    if (contentInput) elem.content = contentInput.value;
    if (translatedInput && translatedInput.value) {
        elem.translated_content = translatedInput.value;
    }

    saveElementsForPage(currentPageData.id, currentElements);
    
    closeEditModal();
    renderElementsList();
    
    const img = document.querySelector('.pdf-preview-image');
    if (img) {
        const container = $('#pdf-container');
        const layer = $('#annotation-layer');
        if (container && layer) {
            const containerRect = container.getBoundingClientRect();
            const imgRect = img.getBoundingClientRect();
            layer.style.left = (imgRect.left - containerRect.left) + 'px';
            layer.style.top = (imgRect.top - containerRect.top) + 'px';
            layer.style.width = imgRect.width + 'px';
            layer.style.height = imgRect.height + 'px';
            renderAnnotations(currentElements, img.naturalWidth, img.naturalHeight, imgRect.width, imgRect.height);
        }
    }
}

function toggleAnnotations() {
    showAnnotations = !showAnnotations;
    renderAnnotations();
}

function toggleEditOrder() {
    isEditOrderMode = !isEditOrderMode;
    
    const editBtn = $('#edit-order-btn');
    const saveBtn = $('#save-order-btn');
    const cancelBtn = $('#cancel-order-btn');
    const container = $('#elements-list');

    if (isEditOrderMode) {
        originalOrder = [...currentElements];
        if (editBtn) editBtn.classList.add('hidden');
        if (saveBtn) saveBtn.classList.remove('hidden');
        if (cancelBtn) cancelBtn.classList.remove('hidden');
        if (container) container.classList.add('edit-order-mode');
    } else {
        if (editBtn) editBtn.classList.remove('hidden');
        if (saveBtn) saveBtn.classList.add('hidden');
        if (cancelBtn) cancelBtn.classList.add('hidden');
        if (container) container.classList.remove('edit-order-mode');
    }
    
    renderElementsList();
}

function saveOrder() {
    currentElements.forEach((elem, idx) => {
        elem.reading_order = idx + 1;
        elem.sort_order = idx + 1;
    });
    saveElementsForPage(currentPageData.id, currentElements);
    
    isEditOrderMode = false;
    const editBtn = $('#edit-order-btn');
    const saveBtn = $('#save-order-btn');
    const cancelBtn = $('#cancel-order-btn');
    const container = $('#elements-list');
    
    if (editBtn) editBtn.classList.remove('hidden');
    if (saveBtn) saveBtn.classList.add('hidden');
    if (cancelBtn) cancelBtn.classList.add('hidden');
    if (container) container.classList.remove('edit-order-mode');
    
    renderElementsList();
}

function cancelOrder() {
    currentElements = [...originalOrder];
    isEditOrderMode = false;
    const editBtn = $('#edit-order-btn');
    const saveBtn = $('#save-order-btn');
    const cancelBtn = $('#cancel-order-btn');
    const container = $('#elements-list');
    
    if (editBtn) editBtn.classList.remove('hidden');
    if (saveBtn) saveBtn.classList.add('hidden');
    if (cancelBtn) cancelBtn.classList.add('hidden');
    if (container) container.classList.remove('edit-order-mode');
    
    renderElementsList();
}

function handleDragStart(e, elementId) {
    if (!isEditOrderMode) return;
    e.target.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', elementId);
}

function handleDragEnd(e) {
    if (!isEditOrderMode) return;
    e.target.classList.remove('dragging');
    $$('.element-card').forEach(card => card.classList.remove('drag-over'));
}

function handleDragOver(e) {
    if (!isEditOrderMode) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    const target = e.currentTarget;
    if (target) {
        target.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    if (!isEditOrderMode) return;
    e.currentTarget.classList.remove('drag-over');
}

function handleDrop(e, targetId) {
    if (!isEditOrderMode) return;
    e.preventDefault();
    e.currentTarget.classList.remove('drag-over');
    
    const draggedId = e.dataTransfer.getData('text/plain');
    if (!draggedId || draggedId === targetId.toString()) return;

    const draggedIdx = currentElements.findIndex(e => e.id == draggedId);
    const targetIdx = currentElements.findIndex(e => e.id == targetId);

    if (draggedIdx === -1 || targetIdx === -1) return;

    const [draggedElem] = currentElements.splice(draggedIdx, 1);
    currentElements.splice(targetIdx, 0, draggedElem);

    currentElements.forEach((elem, idx) => {
        elem.reading_order = idx + 1;
        elem.sort_order = idx + 1;
    });

    saveElementsForPage(currentPageData.id, currentElements);
    renderElementsList();
    renderAnnotations();
}
