# 巡检报告导出功能快速入门

## 功能概述

SmartDBA 现已支持生成中文巡检报告，并可导出为 PDF 和 Markdown 格式。

## 已实现的功能

### ✅ 1. 中文巡检报告生成

巡检报告现在使用中文生成，包含以下必需章节：

- **数据库配置** - 版本、运行时间、关键参数
- **数据库负载指标** - QPS、TPS、连接数、缓存命中率
- **主机负载指标** - CPU、内存、磁盘使用率
- **TOP SQL** - 最慢的查询及其执行时间
- **空间使用情况** - 最大的表及其大小

### ✅ 2. Markdown 导出

- API 端点：`GET /api/inspections/reports/export/{report_id}/markdown`
- 直接下载报告的 Markdown 源文件
- 文件命名：`inspection_report_{report_id}_{timestamp}.md`

### ✅ 3. PDF 导出

- API 端点：`GET /api/inspections/reports/export/{report_id}/pdf`
- 将报告转换为格式化的 PDF 文档
- 文件命名：`inspection_report_{report_id}_{timestamp}.pdf`
- 支持中文字体渲染

### ✅ 4. 前端导出按钮

在巡检报告详情弹窗中添加了两个导出按钮：
- 📄 导出 Markdown
- 📑 导出 PDF

## 使用方法

### 前端操作

1. 访问巡检仪表板页面：`/inspection-dashboard.html`
2. 选择数据源
3. 点击查看任意巡检报告
4. 在报告详情弹窗右上角，点击导出按钮

### API 调用

**导出 Markdown:**
```bash
curl -O http://localhost:8000/api/inspections/reports/export/1/markdown
```

**导出 PDF:**
```bash
curl -O http://localhost:8000/api/inspections/reports/export/1/pdf
```

## 安装 PDF 导出依赖（可选）

PDF 导出功能需要 `weasyprint` 库及其系统依赖。

### 1. 安装 Python 包

```bash
pip install weasyprint
```

### 2. 安装系统依赖

**macOS:**
```bash
brew install pango cairo gdk-pixbuf libffi
```

**Ubuntu/Debian:**
```bash
sudo apt-get install python3-dev python3-pip python3-setuptools python3-wheel \
    python3-cffi libcairo2 libpango-1.0-0 libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 libffi-dev shared-mime-info
```

**CentOS/RHEL:**
```bash
sudo yum install python3-devel cairo pango gdk-pixbuf2 libffi-devel
```

### 注意事项

- 如果不安装 weasyprint，Markdown 导出仍然可用
- PDF 导出在未安装 weasyprint 时会返回 500 错误并提示安装
- 系统需要安装中文字体以正确渲染 PDF 中的中文内容

## 技术实现细节

### 修改的文件

1. **backend/agent/prompts.py**
   - 修改 `INSPECTION_REPORT_PROMPT` 为中文提示词

2. **backend/routers/inspections.py**
   - 添加 `export_report_markdown()` 端点
   - 添加 `export_report_pdf()` 端点

3. **backend/services/report_generator.py**
   - 在 `generate_inspection_report()` 中添加 HTML 生成逻辑
   - 使用 markdown-it-py 将 Markdown 转换为 HTML
   - 添加中文友好的 CSS 样式

4. **frontend/js/pages/inspection-dashboard.js**
   - 修改 `viewReport()` 函数添加导出按钮
   - 添加 `exportMarkdown()` 和 `exportPDF()` 函数

### 报告生成流程

```
用户触发巡检
    ↓
AI 使用中文提示词生成报告
    ↓
生成 Markdown 内容 (content_md)
    ↓
转换为 HTML (content_html)
    ↓
保存到数据库
    ↓
用户可导出 Markdown 或 PDF
```

## 验证功能

运行验证脚本检查功能是否正确实现：

```bash
python verify_export.py
```

预期输出：
```
1. Checking INSPECTION_REPORT_PROMPT... ✅ PASS
2. Checking export endpoints... ✅ PASS
3. Checking HTML generation... ✅ PASS
4. Checking frontend export buttons... ✅ PASS
5. Checking weasyprint (optional)... ⚠️ Not installed (optional)
```

## 故障排除

### PDF 导出失败

**问题：** 点击 "导出 PDF" 后返回错误

**解决方案：**
1. 检查是否安装了 weasyprint：`pip list | grep weasyprint`
2. 检查系统依赖是否安装（见上文安装说明）
3. 查看后端日志获取详细错误信息

### 中文显示为方块

**问题：** PDF 中的中文显示为方块或乱码

**解决方案：**
1. 确保系统安装了中文字体
2. macOS 通常自带中文字体
3. Linux 系统可能需要安装：`sudo apt-get install fonts-noto-cjk`

### 报告内容为空

**问题：** 导出的文件为空或显示 "Report content not available"

**解决方案：**
1. 确保报告已完成生成（status = "completed"）
2. 检查数据库中 content_md 和 content_html 字段是否有内容
3. 重新触发巡检生成新报告

## 下一步

功能已完全实现并可以使用。建议：

1. 测试生成一份巡检报告
2. 尝试导出 Markdown 和 PDF
3. 根据需要安装 weasyprint 依赖
4. 如有问题，查看后端日志或参考故障排除部分
