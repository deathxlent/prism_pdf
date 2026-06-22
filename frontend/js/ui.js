function toggleTopMenu() {
    const dropdown = $('#top-menu-dropdown');
    if (dropdown) {
        dropdown.classList.toggle('show');
    }
}

function closeTopMenu() {
    const dropdown = $('#top-menu-dropdown');
    if (dropdown) {
        dropdown.classList.remove('show');
    }
}

document.addEventListener('click', (e) => {
    const btn = $('#top-menu-btn');
    const dropdown = $('#top-menu-dropdown');
    if (btn && dropdown && !btn.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.classList.remove('show');
    }
});

async function loadResourceStatus() {
    try {
        const res = await fetch(API + '/api/model-status');
        const data = await res.json();
        
        if (data.gpu) {
            const gpuText = $('#gpu-status-text');
            const gpuBar = $('#gpu-vram-bar');
            const gpuFill = gpuBar ? gpuBar.querySelector('.gpu-fill') : null;
            
            if (gpuText) {
                if (data.gpu.cuda_available) {
                    const used = (data.gpu.used_vram_mb || 0) / 1024;
                    const total = (data.gpu.total_vram_mb || 0) / 1024;
                    gpuText.textContent = `${used.toFixed(1)} / ${total.toFixed(1)} GB`;
                    
                    if (gpuBar && total > 0) {
                        gpuBar.classList.remove('hidden');
                        const pct = (used / total) * 100;
                        if (gpuFill) gpuFill.style.width = pct + '%';
                    }
                } else {
                    gpuText.textContent = '不可用';
                }
            }
        }
        
        if (data.yolo) {
            const yoloText = $('#yolo-status-text');
            const yoloMem = $('#yolo-mem-text');
            
            if (yoloText) {
                yoloText.textContent = data.yolo.loaded ? '已加载' : '未加载';
                yoloText.className = 'resource-value ' + (data.yolo.loaded ? 'status-ready' : 'status-idle');
            }
            if (yoloMem && data.yolo.memory_mb) {
                yoloMem.textContent = `占用 ${data.yolo.memory_mb.toFixed(0)} MB`;
            }
        }
        
        const surya = data.surya_order || data.surya;
        if (surya) {
            const suryaText = $('#surya-status-text');
            const suryaMem = $('#surya-mem-text');
            
            if (suryaText) {
                suryaText.textContent = surya.loaded ? '已加载' : '未加载';
                suryaText.className = 'resource-value ' + (surya.loaded ? 'status-ready' : 'status-idle');
            }
            if (suryaMem && surya.memory_mb) {
                suryaMem.textContent = `占用 ${surya.memory_mb.toFixed(0)} MB`;
            }
        }
    } catch (e) {
        console.error('Failed to load resource status:', e);
    }
}
