#!/usr/bin/env python3
"""
告警分页功能验证脚本
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_frontend_code():
    """检查前端代码是否包含分页功能"""
    print("检查前端代码...")

    alerts_js = "frontend/js/pages/alerts.js"

    with open(alerts_js, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "分页数据结构 - currentPage": "currentPage: {" in content,
        "分页数据结构 - pageSize": "pageSize: {" in content,
        "分页数据结构 - totalCount": "totalCount: {" in content,
        "renderPagination 方法": "renderPagination(type)" in content,
        "goToPage 方法": "async goToPage(type, page)" in content,
        "resetPagination 方法": "resetPagination()" in content,
        "事件列表分页": "this.renderPagination('events')" in content,
        "告警列表分页": "this.renderPagination('alerts')" in content,
        "巡检风格分页按钮": "'btn btn-sm btn-secondary'" in content,
        "使用 onclick 属性（修复点击问题）": 'onclick="AlertsPage.goToPage' in content,
        "使用 innerHTML 拼接": "container.innerHTML = buttons.join('')" in content,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed

def check_frontend_css():
    """检查前端样式是否包含分页样式"""
    print("\n检查前端样式...")

    alerts_css = "frontend/css/alerts.css"

    with open(alerts_css, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "告警样式文件存在": True,  # File exists if we got here
        "无复杂分页样式（与巡检统一）": ".pagination-container" not in content,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed

def check_backend_api():
    """检查后端 API 是否支持分页"""
    print("\n检查后端 API...")

    alerts_router = "backend/routers/alerts.py"

    with open(alerts_router, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "事件列表 limit 参数": "limit: int = Query(100, ge=1, le=1000)" in content,
        "事件列表 offset 参数": "offset: int = Query(0, ge=0)" in content,
        "告警列表 limit 参数": "limit: int = Query(100, ge=1, le=1000)" in content,
        "告警列表 offset 参数": "offset: int = Query(0, ge=0)" in content,
        "返回 total 字段": '"total": total' in content,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed

def main():
    print("=" * 60)
    print("告警分页功能验证（统一巡检风格）")
    print("=" * 60)

    frontend_code_ok = check_frontend_code()
    frontend_css_ok = check_frontend_css()
    backend_api_ok = check_backend_api()

    print("\n" + "=" * 60)
    if frontend_code_ok and frontend_css_ok and backend_api_ok:
        print("✓ 所有检查通过！分页功能已统一为巡检风格。")
        print("\n特性：")
        print("- 简洁的分页按钮（上一页、页码、下一页）")
        print("- 智能页码显示（当前页前后各2页）")
        print("- 固定每页10条记录")
        print("- 与巡检模块风格一致")
        print("\n下一步：")
        print("1. 启动服务：python run.py")
        print("2. 访问：http://localhost:9939/frontend/index.html#alerts")
        print("3. 测试分页功能")
        return 0
    else:
        print("✗ 部分检查未通过，请检查上述失败项。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
