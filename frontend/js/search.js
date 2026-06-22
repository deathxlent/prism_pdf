function setupSearch() {
    const searchInput = $('#pdf-search-input');
    if (!searchInput) return;

    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchDebounceTimer);
        const query = e.target.value.trim();
        if (query.length < 2) {
            clearSearchResults();
            return;
        }
        searchDebounceTimer = setTimeout(() => {
            performSearch(query);
        }, 300);
    });

    const panel = $('#search-results-panel');
    const header = $('#search-results-header');
    
    if (panel && header) {
        header.addEventListener('mousedown', (e) => {
            isSearchPanelDragging = true;
            const rect = panel.getBoundingClientRect();
            dragOffset.x = e.clientX - rect.left;
            dragOffset.y = e.clientY - rect.top;
            
            document.addEventListener('mousemove', onSearchPanelDrag);
            document.addEventListener('mouseup', () => {
                isSearchPanelDragging = false;
                document.removeEventListener('mousemove', onSearchPanelDrag);
            });
            e.preventDefault();
        });
    }
}

function handleSearchKeyUp(e) {
    const input = $('#pdf-search-input');
    if (!input) return;
    
    if (e.key === 'Enter') {
        const query = input.value.trim();
        if (query.length >= 2) {
            performSearch(query);
        }
    } else if (e.key === 'Escape') {
        clearSearchResults();
        input.value = '';
        input.blur();
    }
}

function onSearchPanelDrag(e) {
    const panel = $('#search-results-panel');
    if (!panel) return;
    
    const container = $('.detail-container');
    const containerRect = container.getBoundingClientRect();
    
    let left = e.clientX - containerRect.left - dragOffset.x;
    let top = e.clientY - containerRect.top - dragOffset.y;
    
    const maxLeft = containerRect.width - panel.offsetWidth;
    const maxTop = containerRect.height - 100;
    
    left = Math.max(0, Math.min(left, maxLeft));
    top = Math.max(0, Math.min(top, maxTop));
    
    panel.style.left = left + 'px';
    panel.style.top = top + 'px';
}

async function performSearch(keyword) {
    if (!keyword || keyword.length < 2 || !currentDocId) {
        clearSearchResults();
        return;
    }

    try {
        const data = await apiSearchDocument(currentDocId, keyword);
        searchResults = data.results || [];
        currentSearchIndex = -1;
        
        renderSearchResults(keyword);
        
        const countEl = $('#search-count');
        if (countEl) {
            if (searchResults.length > 0) {
                countEl.textContent = `${searchResults.length} 结果`;
                countEl.classList.remove('hidden');
            } else {
                countEl.classList.add('hidden');
            }
        }
        
        const panel = $('#search-results-panel');
        if (panel && searchResults.length > 0) {
            panel.classList.remove('hidden');
        }
    } catch (e) {
        console.error('Search failed:', e);
    }
}

function renderSearchResults(keyword) {
    const body = $('#search-results-body');
    if (!body) return;

    if (searchResults.length === 0) {
        body.innerHTML = '<div class="search-results-empty">未找到匹配内容</div>';
        return;
    }

    const grouped = {};
    for (const result of searchResults) {
        if (!grouped[result.page_number]) {
            grouped[result.page_number] = [];
        }
        grouped[result.page_number].push(result);
    }

    let html = '';
    const sortedPages = Object.keys(grouped).sort((a, b) => parseInt(a) - parseInt(b));
    
    for (const pageNum of sortedPages) {
        const pageResults = grouped[pageNum];
        html += `
            <div class="search-page-group">
                <div class="search-page-title" onclick="goToSearchPage(${pageNum})">
                    <i class="fas fa-file-alt"></i>
                    第 ${pageNum} 页
                    <span class="search-page-count">${pageResults.length} 处</span>
                </div>
        `;
        
        for (let i = 0; i < pageResults.length; i++) {
            const result = pageResults[i];
            const globalIndex = searchResults.findIndex(r => 
                r.page_number === parseInt(pageNum) && r.element_id === result.element_id && r.content === result.content
            );
            html += `
                <div class="search-result-item ${globalIndex === currentSearchIndex ? 'active' : ''}"
                     onclick="goToSearchResult(${globalIndex})">
                    <div class="search-result-type ${result.element_type.toLowerCase()}">
                        ${result.element_type}
                    </div>
                    <div class="search-result-text">
                        ${highlightKeyword(result.content, keyword)}
                    </div>
                </div>
            `;
        }
        
        html += '</div>';
    }

    body.innerHTML = html;
}

function clearSearchResults() {
    searchResults = [];
    currentSearchIndex = -1;
    
    const body = $('#search-results-body');
    if (body) body.innerHTML = '<div class="search-results-empty">请输入关键词进行搜索</div>';
    
    const countEl = $('#search-count');
    if (countEl) countEl.classList.add('hidden');
    
    const panel = $('#search-results-panel');
    if (panel) panel.classList.add('hidden');
    
    $$('.element-content mark').forEach(mark => {
        const parent = mark.parentNode;
        const text = document.createTextNode(mark.textContent);
        parent.replaceChild(text, mark);
        parent.normalize();
    });
}

function closeSearchResults() {
    const panel = $('#search-results-panel');
    if (panel) panel.classList.add('hidden');
}

function goToSearchPage(pageNum) {
    if (!currentPages || currentPages.length === 0) return;
    
    const idx = currentPages.findIndex(p => p.page_number === pageNum);
    if (idx >= 0) {
        goToPage(idx);
    }
}

function goToSearchResult(index) {
    if (index < 0 || index >= searchResults.length) return;
    
    const result = searchResults[index];
    currentSearchIndex = index;
    
    goToSearchPage(result.page_number);
    
    setTimeout(() => {
        highlightElement(result.element_id);
        
        const items = document.querySelectorAll('.search-result-item');
        items.forEach((item, i) => {
            item.classList.toggle('active', i === index);
        });
        
        const activeItem = document.querySelector('.search-result-item.active');
        if (activeItem) {
            activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }
    }, 300);
}

function navigateSearchResult(direction) {
    if (searchResults.length === 0) return;
    
    let newIndex = currentSearchIndex + direction;
    if (newIndex < 0) newIndex = searchResults.length - 1;
    if (newIndex >= searchResults.length) newIndex = 0;
    
    goToSearchResult(newIndex);
}
