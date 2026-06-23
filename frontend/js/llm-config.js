async function initLlmConfig() {
    await Promise.all([
        loadLlmConfigTypes(),
        loadLlmConfigs(),
        loadActiveConfigDisplay()
    ]);
    renderLlmTabs();
    loadResourceStatus();
    
    llmStatusRefreshTimer = setInterval(() => {
        loadResourceStatus();
    }, 30000);
}

async function loadLlmConfigTypes() {
    try {
        const data = await apiGetLlmConfigTypes();
        llmModelTypes = data.model_types || data.types || {};
    } catch (e) {
        console.error('Failed to load LLM config types:', e);
    }
}

async function loadLlmConfigs() {
    try {
        const data = await apiGetLlmConfigs();
        llmConfigsData = data.configs || {};
        const types = data.model_types || data.types || llmModelTypes;
        llmModelTypes = types;
        
        for (const typeKey of Object.keys(llmModelTypes)) {
            if (!llmConfigsData[typeKey]) {
                llmConfigsData[typeKey] = [];
            }
        }
        
        const activeType = data.active_type;
        if (activeType && llmModelTypes[activeType]) {
            llmCurrentType = activeType;
        }
    } catch (e) {
        console.error('Failed to load LLM configs:', e);
    }
}

async function loadActiveConfigDisplay() {
    try {
        const data = await apiGetActiveLlmConfig();
        activeLlmConfig = data.active_config || null;
        
        const activeType = data.active_type;
        if (activeType && llmModelTypes[activeType]) {
            llmCurrentType = activeType;
        }
        
        const typeBadge = $('#current-active-type');
        if (typeBadge && activeLlmConfig) {
            const typeInfo = llmModelTypes[activeType || llmCurrentType];
            typeBadge.textContent = typeInfo ? typeInfo.name : (activeType || llmCurrentType);
        }
    } catch (e) {
        console.error('Failed to load active config:', e);
    }
}

function renderLlmTabs() {
    const tabsContainer = $('#llm-tabs');
    if (!tabsContainer) return;

    const typeKeys = Object.keys(llmModelTypes);
    if (typeKeys.length === 0) return;

    if (!llmModelTypes[llmCurrentType]) {
        llmCurrentType = typeKeys[0];
    }

    tabsContainer.innerHTML = typeKeys.map(key => {
        const typeInfo = llmModelTypes[key];
        const isActive = key === llmCurrentType;
        const configCount = (llmConfigsData[key] || []).length;

        return `
            <div class="llm-tab ${isActive ? 'active' : ''}" 
                 onclick="switchLlmTab('${key}')"
                 data-type="${key}">
                <i class="${typeInfo.icon_class || 'fas fa-cog'}"></i>
                <span>${typeInfo.name || key}</span>
                <span class="llm-tab-count">${configCount}</span>
            </div>
        `;
    }).join('');

    renderLlmConfigList();
}

function switchLlmTab(typeKey) {
    llmCurrentType = typeKey;
    renderLlmTabs();
}

function renderLlmConfigList() {
    const listContainer = $('#llm-config-list');
    const typeInfoEl = $('#tab-type-info');
    
    if (!listContainer) return;

    const typeInfo = llmModelTypes[llmCurrentType];
    const configs = llmConfigsData[llmCurrentType] || [];

    if (typeInfoEl && typeInfo) {
        typeInfoEl.textContent = typeInfo.description || '';
    }

    if (configs.length === 0) {
        listContainer.innerHTML = '<p class="empty-msg">暂无配置，点击上方按钮新建</p>';
        return;
    }

    listContainer.innerHTML = configs.map(config => {
        const isActive = config.is_active;
        return `
            <div class="config-card ${isActive ? 'active' : ''}">
                <div class="config-card-header">
                    <div class="config-name">
                        <i class="fas fa-server"></i>
                        <span>${escapeHtml(config.display_name || config.name || config.model || '未命名')}</span>
                        ${isActive ? '<span class="active-badge">当前使用</span>' : ''}
                    </div>
                    <div class="config-actions">
                        <button class="btn btn-success btn-sm" onclick="activateConfig('${config.id}', '${llmCurrentType}')" ${isActive ? 'disabled' : ''}>
                            <i class="fas fa-check"></i> ${isActive ? '已启用' : '启用'}
                        </button>
                        <button class="btn btn-outline btn-sm" onclick="editConfig('${config.id}', '${llmCurrentType}')">
                            <i class="fas fa-edit"></i> 编辑
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="deleteConfig('${config.id}', '${llmCurrentType}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
                <div class="config-card-body">
                    ${config.model ? `
                    <div class="config-info-row">
                        <span class="config-label">模型:</span>
                        <span class="config-value">${escapeHtml(config.model)}</span>
                    </div>` : ''}
                    ${config.base_url ? `
                    <div class="config-info-row">
                        <span class="config-label">服务地址:</span>
                        <span class="config-value">${escapeHtml(config.base_url)}</span>
                    </div>` : ''}
                    ${config.supports_vision ? `
                    <div class="config-info-row">
                        <span class="config-label">功能:</span>
                        <span class="config-value"><i class="fas fa-eye"></i> 支持图像理解</span>
                    </div>` : ''}
                </div>
            </div>
        `;
    }).join('');
}

