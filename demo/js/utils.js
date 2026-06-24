const DEMO_NOTICE = '此为静态 demo，该功能需要后端服务支持。\n\n请到 https://github.com/deathxlent/prism_pdf 自行安装体验完整功能。';

function showDemoNotice(featureName) {
    alert(`${featureName || '此功能'}需要后端服务支持。\n\n${DEMO_NOTICE}`);
}

function $(selector) {
    return document.querySelector(selector);
}

function $$(selector) {
    return document.querySelectorAll(selector);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderMarkdownSimple(text) {
    return escapeHtml(text)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
}

function formatDateTime(isoString) {
    if (!isoString) return '-';
    const date = new Date(isoString);
    return date.toLocaleString('zh-CN', {
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
        'processing': '处理中',
        'parsing_layout': '解析布局中',
        'parsing_content': '解析内容中',
        'completed': '已完成',
        'failed': '失败'
    };
    return map[status] || status;
}

function getTypeLabel(type) {
    const map = {
        'Text': 'Text',
        'Title': 'Title',
        'Section-header': 'Section',
        'List-item': 'List',
        'Table': 'Table',
        'Picture': 'Picture',
        'Formula': 'Formula',
        'Caption': 'Caption',
        'Footnote': 'Footnote',
        'Page-header': 'Page Header',
        'Page-footer': 'Page Footer'
    };
    return map[type] || type;
}
