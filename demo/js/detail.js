function initDetailPage() {
    setupDetailNavigation();
    setupPdfSearch();
}

function setupDetailNavigation() {
    const prevBtn = $('#prev-page-btn');
    const nextBtn = $('#next-page-btn');
    
    if (prevBtn) {
        prevBtn.addEventListener('click', () => prevPage());
    }
    
    if (nextBtn) {
        nextBtn.addEventListener('click', () => nextPage());
    }
}

function setupPdfSearch() {
    const searchInput = $('#pdf-search-input');
    if (searchInput) {
        searchInput.addEventListener('keyup', (e) => handleSearchKeyUp(e));
    }
}
