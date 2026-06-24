# Prism PDF - 静态演示

> **此为静态演示，所有数据均为预加载，交互效果为模拟。**
> 
> 🔗 **想要完整体验？** 请访问 [Prism PDF GitHub 仓库](https://github.com/deathxlent/prism_pdf) 自行安装，体验真实的 PDF 解析、翻译和 AI 功能！

## 快速开始

### Windows
双击 `start.bat`

### macOS / Linux
```bash
chmod +x start.sh
./start.sh
```

### 手动启动
在浏览器中直接打开 `index.html`，或使用任意本地 HTTP 服务器：
```bash
# Python 3
python -m http.server 8080

# Node.js (npx)
npx serve .
```

然后访问：`http://localhost:8080`

## 演示功能

- 文档列表管理
- PDF 页面预览（静态图片）
- 元素浏览与编辑（数据保存到 localStorage）
- 导出功能（预生成文件）
- 拖拽元素排序
- 解析内容搜索

## 功能限制

以下功能会弹出友好提示：
- 上传 PDF
- 重新解析文档
- 翻译功能（文档/页面/元素级别）
- 删除操作
- 自动排序（Surya 模型）
- 图片描述生成
- 添加新元素（需要 PDF 画布交互）

## 获取完整版本

本演示仅展示界面效果。如需完整的 Prism PDF 功能，包括：
- 真实的 PDF 解析与布局检测
- AI 驱动的翻译
- 自动元素排序
- 图片描述生成
- 以及更多功能...

👉 **访问：https://github.com/deathxlent/prism_pdf**

## 许可

本演示仅用于展示目的。完整许可请参考 GitHub 仓库中的主项目许可协议。
