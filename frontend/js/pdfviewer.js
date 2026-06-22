pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

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

function clearHighlights() {
    activeElementId = null;
    $$('.annotation-box').forEach(box => box.classList.add('hidden'));
    $$('.element-card').forEach(card => card.classList.remove('active'));
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

function getPageDataByNumber(pageNum) {
    return currentPages.find(p => p.page_number === pageNum) || null;
}
