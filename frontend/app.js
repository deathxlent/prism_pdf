document.addEventListener('DOMContentLoaded', async () => {
    setupRouter();
    setupDropZone();
    setupViewToggle();
    setupSearch();
    initExportDropdown();
    
    await initLlmConfig();
    await loadDocuments();

    window.addEventListener('hashchange', handleRoute);
    handleRoute();

    window.addEventListener('resize', () => {
        if (currentPageData) {
            const canvas = $('#pdf-canvas');
            clearAnnotations();
            renderAnnotations(currentElements, canvas.width, canvas.height);
        }
    });
});

function setupRouter() {
    if (!window.location.hash) {
        window.location.hash = '#/home';
    }
}

function handleRoute() {
    const hash = window.location.hash.slice(2) || 'home';
    const parts = hash.split('/');
    const route = parts[0];
    const param = parts[1];

    $$('.page').forEach(p => p.classList.remove('active'));

    if (route === 'detail' && param) {
        $('#page-detail').classList.add('active');
        loadDocumentDetail(parseInt(param));
    } else if (route === 'llm-config') {
        $('#page-llm-config').classList.add('active');
        renderLlmTabs();
        loadResourceStatus();
    } else {
        $('#page-home').classList.add('active');
        loadDocuments();
    }

    closeTopMenu();
}

function navigateTo(path) {
    window.location.hash = '#/' + path;
}

function showSettings() {
    navigateTo('llm-config');
}

function closeAllModals() {
    $$('.modal').forEach(m => m.classList.add('hidden'));
    $$('.language-select-popup').forEach(p => p.classList.add('hidden'));
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeAllModals();
        closeSearchResults();
        clearSearchResults();
    }
    
    const detailPage = $('#page-detail');
    if (detailPage && detailPage.classList.contains('active')) {
        if (e.key === 'ArrowLeft') {
            prevPage();
        } else if (e.key === 'ArrowRight') {
            nextPage();
        } else if (e.key === '+' || e.key === '=') {
            zoomIn();
        } else if (e.key === '-') {
            zoomOut();
        }
    }
});

let ignoreNextModalCloseClick = false;

document.addEventListener('click', (e) => {
    if (ignoreNextModalCloseClick) {
        ignoreNextModalCloseClick = false;
        return;
    }
    
    const modals = $$('.modal');
    modals.forEach(modal => {
        if (!modal.classList.contains('hidden')) {
            const modalContent = modal.querySelector('.modal-content');
            if (modalContent && !modalContent.contains(e.target)) {
                const isModalTrigger = e.target.closest('[onclick*="openModal"], [onclick*="openCreateConfigModal"], [onclick*="showExportOptions"], [onclick*="openTranslatePopup"], [onclick*="openAddElementModal"]');
                if (!isModalTrigger) {
                    modal.classList.add('hidden');
                }
            }
        }
    });
});
