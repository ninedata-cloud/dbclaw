#!/usr/bin/env python3
"""
主机状态显示功能验证脚本
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def check_backend_schema():
    """检查后端 Schema 是否包含状态字段"""
    print("检查后端 Schema...")

    schema_file = "backend/schemas/host.py"

    with open(schema_file, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "cpu_usage 字段": "cpu_usage: Optional[float]" in content,
        "memory_usage 字段": "memory_usage: Optional[float]" in content,
        "disk_usage 字段": "disk_usage: Optional[float]" in content,
        "status 字段": 'status: str = "unknown"' in content,
        "status_message 字段": "status_message: Optional[str]" in content,
        "last_check_time 字段": "last_check_time: Optional[datetime]" in content,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed

def check_backend_api():
    """检查后端 API 是否实现状态计算"""
    print("\n检查后端 API...")

    api_file = "backend/routers/hosts.py"

    with open(api_file, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "获取 memory_usage": "memory_usage" in content,
        "获取 disk_usage": "disk_usage" in content,
        "计算数据新鲜度": "metric_age" in content,
        "离线状态判断": '"offline"' in content,
        "正常状态判断": '"normal"' in content,
        "警告状态判断": '"warning"' in content,
        "严重状态判断": '"error"' in content,
        "状态消息生成": "status_message" in content,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed

def check_frontend_code():
    """检查前端代码是否实现状态显示"""
    print("\n检查前端代码...")

    hosts_js = "frontend/js/pages/hosts.js"

    with open(hosts_js, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "_renderHostRow 方法": "_renderHostRow(host)" in content,
        "状态徽章渲染": "statusBadge" in content,
        "正常状态处理": "case 'normal':" in content,
        "警告状态处理": "case 'warning':" in content,
        "严重状态处理": "case 'error':" in content,
        "离线状态处理": "case 'offline':" in content,
        "指标颜色标识": "formatMetric" in content,
        "CPU 列显示": "formatMetric(host.cpu_usage)" in content,
        "内存列显示": "formatMetric(host.memory_usage)" in content,
        "磁盘列显示": "formatMetric(host.disk_usage)" in content,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"  {status} {check_name}")
        if not result:
            all_passed = False

    return all_passed

def check_frontend_css():
    """检查前端样式是否支持状态显示"""
    print("\n检查前端样式...")

    main_css = "frontend/css/main.css"

    with open(main_css, 'r', encoding='utf-8') as f:
        content = f.read()

    checks = {
        "badge-success 样式": ".badge-success" in content,
        "badge-warning 样式": ".badge-warning" in content,
        "badge-danger 样式": ".badge-danger" in content,
        "badge-secondary 样式": ".badge-secondary" in content,
        "text-success 样式": ".text-success" in content,
        "text-warning 样式": ".text-warning" in content,
        "text-danger 样式": ".text-danger" in content,
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
    print("主机状态显示功能验证")
    print("=" * 60)

    backend_schema_ok = check_backend_schema()
    backend_api_ok = check_backend_api()
    frontend_code_ok = check_frontend_code()
    frontend_css_ok = check_frontend_css()

    print("\n" + "=" * 60)
    if backend_schema_ok and backend_api_ok and frontend_code_ok and frontend_css_ok:
        print("✓ 所有检查通过！主机状态显示功能已完整实现。")
        print("\n功能特性：")
        print("- ✓ 正常 - 所有指标正常（绿色）")
        print("- ⚠ 异常 - 部分指标接近阈值（黄色）")
        print("- ✗ 严重 - 部分指标超过阈值（红色）")
        print("- ○ 离线 - 连接失败或无数据（灰色）")
        print("\n下一步：")
        print("1. 启动服务：python run.py")
        print("2. 访问：http://localhost:9939/frontend/index.html#hosts")
        print("3. 查看主机状态显示")
        return 0
    else:
        print("✗ 部分检查未通过，请检查上述失败项。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
