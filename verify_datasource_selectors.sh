#!/bin/bash
echo "检查所有数据源选择器的宽度设置："
echo ""
echo "=== Monitor Page ==="
grep -n "minWidth.*connSelect" frontend/js/pages/monitor.js
echo ""
echo "=== Query Page ==="
grep -n "minWidth.*connSelect" frontend/js/pages/query.js
echo ""
echo "=== Diagnosis Page ==="
grep -n "minWidth.*connSelect" frontend/js/pages/diagnosis.js
echo ""
echo "=== Inspection Page ==="
grep -n "min-width.*filterDatasource" frontend/js/pages/inspection.js
echo ""
echo "=== Skills Page ==="
grep -n "min-width.*datasource_id" frontend/js/pages/skills.js
echo ""
echo "=== CSS定义 ==="
grep -n "datasource-select" frontend/css/main.css
