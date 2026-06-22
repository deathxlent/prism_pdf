const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const API = '';
const LLM_FETCH_TIMEOUT_MS = 60 * 60 * 1000;

async function fetchWithTimeout(url, options = {}, timeoutMs = 30000) {
    const controller = new AbortController();
    const id = setTimeout(() => controller.abort(), timeoutMs);
    try {
        const res = await fetch(url, { ...options, signal: controller.signal });
        clearTimeout(id);
        return res;
    } catch (e) {
        clearTimeout(id);
        if (e.name === 'AbortError') {
            throw new Error('timeout');
        }
        throw e;
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function formatDateTime(isoStr) {
    if (!isoStr) return '-';
    const d = new Date(isoStr);
    return d.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function getStatusText(status) {
    const map = {
        'uploaded': '已上传',
        'validated': '已验证',
        'pages_ready': '待解析',
        'processing': '处理中',
        'parsing_layout': '布局解析中',
        'parsing_content': '内容解析中',
        'completed': '已完成',
        'failed': '失败'
    };
    return map[status] || status;
}

function getResultText(status) {
    if (status === 'completed') return '<span class="parse-result success"><i class="fas fa-check-circle"></i> 解析成功</span>';
    if (status === 'failed') return '<span class="parse-result failed"><i class="fas fa-times-circle"></i> 解析失败</span>';
    if (status === 'processing' || status.startsWith('parsing')) return '<span class="parse-result processing"><i class="fas fa-spinner fa-spin"></i> 解析中</span>';
    return '<span class="parse-result"><i class="fas fa-clock"></i> 待解析</span>';
}

function renderMarkdownSimple(text) {
    if (!text) return '';
    
    let html = escapeHtml(text);
    
    html = html.replace(/^### (.*$)/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.*$)/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.*$)/gm, '<h1>$1</h1>');
    
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
    html = html.replace(/`(.*?)`/g, '<code>$1</code>');
    
    html = html.replace(/^\|(.+)\|$/gm, (match) => {
        const cells = match.split('|').filter(c => c.trim());
        if (cells.every(c => /^[-:]+$/.test(c.trim()))) return '';
        return '<tr>' + cells.map(c => `<td>${c.trim()}</td>`).join('') + '</tr>';
    });
    
    if (html.includes('<tr>')) {
        html = '<table>' + html.replace(/(<tr>.*?<\/tr>)/gs, '$1') + '</table>';
    }
    
    html = html.replace(/^- (.*$)/gm, '<li>$1</li>');
    html = html.replace(/^(\d+)\. (.*$)/gm, '<li>$2</li>');
    
    html = html.replace(/(<li>.*?<\/li>)(\n<li>)/gs, '$1$2');
    html = html.replace(/(<li>.*?<\/li>)+/g, '<ul>$&</ul>');
    
    html = html.replace(/\n\n/g, '</p><p>');
    html = '<p>' + html + '</p>';
    
    html = html.replace(/<p><h(\d)>/g, '<h$1>');
    html = html.replace(/<\/h(\d)><\/p>/g, '</h$1>');
    html = html.replace(/<p><table>/g, '<table>');
    html = html.replace(/<\/table><\/p>/g, '</table>');
    html = html.replace(/<p><ul>/g, '<ul>');
    html = html.replace(/<\/ul><\/p>/g, '</ul>');
    html = html.replace(/<p><\/p>/g, '');
    
    return html;
}

function highlightKeyword(text, keyword) {
    if (!keyword || !text) return escapeHtml(text || '');
    
    const regex = new RegExp(`(${escapeRegExp(keyword)})`, 'gi');
    return escapeHtml(text).replace(regex, '<mark>$1</mark>');
}

function togglePasswordVisibility(inputId, btn) {
    const input = document.getElementById(inputId);
    const icon = btn.querySelector('i');
    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}
