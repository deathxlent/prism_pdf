function showTranslatePageLanguageSelect() {
    languageSelectCallback = (lang) => {
        translatePage(lang);
    };
    $('#language-select-popup').classList.remove('hidden');
}

function showElementTranslateLanguageSelect(elementId) {
    languageSelectCallback = (lang) => {
        translateElement(elementId, lang);
    };
    $('#language-select-popup').classList.remove('hidden');
}

function showDocTranslateLanguageSelect(docId) {
    languageSelectCallback = (lang) => {
        translateDocument(docId, lang);
    };
    $('#language-select-popup').classList.remove('hidden');
}

function confirmLanguageSelect(lang) {
    if (languageSelectCallback) {
        languageSelectCallback(lang);
    }
    cancelLanguageSelect();
}

function cancelLanguageSelect() {
    $('#language-select-popup').classList.add('hidden');
    languageSelectCallback = null;
}

async function translateElement(elementId, targetLanguage) {
    showLoading('正在翻译中...');
    try {
        const result = await fetchWithTimeout(
            API + '/api/elements/' + elementId + '/translate',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_language: targetLanguage })
            },
            LLM_FETCH_TIMEOUT_MS
        );

        if (!result.ok) {
            const err = await result.json();
            throw new Error(err.detail || '翻译失败');
        }

        const data = await result.json();
        const idx = currentElements.findIndex(e => e.id === elementId);
        if (idx !== -1) {
            currentElements[idx].translated_content = data.translated_content;
        }
        renderElements();
        hideLoading();
        alert('翻译完成');
    } catch (e) {
        hideLoading();
        if (e.message === 'timeout') {
            alert('翻译请求超时，请稍后重试');
        } else {
            alert('翻译失败: ' + e.message);
        }
    }
}

async function translatePage(targetLanguage) {
    if (!currentPageData) return;
    
    showLoading('正在翻译整页内容，请稍候...');
    try {
        const result = await fetchWithTimeout(
            API + '/api/pages/' + currentPageData.id + '/translate',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_language: targetLanguage })
            },
            LLM_FETCH_TIMEOUT_MS
        );

        if (!result.ok) {
            const err = await result.json();
            throw new Error(err.detail || '翻译失败');
        }

        const data = await result.json();
        if (data.results) {
            for (const item of data.results) {
                const idx = currentElements.findIndex(e => e.id === item.element_id);
                if (idx !== -1) {
                    currentElements[idx].translated_content = item.translated_content;
                }
            }
        }
        renderElements();
        hideLoading();
        alert('整页翻译完成');
    } catch (e) {
        hideLoading();
        if (e.message === 'timeout') {
            alert('翻译请求超时，请稍后重试');
        } else {
            alert('翻译失败: ' + e.message);
        }
    }
}

async function translateDocument(docId, targetLanguage) {
    if (!confirm('确定要翻译整个文档吗？这可能需要较长时间。')) return;
    
    showLoading('正在翻译整个文档，这可能需要几分钟...');
    try {
        const result = await fetchWithTimeout(
            API + '/api/documents/' + docId + '/translate',
            {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ target_language: targetLanguage })
            },
            LLM_FETCH_TIMEOUT_MS
        );

        if (!result.ok) {
            const err = await result.json();
            throw new Error(err.detail || '翻译失败');
        }

        hideLoading();
        alert('文档翻译已完成');
        if (currentDocId === docId) {
            loadPage(currentPageIndex);
            updateExportDropdownVisibility();
        }
    } catch (e) {
        hideLoading();
        if (e.message === 'timeout') {
            alert('翻译请求超时，请稍后重试');
        } else {
            alert('翻译失败: ' + e.message);
        }
    }
}
