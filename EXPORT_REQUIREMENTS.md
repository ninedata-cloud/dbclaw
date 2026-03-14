# 巡检报告导出功能

## 功能说明

SmartDBA 现在支持将巡检报告导出为 PDF 和 Markdown 格式。

### 功能特性

1. **中文报告生成**：巡检报告使用中文生成，包含以下必需章节：
   - 数据库配置
   - 数据库负载指标
   - 主机负载指标
   - TOP SQL
   - 空间使用情况

2. **Markdown 导出**：直接下载报告的 Markdown 源文件

3. **PDF 导出**：将报告转换为格式化的 PDF 文档

## 安装依赖

PDF 导出功能需要安装 `weasyprint` 库：

```bash
pip install weasyprint
```

### WeasyPrint 系统依赖

WeasyPrint 需要一些系统级依赖：

**macOS:**
```bash
brew install pango cairo gdk-pixbuf libffi
```

**Ubuntu/Debian:**
```bash
sudo apt-get install python3-dev python3-pip python3-setuptools python3-wheel python3-cffi libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

**CentOS/RHEL:**
```bash
sudo yum install python3-devel cairo pango gdk-pixbuf2 libffi-devel
```

## 使用方法

### 前端使用

1. 进入巡检仪表板页面
2. 选择数据源并查看巡检报告
3. 在报告详情弹窗中，点击右上角的导出按钮：
   - **📄 导出 Markdown**：下载 .md 文件
   - **📑 导出 PDF**：下载 .pdf 文件

### API 端点

**导出 Markdown:**
```
GET /api/inspections/reports/export/{report_id}/markdown
```

**导出 PDF:**
```
GET /api/inspections/reports/export/{report_id}/pdf
```

## 技术实现

### 后端修改

1. **prompts.py**：修改 `INSPECTION_REPORT_PROMPT` 为中文提示词
2. **inspections.py**：添加两个导出端点
3. **report_generator.py**：在生成报告时同时生成 HTML 内容

### 前端修改

1. **inspection-dashboard.js**：在报告详情弹窗中添加导出按钮

## 文件命名规则

导出的文件使用以下命名格式：
- Markdown: `inspection_report_{report_id}_{timestamp}.md`
- PDF: `inspection_report_{report_id}_{timestamp}.pdf`

其中 timestamp 格式为 `YYYYMMDD_HHMMSS`

## 注意事项

1. 如果未安装 weasyprint，PDF 导出将返回 500 错误并提示安装
2. 报告必须已完成生成才能导出
3. PDF 导出需要报告的 HTML 内容，Markdown 导出需要 Markdown 内容
4. 中文字体支持：WeasyPrint 会自动使用系统中文字体，确保系统已安装中文字体
