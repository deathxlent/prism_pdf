let currentDocId = null;
let currentPageIndex = 0;
let currentPageData = null;
let currentPages = [];
let currentElements = [];
let currentDocument = null;
let editingElementId = null;
let isEditOrderMode = false;
let originalOrder = [];
let activeElementId = null;
let showAnnotations = false;
let searchResults = [];
let currentSearchIndex = -1;
let isAddElementMode = false;
let selectionOverlay = null;
let selectionRect = null;
let selectionStart = null;
let selectedBbox = null;
let pendingNewElement = null;
let ignoreNextModalCloseClick = false;

const STORAGE_KEY = 'prism_pdf_demo_data';

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const data = JSON.parse(saved);
            if (data.elements) {
                return data;
            }
        }
    } catch (e) {
        console.error('Failed to load state:', e);
    }
    return null;
}

function saveState() {
    try {
        const data = {
            elements: {}
        };
        
        currentPages.forEach(page => {
            const pageElements = currentElements.filter(e => e.page_id === page.id);
            data.elements[page.id] = pageElements;
        });
        
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
    } catch (e) {
        console.error('Failed to save state:', e);
    }
}

function loadElementsForPage(pageId) {
    const state = loadState();
    if (state && state.elements && state.elements[pageId]) {
        return state.elements[pageId];
    }
    
    const page = currentPages.find(p => p.id === pageId);
    if (page && page.elements) {
        return page.elements;
    }
    
    return [];
}

function saveElementsForPage(pageId, elements) {
    const state = loadState() || { elements: {} };
    state.elements[pageId] = elements;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
