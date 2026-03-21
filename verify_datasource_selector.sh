#!/bin/bash
# 验证数据源选择器组件集成

echo "=== 数据源选择器组件验证 ==="
echo ""

# 1. 检查组件文件是否存在
echo "1. 检查组件文件..."
if [ -f "frontend/js/components/datasource-selector.js" ]; then
    echo "   ✓ datasource-selector.js 存在"
else
    echo "   ✗ datasource-selector.js 不存在"
    exit 1
fi

if [ -f "frontend/css/datasource-selector.css" ]; then
    echo "   ✓ datasource-selector.css 存在"
else
    echo "   ✗ datasource-selector.css 不存在"
    exit 1
fi

# 2. 检查 index.html 是否引入了组件
echo ""
echo "2. 检查 index.html 引入..."
if grep -q "datasource-selector.css" frontend/index.html; then
    echo "   ✓ CSS 已引入"
else
    echo "   ✗ CSS 未引入"
fi

if grep -q "datasource-selector.js" frontend/index.html; then
    echo "   ✓ JS 已引入"
else
    echo "   ✗ JS 未引入"
fi

# 3. 检查 inspection.js 是否使用了新组件
echo ""
echo "3. 检查 inspection.js 迁移..."
if grep -q "DatasourceSelector" frontend/js/pages/inspection.js; then
    echo "   ✓ 使用了 DatasourceSelector 组件"
else
    echo "   ✗ 未使用 DatasourceSelector 组件"
fi

if grep -q "datasourceSelector: null" frontend/js/pages/inspection.js; then
    echo "   ✓ 添加了 datasourceSelector 属性"
else
    echo "   ✗ 未添加 datasourceSelector 属性"
fi

if grep -q "datasourceSelector.destroy()" frontend/js/pages/inspection.js; then
    echo "   ✓ 添加了清理逻辑"
else
    echo "   ✗ 未添加清理逻辑"
fi

# 4. 检查服务是否运行
echo ""
echo "4. 检查服务状态..."
if curl -s http://localhost:9939/ > /dev/null 2>&1; then
    echo "   ✓ 服务正在运行 (http://localhost:9939)"
else
    echo "   ✗ 服务未运行"
fi

# 5. 检查文档是否存在
echo ""
echo "5. 检查文档..."
if [ -f "docs/DATASOURCE_SELECTOR_GUIDE.md" ]; then
    echo "   ✓ 使用文档存在"
else
    echo "   ✗ 使用文档不存在"
fi

if [ -f "docs/DATASOURCE_SELECTOR_MIGRATION.md" ]; then
    echo "   ✓ 迁移指南存在"
else
    echo "   ✗ 迁移指南不存在"
fi

if [ -f "frontend/datasource-selector-demo.html" ]; then
    echo "   ✓ 示例页面存在"
else
    echo "   ✗ 示例页面不存在"
fi

echo ""
echo "=== 验证完成 ==="
echo ""
echo "访问以下页面进行测试："
echo "  - 智能巡检页面: http://localhost:9939/#/inspection"
echo "  - 示例页面: http://localhost:9939/datasource-selector-demo.html"
echo ""
