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
        llmModelTypes = data.types || {};
    } catch (e) {
        console.error('Failed to load LLM config types:', e);
    }
}

async function loadLlmConfigs() {
    try {
        const data = await apiGetLlmConfigs();
        llmConfigsData = data.configs || {};
        
        if (llmModelTypes) {
            for (const typeKey of Object.keys(llmModelTypes)) {
                if (!llmConfigsData[typeKey]) {
                    llmConfigsData[typeKey] = [];
                }
            }
        }
    } catch (e) {
        console.error('Failed to load LLM configs:', e);
    }
}

async function loadActiveConfigDisplay() {
    try {
        const data = await apiGetActiveLlmConfig();
        activeLlmConfig = data.active_config || null;
        
        const typeBadge = $('#current-active-type');
        if (typeBadge && activeLlmConfig) {
            const typeInfo = llmModelTypes[activeLlmConfig.type];
            typeBadge.textContent = typeInfo ? typeInfo.name : activeLlmConfig.type;
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
                        ${!isActive ? `<button class="btn btn-success btn-sm" onclick="activateConfig('${config.id}', '${llmCurrentType}')">
                            <i class="fas fa-check"></i> 启用
                        </button>` : ''}
                        <button class="btn btn-outline btn-sm" onclick="editConfig('${config.id}', '${llmCurrentType}')">
                            <i class="fas fa-edit"></i> 编辑
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="deleteConfig('${config.id}', '${llmCurrentType}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
                <div class="config-card-body">
                    <div class="config-info-row">
                        <span class="config-label">模型:</span>
                        <span class="config-value">${escapeHtml(config.model || '-')}</span>
                    </div>
                    ${config.base_url ? `
                    <div class="config-info-row">
                        <span class="config-label">Base URL:</span>
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
    
    $('#llm-config-modal').classList.remove('hidden');
}

function editConfig(configId, typeKey) {
    const configs = llmConfigsData[typeKey] || [];
    const config = configs.find(c => c.id === configId);
    if (!config) return;
    
    llmEditingConfigId = configId;
    llmCurrentType = typeKey;
    
    $('#llm-config-modal-title').textContent = '编辑配置';
    $('#llm-config-name').value = config.display_name || config.name || '';
    $('#llm-config-type').value = typeKey;
    $('#llm-config-base-url').value = config.base_url || '';
    $('#llm-config-api-key').value = config.api_key || '';
    $('#llm-config-model').value = config.model || '';
    $('#llm-config-temperature').value = config.temperature || '0.7';
    $('#llm-config-max-tokens').value = config.max_tokens || '4096';
    $('#llm-config-supports-vision').checked = config.supports_vision || false;
    
    $('#llm-config-modal').classList.remove('hidden');
}

function onLlmConfigTypeChange() {
    const select = $('#llm-config-type');
    const selectedType = select.value;
}

async function saveLlmConfig() {
    const typeKey = $('#llm-config-type').value;
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
    if (!model) {
        alert('请输入模型名称');
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
    $('#llm-config-modal').classList.add('hidden');
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
    if (!confirm('确定要启用这个配置吗？')) return;

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
