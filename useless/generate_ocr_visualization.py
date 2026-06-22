import json
import base64
from pathlib import Path
from html import escape

OCR_RESULT_PATH = r"G:\ws\Prism PDF\useless\ocr_result.json"
IMAGE_PATH = r"G:\ws\Prism PDF\tmp\65adda9dc5874afcb0fd59a78574a942\page_1.jpg"
OUTPUT_PATH = r"G:\ws\Prism PDF\useless\ocr_visualization.html"

TYPE_COLORS = {
    "page_header": "#ef4444",
    "page_footer": "#ef4444",
    "title": "#dc2626",
    "heading": "#ea580c",
    "paragraph": "#2563eb",
    "text": "#1e40af",
    "list": "#7c3aed",
    "image": "#059669",
    "figure": "#059669",
    "table": "#0891b2",
    "equation": "#db2777",
    "code": "#475569",
    "footnote": "#65a30d",
    "citation": "#ca8a04",
}

TYPE_BG_COLORS = {
    "page_header": "#fef2f2",
    "page_footer": "#fef2f2",
    "title": "#fef2f2",
    "heading": "#fff7ed",
    "paragraph": "#eff6ff",
    "text": "#eff6ff",
    "list": "#f5f3ff",
    "image": "#f0fdf4",
    "figure": "#f0fdf4",
    "table": "#ecfeff",
    "equation": "#fdf2f8",
    "code": "#f8fafc",
    "footnote": "#f7fee7",
    "citation": "#fefce8",
}

TYPE_LABELS = {
    "page_header": "页头",
    "page_footer": "页脚",
    "title": "标题",
    "heading": "子标题",
    "paragraph": "段落",
    "text": "文本",
    "list": "列表",
    "image": "图片",
    "figure": "图表",
    "table": "表格",
    "equation": "公式",
    "code": "代码",
    "footnote": "脚注",
    "citation": "引用",
}

TYPE_ICONS = {
    "page_header": "📌",
    "page_footer": "📌",
    "title": "🔴",
    "heading": "🟠",
    "paragraph": "📝",
    "text": "📄",
    "list": "📋",
    "image": "🖼️",
    "figure": "📊",
    "table": "📊",
    "equation": "🔢",
    "code": "💻",
    "footnote": "📑",
    "citation": "📚",
}


def get_image_base64(image_path: str) -> str:
    with open(image_path, "rb") as f:
        data = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/jpeg;base64,{data}"


def render_table(cells: list) -> str:
    html_parts = ['<table class="result-table">']
    
    for row_idx, row in enumerate(cells):
        html_parts.append("  <tr>")
        for cell in row:
            content = escape(cell.get("content", ""))
            row_span = cell.get("row_span", 1)
            col_span = cell.get("col_span", 1)
            is_header = cell.get("is_header", False)
            
            attrs = []
            if row_span > 1:
                attrs.append(f'rowspan="{row_span}"')
            if col_span > 1:
                attrs.append(f'colspan="{col_span}"')
            if is_header:
                attrs.append('class="table-header"')
            if not content and row_span == 1 and col_span == 1:
                attrs.append('class="empty-cell"')
            
            tag = "th" if is_header else "td"
            attr_str = " ".join(attrs)
            if attr_str:
                html_parts.append(f"    <{tag} {attr_str}>{content}</{tag}>")
            else:
                html_parts.append(f"    <{tag}>{content}</{tag}>")
        html_parts.append("  </tr>")
    
    html_parts.append("</table>")
    return "\n".join(html_parts)


def render_element(elem: dict, index: int) -> str:
    etype = elem.get("type", "unknown")
    order = elem.get("order", index + 1)
    content = elem.get("content", "")
    color = TYPE_COLORS.get(etype, "#666")
    bg_color = TYPE_BG_COLORS.get(etype, "#f9fafb")
    label = TYPE_LABELS.get(etype, etype)
    icon = TYPE_ICONS.get(etype, "❓")
    
    html_parts = [
        f'<div class="element-card" data-type="{etype}" data-order="{order}" id="elem-{order}" style="border-left: 4px solid {color}; background: {bg_color};">',
        f'  <div class="element-header">',
        f'    <span class="element-order">#{order}</span>',
        f'    <span class="element-type-badge" style="background: {color};">{icon} {label}</span>',
    ]
    
    if etype in ("title", "heading"):
        level = elem.get("level", "?")
        html_parts.append(f'    <span class="element-level">H{level}</span>')
    
    html_parts.append(f'  </div>')
    html_parts.append(f'  <div class="element-content">')
    
    if etype == "table":
        cells = elem.get("cells", [])
        if cells:
            html_parts.append(f'    <div class="table-caption">{escape(content)}</div>')
            html_parts.append(f'    {render_table(cells)}')
        else:
            html_parts.append(f'    <p>{escape(content)}</p>')
    elif etype in ("image", "figure"):
        desc = elem.get("image_description", content)
        html_parts.append(f'    <div class="image-desc">')
        html_parts.append(f'      <div class="image-icon">{icon}</div>')
        html_parts.append(f'      <div class="image-text">{escape(desc)}</div>')
        html_parts.append(f'    </div>')
    else:
        html_parts.append(f'    <p>{escape(content)}</p>')
    
    html_parts.append(f'  </div>')
    html_parts.append(f'</div>')
    
    return "\n".join(html_parts)