function openCreateConfigModal() {
    llmEditingConfigId = null;
    
    $('#llm-config-modal-title').textContent = '新建配置';
    $('#llm-config-name').value = '';
    $('#llm-config-base-url').value = '';
    $('#llm-config-api-key').value = '';
    $('#llm-config-model').value = '';
    $('#llm-config-temperature').value = '0.7';
    $('#llm-config-max-tokens').value = '4096';
    $('#llm-config-supports-vision').checked = false;
    
    const typeSelect = $('#llm-config-type');
    const typeKeys = Object.keys(llmModelTypes);
    typeSelect.innerHTML = typeKeys.map(key => {
        const typeInfo = llmModelTypes[key];
        return `<option value="${key}">${typeInfo.name || key}</option>`;
    }).join('');
    typeSelect.value = llmCurrentType;
    typeSelect.disabled = false;
    
    updateConfigFormFields(llmCurrentType);
    $('#llm-config-modal').classList.remove('hidden');
}

function editConfig(configId, typeKey) {
    const configs = llmConfigsData[typeKey] || [];
    const config = configs.find(c => c.id === configId);
    if (!config) {
        alert('配置未找到，请刷新页面重试');
        return;
    }
    
    llmEditingConfigId = configId;
    llmCurrentType = typeKey;
    
    $('#llm-config-modal-title').textContent = '编辑配置';
    $('#llm-config-name').value = config.display_name || config.name || '';
    const typeSelect = $('#llm-config-type');
    if (typeSelect) {
        typeSelect.value = typeKey;
        typeSelect.disabled = true;
    }
    $('#llm-config-base-url').value = config.base_url || '';
    $('#llm-config-api-key').value = config.api_key || '';
    $('#llm-config-model').value = config.model || '';
    $('#llm-config-temperature').value = config.temperature || '0.7';
    $('#llm-config-max-tokens').value = config.max_tokens || '4096';
    $('#llm-config-supports-vision').checked = config.supports_vision || false;
    
    updateConfigFormFields(typeKey);
    
    const modal = $('#llm-config-modal');
    if (modal) {
        modal.classList.remove('hidden');
        document.body.appendChild(modal);
        
        // 使用 setProperty 来强制设置样式，使用 !important 确保不被CSS覆盖
        modal.style.setProperty('z-index', '999999', 'important');
        modal.style.setProperty('position', 'fixed', 'important');
        modal.style.setProperty('top', '0', 'important');
        modal.style.setProperty('left', '0', 'important');
        modal.style.setProperty('width', '100vw', 'important');
        modal.style.setProperty('height', '100vh', 'important');
        modal.style.setProperty('display', 'flex', 'important');
        modal.style.setProperty('align-items', 'center', 'important');
        modal.style.setProperty('justify-content', 'center', 'important');
    }
}

function updateConfigFormFields(typeKey) {
    const typeInfo = llmModelTypes[typeKey] || {};
    const fields = typeInfo.fields || [];
    
    const fieldMap = {
        'api_key': '#llm-config-api-key-group',
        'base_url': '#llm-config-base-url-group',
        'model': '#llm-config-model-group',
    };
    
    for (const [field, selector] of Object.entries(fieldMap)) {
        const el = $(selector);
        if (el) {
            el.style.display = fields.includes(field) ? '' : 'none';
        }
    }
    
    const tempRow = $('#llm-config-temperature-group');
    if (tempRow) {
        tempRow.style.display = (fields.includes('temperature') || fields.includes('max_tokens')) ? '' : 'none';
    }
    
    const visionGroup = $('#llm-config-supports-vision-group');
    if (visionGroup) {
        visionGroup.style.display = typeInfo.supports_vision !== undefined ? '' : 'none';
    }
}

