function closeAllModals() {
    $$('.modal').forEach(m => m.classList.add('hidden'));
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAllModals();
        closeSearchResults();
    }
    
    const detailPage = $('#page-detail');
    if (detailPage && detailPage.classList.contains('active')) {
        if (e.key === 'ArrowLeft') {
            prevPage();
        } else if (e.key === 'ArrowRight') {
            nextPage();
        }
    }
});

document.addEventListener('click', (e) => {
    const modals = $$('.modal');
    modals.forEach(modal => {
        if (!modal.classList.contains('hidden')) {
            const modalContent = modal.querySelector('.modal-content');
            if (modalContent && !modalContent.contains(e.target) && !e.target.closest('.selection-overlay')) {
                modal.classList.add('hidden');
            }
        }
    });
    
    const dropdowns = $$('.export-dropdown');
    dropdowns.forEach(d => {
        if (!d.contains(e.target) && !e.target.closest('.btn-group')) {
            d.classList.remove('show');
        }
    });
});

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

function handleSearchKeyUp(event) {
    if (event.key === 'Enter') {
        performSearch();
    }
}

function performSearch() {
    const keyword = $('#pdf-search-input').value.trim().toLowerCase();
    if (!keyword) {
        closeSearchResults();
        return;
    }

    searchResults = [];
    currentPages.forEach(page => {
        const elements = loadElementsForPage(page.id);
        elements.forEach(elem => {
            if (elem.content && elem.content.toLowerCase().includes(keyword)) {
                searchResults.push({
                    page: page,
                    element: elem
                });
            }
        });
    });

    const countEl = $('#search-count');
    if (countEl) {
        countEl.textContent = `${searchResults.length} 结果`;
        countEl.classList.toggle('hidden', searchResults.length === 0);
    }

    if (searchResults.length > 0) {
        showSearchResults();
    }
}

function showSearchResults() {
    const panel = $('#search-results-panel');
    const list = $('#search-results-list');
    
    if (!panel || !list) return;
    
    list.innerHTML = searchResults.map((result, idx) => `
        <div class="search-result-item" onclick="goToSearchResult(${idx})">
            <div class="search-result-page">第 ${result.page.page_number} 页 - ${result.element.element_type}</div>
            <div class="search-result-content">${escapeHtml(result.element.content.substring(0, 100))}...</div>
        </div>
    `).join('');
    
    panel.classList.remove('hidden');
}

function closeSearchResults() {
    const panel = $('#search-results-panel');
    if (panel) panel.classList.add('hidden');
    const countEl = $('#search-count');
    if (countEl) countEl.classList.add('hidden');
    searchResults = [];
    currentSearchIndex = -1;
}

function goToSearchResult(index) {
    if (index < 0 || index >= searchResults.length) return;
    
    const result = searchResults[index];
    const pageIndex = currentPages.findIndex(p => p.id === result.page.id);
    if (pageIndex >= 0) {
        loadPage(pageIndex);
        setTimeout(() => {
            highlightElement(result.element.id);
        }, 300);
    }
    
    closeSearchResults();
}
