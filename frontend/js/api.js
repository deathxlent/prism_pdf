async function apiGetDocuments() {
    const res = await fetch(API + '/api/documents');
    return await res.json();
}

async function apiGetStatus(docId) {
    const res = await fetch(API + '/api/status/' + docId);
    return await res.json();
}

async function apiGetResults(docId) {
    const res = await fetch(API + '/api/results/' + docId);
    return await res.json();
}

async function apiGetProgress(docId) {
    const res = await fetch(API + '/api/progress/' + docId);
    return await res.json();
}

async function apiUploadFile(file, onProgress) {
    const formData = new FormData();
    formData.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', API + '/api/upload');

    if (onProgress) {
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                onProgress(pct);
            }
        };
    }

    return new Promise((resolve, reject) => {
        xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
                resolve(JSON.parse(xhr.responseText));
            } else {
                try {
                    reject(JSON.parse(xhr.responseText));
                } catch {
                    reject({ detail: xhr.statusText });
                }
            }
        };
        xhr.onerror = () => reject({ detail: 'Network error' });
        xhr.send(formData);
    });
}

async function apiStartParsing(docId) {
    const res = await fetch(API + '/api/parse/' + docId, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to start parsing');
    return data;
}

async function apiReparseDocument(docId) {
    const res = await fetch(API + '/api/reparse/' + docId, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Failed to start reparsing');
    return data;
}

async function apiDeleteDocument(docId) {
    await fetch(API + '/api/documents/' + docId, { method: 'DELETE' });
}

async function apiGetPageElements(pageId) {
    const res = await fetch(API + '/api/pages/' + pageId + '/elements');
    return await res.json();
}

async function apiUpdateElement(elementId, data) {
    const res = await fetch(API + '/api/elements/' + elementId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to update element');
    return await res.json();
}

async function apiDeleteElement(elementId) {
    const res = await fetch(API + '/api/elements/' + elementId, {
        method: 'DELETE'
    });
    if (!res.ok) throw new Error('Failed to delete element');
}

async function apiCreateElement(pageId, data) {
    const res = await fetch(API + '/api/pages/' + pageId + '/elements', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) throw new Error('Failed to create element');
    return await res.json();
}

async function apiReorderElements(pageId, elementOrder) {
    const res = await fetch(API + '/api/pages/' + pageId + '/elements/reorder', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ element_order: elementOrder })
    });
    if (!res.ok) throw new Error('Failed to reorder elements');
}

async function apiReorderPage(pageId) {
    const res = await fetch(`${API}/api/pages/${pageId}/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '重排序失败');
    }
    return await res.json();
}

async function apiGetRawLayout(pageId) {
    const res = await fetch(API + '/api/pages/' + pageId + '/layout-raw');
    if (!res.ok) throw new Error('Failed to get raw layout data');
    return await res.json();
}

async function apiSearchDocument(docId, keyword) {
    const res = await fetch(`${API}/api/documents/${docId}/search?q=${encodeURIComponent(keyword)}`);
    return await res.json();
}

async function apiDescribeImage(elementId) {
    const res = await fetch(API + '/api/elements/' + elementId + '/describe-image', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '生成图片描述失败');
    }
    return await res.json();
}

async function apiTranslateElement(elementId, targetLanguage) {
    const res = await fetch(API + '/api/elements/' + elementId + '/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_language: targetLanguage })
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '翻译失败');
    }
    return await res.json();
}

async function apiTranslatePage(pageId, targetLanguage) {
    const res = await fetch(API + '/api/pages/' + pageId + '/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_language: targetLanguage })
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '翻译失败');
    }
    return await res.json();
}

async function apiTranslateDocument(docId, targetLanguage) {
    const res = await fetch(API + '/api/documents/' + docId + '/translate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_language: targetLanguage })
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '翻译失败');
    }
    return await res.json();
}

async function apiGetLlmConfigTypes() {
    const res = await fetch(API + '/api/llm-config/types');
    return await res.json();
}

async function apiGetLlmConfigs() {
    const res = await fetch(API + '/api/llm-config');
    return await res.json();
}

async function apiGetActiveLlmConfig() {
    const res = await fetch(API + '/api/llm-config/active');
    return await res.json();
}

async function apiSetActiveLlmType(typeKey) {
    const res = await fetch(`${API}/api/llm-config/active-type/${encodeURIComponent(typeKey)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) throw new Error('Failed to set active type');
    return await res.json();
}

async function apiCreateLlmConfig(typeKey, data) {
    const res = await fetch(`${API}/api/llm-config/${encodeURIComponent(typeKey)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '创建失败');
    }
    return await res.json();
}

async function apiUpdateLlmConfig(typeKey, configId, data) {
    const res = await fetch(`${API}/api/llm-config/${encodeURIComponent(typeKey)}/${encodeURIComponent(configId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '保存失败');
    }
    return await res.json();
}

async function apiDeleteLlmConfig(typeKey, configId) {
    const res = await fetch(`${API}/api/llm-config/${encodeURIComponent(typeKey)}/${encodeURIComponent(configId)}`, {
        method: 'DELETE'
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '删除失败');
    }
}

async function apiActivateLlmConfig(typeKey, configId) {
    const res = await fetch(`${API}/api/llm-config/${encodeURIComponent(typeKey)}/${encodeURIComponent(configId)}/activate`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' }
    });
    if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || '激活失败');
    }
    return await res.json();
}

async function apiGetModelStatus() {
    const res = await fetch(API + '/api/model-status');
    return await res.json();
}

async function getLlmActiveConfig() {
    try {
        const res = await fetch(API + '/api/llm-config/active');
        const data = await res.json();
        return data && data.active_config ? data.active_config : null;
    } catch (e) {
        return null;
    }
}

function updateLlmButtons() {
    const hasLlm = !!activeLlmConfig;

    const translateBtn = $('#translate-page-btn');
    if (translateBtn) {
        if (hasLlm) {
            translateBtn.classList.remove('hidden');
        } else {
            translateBtn.classList.add('hidden');
        }
    }

    const translateDocBtn = $('#translate-doc-btn');
    if (translateDocBtn) {
        if (hasLlm) {
            translateDocBtn.classList.remove('hidden');
        } else {
            translateDocBtn.classList.add('hidden');
        }
    }
}