function onLlmConfigTypeChange() {
    const select = $('#llm-config-type');
    const selectedType = select.value;
    updateConfigFormFields(selectedType);
    
    const typeInfo = llmModelTypes[selectedType] || {};
    const defaults = typeInfo.defaults || {};
    
    const baseUrlEl = $('#llm-config-base-url');
    if (baseUrlEl) {
        if (selectedType === 'paddlevl') {
            baseUrlEl.placeholder = 'http://localhost:8080/v1 (PaddleVL 图片描述服务地址)';
        } else {
            baseUrlEl.placeholder = 'https://api.example.com/v1';
        }
    }
    
    if (defaults.base_url && !baseUrlEl.value.trim()) {
        baseUrlEl.value = defaults.base_url;
    }
    if (defaults.model && !$('#llm-config-model').value.trim()) {
        $('#llm-config-model').value = defaults.model;
    }
    if (defaults.api_key && !$('#llm-config-api-key').value.trim()) {
        $('#llm-config-api-key').value = defaults.api_key;
    }
    if (defaults.temperature) {
        $('#llm-config-temperature').value = defaults.temperature;
    }
    if (defaults.max_tokens) {
        $('#llm-config-max-tokens').value = defaults.max_tokens;
    }
}

async function saveLlmConfig() {
    let typeKey = $('#llm-config-type').value;
    
    // 如果是编辑模式，使用 llmCurrentType
    if (llmEditingConfigId && llmCurrentType) {
        typeKey = llmCurrentType;
    }
    
    const name = $('#llm-config-name').value.trim();
    const baseUrl = $('#llm-config-base-url').value.trim();
    const apiKey = $('#llm-config-api-key').value.trim();
    const model = $('#llm-config-model').value.trim();
    const temperature = parseFloat($('#llm-config-temperature').value) || 0.7;
    const maxTokens = parseInt($('#llm-config-max-tokens').value) || 4096;
    const supportsVision = $('#llm-config-supports-vision').checked;

    if (!name) {
        alert('请输入配置名称');
        return;
    }

    const typeInfo = llmModelTypes[typeKey] || {};
    const fields = typeInfo.fields || [];

    if (fields.includes('model') && !model) {
        alert('请输入模型名称');
        return;
    }

    if (typeKey === 'paddlevl' && !baseUrl) {
        alert('请输入 PaddleVL 服务地址');
        return;
    }

    const data = {
        display_name: name,
        base_url: baseUrl,
        api_key: apiKey,
        model: model,
        temperature: temperature,
        max_tokens: maxTokens,
        supports_vision: supportsVision
    };

    try {
        if (llmEditingConfigId) {
            await apiUpdateLlmConfig(typeKey, llmEditingConfigId, data);
        } else {
            await apiCreateLlmConfig(typeKey, data);
        }

        await loadLlmConfigs();
        await loadActiveConfigDisplay();
        renderLlmTabs();
        updateLlmButtons();
        
        closeLlmConfigModal();
        alert('保存成功');
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

function closeLlmConfigModal() {
    const modal = $('#llm-config-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.style.setProperty('display', 'none', 'important');
    }
    const typeSelect = $('#llm-config-type');
    if (typeSelect) typeSelect.disabled = false;
    llmEditingConfigId = null;
}

async function deleteConfig(configId, typeKey) {
    if (!confirm('确定要删除这个配置吗？')) return;

    try {
        await apiDeleteLlmConfig(typeKey, configId);
        await loadLlmConfigs();
        renderLlmTabs();
    } catch (e) {
        alert('删除失败: ' + e.message);
    }
}

async function activateConfig(configId, typeKey) {
    try {
        await apiActivateLlmConfig(typeKey, configId);
        await loadLlmConfigs();
        await loadActiveConfigDisplay();
        renderLlmTabs();
        updateLlmButtons();
    } catch (e) {
        alert('激活失败: ' + e.message);
    }
}