def generate_html(ocr_data: dict, image_base64: str) -> str:
    page_info = ocr_data.get("page_info", {})
    elements = ocr_data.get("elements", [])
    
    type_counts = {}
    for elem in elements:
        etype = elem.get("type", "unknown")
        type_counts[etype] = type_counts.get(etype, 0) + 1
    
    type_filter_html = []
    for etype, count in sorted(type_counts.items()):
        color = TYPE_COLORS.get(etype, "#666")
        label = TYPE_LABELS.get(etype, etype)
        icon = TYPE_ICONS.get(etype, "❓")
        type_filter_html.append(
            f'<button class="filter-btn active" data-type="{etype}" style="border-color: {color};" onclick="filterByType(\'{etype}\')">'
            f'{icon} {label} <span class="filter-count">{count}</span>'
            f'</button>'
        )
    
    elements_html = []
    for i, elem in enumerate(elements):
        elements_html.append(render_element(elem, i))
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OCR 结果可视化 - 第{page_info.get('page_number', '?')}页</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1800px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .header h1 {{
            font-size: 28px;
            color: #1e293b;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        
        .header h1::before {{
            content: '🔍';
            font-size: 32px;
        }}
        
        .page-info {{
            display: flex;
            gap: 24px;
            flex-wrap: wrap;
        }}
        
        .info-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            background: #f8fafc;
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 14px;
            color: #475569;
        }}
        
        .info-item .label {{
            font-weight: 600;
            color: #64748b;
        }}
        
        .info-item .value {{
            color: #1e293b;
            font-weight: 500;
        }}
        
        .filter-bar {{
            background: white;
            border-radius: 16px;
            padding: 16px 24px;
            margin-bottom: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .filter-title {{
            font-size: 14px;
            font-weight: 600;
            color: #475569;
            margin-bottom: 12px;
        }}
        
        .filter-buttons {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}
        
        .filter-btn {{
            background: white;
            border: 2px solid #e2e8f0;
            padding: 8px 16px;
            border-radius: 999px;
            cursor: pointer;
            font-size: 13px;
            font-weight: 500;
            color: #475569;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        
        .filter-btn:hover {{
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .filter-btn.active {{
            background: #f1f5f9;
        }}
        
        .filter-btn.inactive {{
            opacity: 0.4;
        }}
        
        .filter-count {{
            background: rgba(0,0,0,0.1);
            padding: 2px 8px;
            border-radius: 999px;
            font-size: 11px;
            font-weight: 600;
        }}
        
        .filter-actions {{
            margin-top: 12px;
            display: flex;
            gap: 8px;
        }}
        
        .action-btn {{
            background: #f1f5f9;
            border: none;
            padding: 6px 12px;
            border-radius: 6px;
            cursor: pointer;
            font-size: 12px;
            color: #64748b;
            transition: all 0.2s;
        }}
        
        .action-btn:hover {{
            background: #e2e8f0;
            color: #1e293b;
        }}
        
        .main-content {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        
        @media (max-width: 1200px) {{
            .main-content {{
                grid-template-columns: 1fr;
            }}
        }}
        
        .panel {{
            background: white;
            border-radius: 16px;
            padding: 20px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        }}
        
        .panel-title {{
            font-size: 18px;
            font-weight: 600;
            color: #1e293b;
            margin-bottom: 16px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}
        
        .panel-title::before {{
            content: '';
            width: 4px;
            height: 20px;
            background: linear-gradient(135deg, #667eea, #764ba2);
            border-radius: 2px;
        }}
        
        .image-panel {{
            position: sticky;
            top: 20px;
            max-height: calc(100vh - 280px);
            overflow: auto;
        }}
        
        .document-image {{
            width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .results-panel {{
            max-height: calc(100vh - 280px);
            overflow-y: auto;
        }}
        
        .elements-list {{
            display: flex;
            flex-direction: column;
            gap: 16px;
        }}
        
        .element-card {{
            border-radius: 12px;
            padding: 16px;
            transition: all 0.3s;
            cursor: pointer;
        }}
        
        .element-card:hover {{
            transform: translateX(4px);
            box-shadow: 0 8px 24px rgba(0,0,0,0.1);
        }}
        
        .element-card.hidden {{
            display: none;
        }}
        
        .element-header {{
            display: flex;
            align-items: center;
            gap: 12px;
            margin-bottom: 12px;
        }}
        
        .element-order {{
            background: #1e293b;
            color: white;
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            font-weight: 700;
            flex-shrink: 0;
        }}
        
        .element-type-badge {{
            color: white;
            padding: 4px 12px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }}
        
        .element-level {{
            background: #fef3c7;
            color: #92400e;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 700;
        }}
        
        .element-content {{
            color: #334155;
            line-height: 1.7;
            font-size: 14px;
        }}
        
        .element-content p {{
            white-space: pre-wrap;
            word-break: break-word;
        }}
        
        .result-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        
        .result-table th,
        .result-table td {{
            border: 1px solid #e2e8f0;
            padding: 10px 12px;
            text-align: left;
            font-size: 13px;
            vertical-align: top;
        }}
        
        .result-table th.table-header {{
            background: linear-gradient(135deg, #667eea, #764ba2);
            color: white;
            font-weight: 600;
        }}
        
        .result-table tr:hover td {{
            background: #f8fafc;
        }}
        
        .result-table .empty-cell {{
            background: #f8fafc;
        }}
        
        .table-caption {{
            font-size: 13px;
            color: #64748b;
            font-style: italic;
            margin-bottom: 8px;
        }}
        
        .image-desc {{
            display: flex;
            gap: 12px;
            align-items: flex-start;
            background: white;
            padding: 16px;
            border-radius: 8px;
            border: 2px dashed #10b981;
        }}
        
        .image-icon {{
            font-size: 40px;
            flex-shrink: 0;
        }}
        
        .image-text {{
            color: #065f46;
            line-height: 1.7;
        }}
        
        .stats-bar {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid #e2e8f0;
        }}
        
        .stat-item {{
            display: flex;
            flex-direction: column;
            background: #f8fafc;
            padding: 8px 16px;
            border-radius: 8px;
        }}
        
        .stat-label {{
            font-size: 11px;
            color: #94a3b8;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }}
        
        .stat-value {{
            font-size: 20px;
            font-weight: 700;
            color: #1e293b;
        }}
        
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
            padding-top: 16px;
            border-top: 1px solid #e2e8f0;
        }}
        
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 12px;
            color: #64748b;
        }}
        
        .legend-color {{
            width: 12px;
            height: 12px;
            border-radius: 3px;
        }}
        
        .no-results {{
            text-align: center;
            padding: 40px;
            color: #94a3b8;
            font-size: 14px;
        }}
        
        /* 滚动条样式 */
        .image-panel::-webkit-scrollbar,
        .results-panel::-webkit-scrollbar {{
            width: 8px;
        }}
        
        .image-panel::-webkit-scrollbar-track,
        .results-panel::-webkit-scrollbar-track {{
            background: #f1f5f9;
            border-radius: 4px;
        }}
        
        .image-panel::-webkit-scrollbar-thumb,
        .results-panel::-webkit-scrollbar-thumb {{
            background: #cbd5e1;
            border-radius: 4px;
        }}
        
        .image-panel::-webkit-scrollbar-thumb:hover,
        .results-panel::-webkit-scrollbar-thumb:hover {{
            background: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>OCR 结构化识别结果可视化</h1>
            <div class="page-info">
                <div class="info-item">
                    <span class="label">📄 页码:</span>
                    <span class="value">{page_info.get('page_number', '未检测到')}</span>
                </div>
                <div class="info-item">
                    <span class="label">🔄 方向:</span>
                    <span class="value">{page_info.get('orientation', '未检测到')}</span>
                </div>
                <div class="info-item">
                    <span class="label">🌐 语言:</span>
                    <span class="value">{page_info.get('language', '未检测到')}</span>
                </div>
                <div class="info-item">
                    <span class="label">📊 元素总数:</span>
                    <span class="value">{len(elements)}</span>
                </div>
            </div>
            
            <div class="stats-bar">
                <div class="stat-item">
                    <span class="stat-label">标题</span>
                    <span class="stat-value">{type_counts.get('title', 0) + type_counts.get('heading', 0)}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">段落</span>
                    <span class="stat-value">{type_counts.get('paragraph', 0) + type_counts.get('text', 0)}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">表格</span>
                    <span class="stat-value">{type_counts.get('table', 0)}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">列表</span>
                    <span class="stat-value">{type_counts.get('list', 0)}</span>
                </div>
                <div class="stat-item">
                    <span class="stat-label">图片/图表</span>
                    <span class="stat-value">{type_counts.get('image', 0) + type_counts.get('figure', 0)}</span>
                </div>
            </div>
        </div>
        
        <div class="filter-bar">
            <div class="filter-title">按类型筛选</div>
            <div class="filter-buttons">
                {''.join(type_filter_html)}
            </div>
            <div class="filter-actions">
                <button class="action-btn" onclick="showAll()">显示全部</button>
                <button class="action-btn" onclick="hideAll()">隐藏全部</button>
            </div>
            
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background: #ef4444;"></div>
                    <span>页头/页脚</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #ea580c;"></div>
                    <span>标题</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #2563eb;"></div>
                    <span>段落文本</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #0891b2;"></div>
                    <span>表格</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #7c3aed;"></div>
                    <span>列表</span>
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background: #059669;"></div>
                    <span>图片/图表</span>
                </div>
            </div>
        </div>
        
        <div class="main-content">
            <div class="panel image-panel">
                <div class="panel-title">原图</div>
                <img src="{image_base64}" alt="文档原图" class="document-image">
            </div>
            
            <div class="panel results-panel">
                <div class="panel-title">识别结果（按阅读顺序）</div>
                <div class="elements-list" id="elements-list">
                    {''.join(elements_html)}
                </div>
                <div class="no-results hidden" id="no-results">
                    没有符合筛选条件的元素
                </div>
            </div>
        </div>
    </div>
    
    <script>
        const activeFilters = new Set({', '.join([f"'{t}'" for t in type_counts.keys()])});
        
        function filterByType(type) {{
            const btn = document.querySelector(`.filter-btn[data-type="${{type}}"]`);
            
            if (activeFilters.has(type)) {{
                activeFilters.delete(type);
                btn.classList.remove('active');
                btn.classList.add('inactive');
            }} else {{
                activeFilters.add(type);
                btn.classList.add('active');
                btn.classList.remove('inactive');
            }}
            
            applyFilters();
        }}
        
        function applyFilters() {{
            const elements = document.querySelectorAll('.element-card');
            let visibleCount = 0;
            
            elements.forEach(elem => {{
                const type = elem.dataset.type;
                if (activeFilters.has(type)) {{
                    elem.classList.remove('hidden');
                    visibleCount++;
                }} else {{
                    elem.classList.add('hidden');
                }}
            }});
            
            const noResults = document.getElementById('no-results');
            if (visibleCount === 0) {{
                noResults.classList.remove('hidden');
            }} else {{
                noResults.classList.add('hidden');
            }}
        }}
        
        function showAll() {{
            activeFilters.clear();
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                const type = btn.dataset.type;
                activeFilters.add(type);
                btn.classList.add('active');
                btn.classList.remove('inactive');
            }});
            applyFilters();
        }}
        
        function hideAll() {{
            activeFilters.clear();
            document.querySelectorAll('.filter-btn').forEach(btn => {{
                btn.classList.remove('active');
                btn.classList.add('inactive');
            }});
            applyFilters();
        }}
        
        // 点击元素滚动到对应位置（虽然没有bbox，但可以高亮）
        document.querySelectorAll('.element-card').forEach(card => {{
            card.addEventListener('click', function() {{
                // 移除其他高亮
                document.querySelectorAll('.element-card').forEach(c => {{
                    c.style.boxShadow = '';
                }});
                // 高亮当前
                this.style.boxShadow = '0 0 0 3px rgba(102, 126, 234, 0.5), 0 8px 24px rgba(0,0,0,0.15)';
                // 滚动到视图
                this.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }});
        }});
    </script>
</body>
</html>
"""
    
    return html


def main():
    print("=" * 70)
    print("📊 OCR 结果可视化 HTML 生成器")
    print("=" * 70)
    
    ocr_result_file = Path(OCR_RESULT_PATH)
    if not ocr_result_file.exists():
        print(f"❌ OCR 结果文件不存在: {OCR_RESULT_PATH}")
        return 1
    
    image_file = Path(IMAGE_PATH)
    if not image_file.exists():
        print(f"❌ 图片文件不存在: {IMAGE_PATH}")
        return 1
    
    print(f"\n📖 读取 OCR 结果: {ocr_result_file.name}")
    with open(ocr_result_file, "r", encoding="utf-8") as f:
        ocr_data = json.load(f)
    
    print(f"🖼️  编码图片: {image_file.name} ({image_file.stat().st_size/1024:.1f} KB)")
    image_base64 = get_image_base64(IMAGE_PATH)
    
    print("🎨 生成 HTML...")
    html_content = generate_html(ocr_data, image_base64)
    
    output_file = Path(OUTPUT_PATH)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"\n✅ 可视化 HTML 已生成: {output_file}")
    print(f"📏 文件大小: {len(html_content)/1024:.1f} KB")
    print(f"📊 识别元素: {len(ocr_data.get('elements', []))} 个")
    
    print(f"\n👉 在浏览器中打开查看: {output_file}")
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
